"""Three-play reconciliation for ambiguous canonical transition failures.

Diagnostic only. For an ambiguous A->B mismatch, inspect B->C and ask whether
one structured state field at B is isolated while the surrounding sequence is
otherwise coherent. No values are corrected here.
"""
from __future__ import annotations
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from cfb_analytics.canonical.failure_classification import classify_failure
from cfb_analytics.canonical.materialize import canonical_partition_dir
from cfb_analytics.canonical.transitions import _audit_pair, _num
from cfb_analytics.canonical.forensics import _ordering_signals
from cfb_analytics.raw.audit import discover_partitions
from cfb_analytics.raw.sequence import _candidate_sort_key


def _load(path: Path): return json.loads(path.read_text(encoding="utf-8"))

def _same_series(a,b):
    return a.get("driveId") is not None and a.get("driveId")==b.get("driveId") and a.get("offense")==b.get("offense")

def _expected_field(a):
    y,g=a.get("yardsToGoal"),a.get("analyticsYardsGained")
    return y-g if _num(y) and _num(g) else None

def _expected_distance(a):
    d,g,down=a.get("distance"),a.get("analyticsYardsGained"),a.get("down")
    if not all(_num(x) for x in (d,g,down)): return None
    if g<d and int(down)<4: return d-g
    return None

def _close(a,b,tol=1): return _num(a) and _num(b) and abs(a-b)<=tol

def classify_ambiguous_triplet(a,b,c):
    """Refine an ambiguous A->B failure using the next canonical play C."""
    flags_ab=_audit_pair(a,b)
    base=classify_failure(a,b,flags_ab)
    if base["classification"]!="AMBIGUOUS_STATE_SUSPECT": return {"subtype":"NOT_AMBIGUOUS","confidence":"LOW","reasons":[]}
    reasons=[]
    if c is None: return {"subtype":"NO_LOOKAHEAD","confidence":"LOW","reasons":["no following play"]}
    failed=[k for k,v in _ordering_signals(b,c).items() if v is False]
    if failed:
        return {"subtype":"LIKELY_CHRONOLOGY","confidence":"HIGH","reasons":["B->C ordering failure: "+", ".join(failed)]}
    if not _same_series(b,c):
        return {"subtype":"LOOKAHEAD_BOUNDARY","confidence":"LOW","reasons":["C leaves B drive/offense"]}

    flags_bc=_audit_pair(b,c)
    ef_ab=_expected_field(a); ef_bc=_expected_field(b)
    ed_ab=_expected_distance(a); ed_bc=_expected_distance(b)
    b_field_bad=ef_ab is not None and _num(b.get("yardsToGoal")) and not _close(b["yardsToGoal"],ef_ab)
    c_field_from_b_ok=ef_bc is not None and _close(c.get("yardsToGoal"),ef_bc)
    b_dist_bad=ed_ab is not None and _num(b.get("distance")) and not _close(b["distance"],ed_ab)
    c_dist_from_b_ok=ed_bc is not None and _close(c.get("distance"),ed_bc)

    if b_field_bad and c_field_from_b_ok and not b_dist_bad:
        reasons.append("B field position disagrees with A but B->C field progression reconciles")
        return {"subtype":"LIKELY_BAD_FIELD_POSITION_B","confidence":"HIGH","reasons":reasons}
    if b_dist_bad and c_dist_from_b_ok and not b_field_bad:
        reasons.append("B distance disagrees with A but B->C distance progression reconciles")
        return {"subtype":"LIKELY_BAD_DISTANCE_B","confidence":"HIGH","reasons":reasons}
    if b_field_bad and b_dist_bad and not flags_bc:
        reasons.append("A->B state disagrees while B->C is clean")
        return {"subtype":"LIKELY_MISSING_INTERMEDIATE_STATE","confidence":"MEDIUM","reasons":reasons}
    if flags_bc:
        reasons.append("both A->B and B->C remain inconsistent")
        return {"subtype":"PERSISTENT_STATE_INCONSISTENCY","confidence":"LOW","reasons":reasons}
    return {"subtype":"STILL_AMBIGUOUS","confidence":"LOW","reasons":["lookahead does not isolate one field"]}


def ambiguous_state_audit(raw_root:Path,processed_root:Path,seasons:Iterable[int],examples:int=3)->dict[str,Any]:
    counts=Counter(); confidence=Counter(); by_season=defaultdict(Counter); samples=defaultdict(list); ambiguous=0; with_lookahead=0
    for season in seasons:
        for st,wk in discover_partitions(raw_root,season):
            cp=canonical_partition_dir(processed_root,season,st,wk)/"plays.json"
            if not cp.exists(): raise FileNotFoundError(f"Canonical plays missing: {cp}")
            grouped=defaultdict(list)
            for row in _load(cp): grouped[str(row.get("gameId"))].append(row)
            for gid,rows in grouped.items():
                ordered=sorted(rows,key=_candidate_sort_key)
                for i in range(len(ordered)-1):
                    a,b=ordered[i],ordered[i+1]; flags=_audit_pair(a,b)
                    if not flags: continue
                    if classify_failure(a,b,flags)["classification"]!="AMBIGUOUS_STATE_SUSPECT": continue
                    ambiguous+=1; c=ordered[i+2] if i+2<len(ordered) else None
                    if c is not None: with_lookahead+=1
                    result=classify_ambiguous_triplet(a,b,c); sub=result["subtype"]
                    counts[sub]+=1; confidence[result["confidence"]]+=1; by_season[season][sub]+=1
                    if len(samples[sub])<examples:
                        def mini(p):
                            if p is None:return None
                            return {k:p.get(k) for k in ("id","driveId","playNumber","period","clock","down","distance","yardsToGoal","analyticsYardsGained","sourcePlayType","playText")}
                        samples[sub].append({"season":season,"season_type":st,"week":wk,"gameId":gid,"reasons":result["reasons"],"A":mini(a),"B":mini(b),"C":mini(c)})
    return {"ambiguous_pairs":ambiguous,"with_lookahead":with_lookahead,"subtype_counts":dict(counts),"confidence_counts":dict(confidence),"by_season":{str(s):dict(c) for s,c in by_season.items()},"examples":dict(samples),"note":"Three-play diagnostic only; no corrections are applied."}


def concise_ambiguous_state(r):
    total=r["ambiguous_pairs"]
    order=("LIKELY_BAD_FIELD_POSITION_B","LIKELY_BAD_DISTANCE_B","LIKELY_CHRONOLOGY","LIKELY_MISSING_INTERMEDIATE_STATE","PERSISTENT_STATE_INCONSISTENCY","LOOKAHEAD_BOUNDARY","NO_LOOKAHEAD","STILL_AMBIGUOUS")
    lines=["AMBIGUOUS STATE THREE-PLAY AUDIT",f"Ambiguous A->B pairs: {total:,}",f"Pairs with C lookahead: {r['with_lookahead']:,}","","Lookahead hypotheses:"]
    for key in order:
        n=r["subtype_counts"].get(key,0); pct=100*n/total if total else 0
        lines.append(f"  {key:.<43} {n:>6,} ({pct:5.1f}%)")
    lines += ["","Confidence:"]
    for key in ("HIGH","MEDIUM","LOW"):
        n=r["confidence_counts"].get(key,0); pct=100*n/total if total else 0
        lines.append(f"  {key:.<12} {n:>6,} ({pct:5.1f}%)")
    lines += ["","No values are corrected by this audit."]
    return "\n".join(lines)
