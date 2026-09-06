"""Audit promoted analytics yardage corrections in materialized canonical plays."""
from __future__ import annotations
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from cfb_analytics.canonical.corrections import CORRECTION_VERSION
from cfb_analytics.canonical.materialize import canonical_partition_dir
from cfb_analytics.raw.audit import discover_partitions


def _load(path: Path): return json.loads(path.read_text(encoding="utf-8"))

def yardage_correction_audit(processed_root:Path, raw_root:Path, seasons:Iterable[int])->dict[str,Any]:
    scanned=0; corrected=0; bad=[]; deltas=Counter(); sources=Counter(); confidence=Counter(); by_season=Counter()
    for season in seasons:
        for st,wk in discover_partitions(raw_root,season):
            path=canonical_partition_dir(processed_root,season,st,wk)/"plays.json"
            if not path.exists(): raise FileNotFoundError(path)
            for row in _load(path):
                scanned+=1; sources[str(row.get("analyticsYardsSource"))]+=1; confidence[str(row.get("analyticsYardsConfidence"))]+=1
                if row.get("analyticsYardsWasCorrected"):
                    corrected+=1; by_season[season]+=1
                    source=row.get("sourceYardsGained"); value=row.get("analyticsYardsGained"); text=row.get("textYardsGained"); implied=row.get("analyticsYardsFieldImplied")
                    if isinstance(source,(int,float)) and isinstance(value,(int,float)): deltas[value-source]+=1
                    checks={
                        "version":row.get("analyticsYardsCorrectionVersion")==CORRECTION_VERSION,
                        "source":row.get("analyticsYardsSource")=="TEXT_AND_NEXT_STATE",
                        "confidence":row.get("analyticsYardsConfidence")=="HIGH",
                        "text_matches":value==text,
                        "field_supports":isinstance(implied,(int,float)) and isinstance(value,(int,float)) and abs(implied-value)<=1,
                        "source_preserved":row.get("yardsGained")==source,
                        "reason":bool(row.get("analyticsYardsCorrectionReason")),
                    }
                    if not all(checks.values()) and len(bad)<20: bad.append({"id":row.get("id"),"checks":checks})
    checks={"corrected_rows_have_valid_provenance":not bad,"correction_version_current":True}
    return {"status":"PASS" if all(checks.values()) else "REVIEW","plays_scanned":scanned,"corrected":corrected,"checks":checks,"deltas":dict(deltas.most_common()),"sources":dict(sources),"confidence":dict(confidence),"by_season":dict(by_season),"problems":bad}

def concise_yardage_correction_audit(r):
    lines=["CANONICAL YARDAGE CORRECTION AUDIT: "+r["status"],f"Plays scanned: {r['plays_scanned']:,}",f"Analytics yardage corrected: {r['corrected']:,}","","Checks:"]
    for k,v in r["checks"].items(): lines.append(f"  {'PASS' if v else 'FAIL'} {k}")
    lines += ["","Correction deltas:"]
    for d,n in list(r["deltas"].items())[:15]: lines.append(f"  {int(d):+d} yards........ {n:>5,}")
    lines += ["","Corrected by season:"]
    for s,n in sorted(r["by_season"].items()): lines.append(f"  {s}: {n:,}")
    return "\n".join(lines)
