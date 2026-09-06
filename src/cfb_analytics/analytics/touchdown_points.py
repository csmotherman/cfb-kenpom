"""Evidence-based adjudication of actual offensive touchdown sequence points.

Primary evidence is the scoring team's scoreboard delta on the TD record. Only
standard +6/+7/+8 deltas are accepted directly. Abnormal/missing TD-record states
may fall back to the immediate later team-score delta when it is standard.
Everything else remains unresolved. Diagnostic only; no data is modified.
"""
from __future__ import annotations
import json
from collections import Counter,defaultdict
from pathlib import Path
from cfb_analytics.raw.audit import discover_partitions
from cfb_analytics.raw.sequence import _candidate_sort_key
from cfb_analytics.canonical.materialize import canonical_partition_dir
from cfb_analytics.analytics.score_transition_forensics import TD_SUBTYPES,team_score

STANDARD={6,7,8}

def adjudicate_touchdown_points(rows,index,lookback=8):
 td=rows[index];team=td.get("offense")
 if not team:return {"status":"UNRESOLVED","reason":"NO_TEAM"}
 before=None
 for j in range(index-1,max(-1,index-lookback-1),-1):
  s=team_score(rows[j],team)
  if s is not None: before=s;break
 if before is None:return {"status":"UNRESOLVED","reason":"NO_BEFORE_SCORE"}
 td_score=team_score(td,team)
 if td_score is not None:
  d=td_score-before
  if d in STANDARD:return {"status":"RESOLVED","points":d,"source":"TD_RECORD_SCORE","before":before,"tdScore":td_score}
 # Fallback is deliberately narrow: only the immediately following candidate
 # record, and only if it observes the same team's standard +6/+7/+8 delta.
 if index+1<len(rows):
  after=team_score(rows[index+1],team)
  if after is not None:
   d=after-before
   if d in STANDARD:return {"status":"RESOLVED","points":d,"source":"NEXT_RECORD_SCORE","before":before,"tdScore":td_score,"afterScore":after}
 return {"status":"UNRESOLVED","reason":"NONSTANDARD_OR_MISSING_SCORE_STATE","before":before,"tdScore":td_score}

def touchdown_points_audit(raw_root:Path,processed_root:Path,seasons,examples=12):
 totals=Counter();points=Counter();sources=Counter();reasons=Counter();sample=[]
 for season in seasons:
  for st,w in discover_partitions(raw_root,season):
   plays=json.loads((canonical_partition_dir(processed_root,season,st,w)/"plays.json").read_text());games=defaultdict(list)
   for p in plays:games[str(p.get("gameId"))].append(p)
   for game_id,rows in games.items():
    rows=sorted(rows,key=_candidate_sort_key)
    for i,p in enumerate(rows):
     if p.get("eventSubtype") not in TD_SUBTYPES:continue
     totals["touchdowns"]+=1;r=adjudicate_touchdown_points(rows,i)
     if r["status"]=="RESOLVED":
      totals["resolved"]+=1;points[str(r["points"])]+=1;sources[r["source"]]+=1
     else:
      reasons[r["reason"]]+=1
      if len(sample)<examples:sample.append({"season":season,"week":w,"gameId":game_id,"team":p.get("offense"),"reason":r["reason"],"before":r.get("before"),"tdScore":r.get("tdScore"),"tdText":p.get("playText"),"neighbors":[q.get("playText") for q in rows[max(0,i-2):min(len(rows),i+3)]]})
 resolved=totals["resolved"];tds=totals["touchdowns"]
 return {"touchdowns":tds,"resolved":resolved,"coverage":resolved/tds if tds else None,"points":dict(points),"sources":dict(sources),"unresolved_reasons":dict(reasons),"examples":sample}

def concise_touchdown_points_audit(r):
 lines=["TOUCHDOWN POINT ADJUDICATION AUDIT",f"Offensive touchdowns scanned: {r['touchdowns']:,}",f"Resolved to +6/+7/+8 points: {r['resolved']:,} ({r['coverage']:.2%})" if r['coverage'] is not None else "Resolved: 0","","Resolved touchdown sequence points:"]
 for k,v in sorted(r['points'].items(),key=lambda x:int(x[0])):lines.append(f"+{k} points{'.'*24} {v:>8,}")
 lines.append("\nEvidence source:")
 for k,v in sorted(r['sources'].items(),key=lambda x:-x[1]):lines.append(f"{k:.<36} {v:>8,}")
 lines.append("\nUnresolved reasons:")
 for k,v in sorted(r['unresolved_reasons'].items(),key=lambda x:-x[1]):lines.append(f"{k:.<36} {v:>8,}")
 lines += ["",f"Unresolved touchdowns: {r['touchdowns']-r['resolved']:,}","Only standard +6/+7/+8 scoreboard evidence is accepted; abnormal states are not coerced.","No data is modified. Use --json --examples N for unresolved cases."]
 return "\n".join(lines)
