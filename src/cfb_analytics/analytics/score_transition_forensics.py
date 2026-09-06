"""Forensic audit of team-specific scoreboard deltas around offensive touchdowns.

Uses team identity to interpret offenseScore/defenseScore across possession changes:
if the scoring team is offense, offenseScore is its score; if it is defense,
defenseScore is its score. We compare the nearest trustworthy score before a TD
with the first later trustworthy score for the same team. Diagnostic only.
"""
from __future__ import annotations
import json
from collections import Counter,defaultdict
from pathlib import Path
from cfb_analytics.raw.audit import discover_partitions
from cfb_analytics.raw.sequence import _candidate_sort_key
from cfb_analytics.canonical.materialize import canonical_partition_dir

TD_SUBTYPES={"RUSH_TD","PASS_TD"}

def _num(v): return isinstance(v,(int,float)) and not isinstance(v,bool)

def team_score(play,team):
 if play.get("offense")==team and _num(play.get("offenseScore")): return int(play["offenseScore"])
 if play.get("defense")==team and _num(play.get("defenseScore")): return int(play["defenseScore"])
 return None

def touchdown_score_delta(rows,index,lookback=8,lookahead=12):
 td=rows[index]; team=td.get("offense")
 if not team: return {"status":"NO_TEAM"}
 before=None; before_i=None
 for j in range(index-1,max(-1,index-lookback-1),-1):
  s=team_score(rows[j],team)
  if s is not None:
   before=s;before_i=j;break
 td_score=team_score(td,team)
 after=None;after_i=None
 for j in range(index+1,min(len(rows),index+lookahead+1)):
  s=team_score(rows[j],team)
  if s is not None:
   after=s;after_i=j;break
 if before is None: return {"status":"NO_BEFORE_SCORE","team":team,"tdScore":td_score,"afterScore":after}
 if after is None: return {"status":"NO_AFTER_SCORE","team":team,"beforeScore":before,"tdScore":td_score}
 delta=after-before
 return {"status":"RESOLVED","team":team,"beforeScore":before,"tdScore":td_score,"afterScore":after,"delta":delta,"beforeOffset":index-before_i,"afterOffset":after_i-index}

def score_transition_audit(raw_root:Path,processed_root:Path,seasons,examples=12):
 totals=Counter();deltas=Counter();td_states=Counter();offsets=Counter();sample=[]
 for season in seasons:
  for st,w in discover_partitions(raw_root,season):
   plays=json.loads((canonical_partition_dir(processed_root,season,st,w)/"plays.json").read_text());games=defaultdict(list)
   for p in plays: games[str(p.get("gameId"))].append(p)
   for game_id,rows in games.items():
    rows=sorted(rows,key=_candidate_sort_key)
    for i,p in enumerate(rows):
     if p.get("eventSubtype") not in TD_SUBTYPES: continue
     totals["touchdowns"]+=1;r=touchdown_score_delta(rows,i);totals[r["status"]]+=1
     if r["status"]=="RESOLVED":
      deltas[str(r["delta"])]+=1;offsets[f"after_plus_{r['afterOffset']}"]+=1
      if r.get("tdScore") is None: td_states["TD_SCORE_MISSING"]+=1
      else:
       td_delta=r["tdScore"]-r["beforeScore"]
       td_states[f"TD_RECORD_DELTA_{td_delta}"]+=1
      if r["delta"] not in (6,7,8) and len(sample)<examples:
       sample.append({"season":season,"week":w,"gameId":game_id,"team":r["team"],"delta":r["delta"],"before":r["beforeScore"],"tdScore":r.get("tdScore"),"after":r["afterScore"],"tdText":p.get("playText"),"neighbors":[q.get("playText") for q in rows[max(0,i-2):min(len(rows),i+4)]]})
     elif len(sample)<examples:
      sample.append({"season":season,"week":w,"gameId":game_id,"status":r["status"],"tdText":p.get("playText")})
 resolved=totals["RESOLVED"];standard=sum(int(deltas.get(str(x),0)) for x in (6,7,8))
 return {"touchdowns":totals["touchdowns"],"resolved":resolved,"coverage":resolved/totals["touchdowns"] if totals["touchdowns"] else None,"standard_6_7_8":standard,"standard_rate":standard/resolved if resolved else None,"status_counts":dict(totals),"score_deltas":dict(deltas),"td_record_score_states":dict(td_states),"after_offsets":dict(offsets),"examples":sample}

def concise_score_transition_audit(r):
 lines=["TOUCHDOWN SCORE-TRANSITION FORENSICS",f"Offensive touchdowns scanned: {r['touchdowns']:,}",f"Resolved team-score transitions: {r['resolved']:,} ({r['coverage']:.2%})" if r['coverage'] is not None else "Resolved: 0",f"Resolved deltas of +6/+7/+8: {r['standard_6_7_8']:,} ({r['standard_rate']:.2%})" if r['standard_rate'] is not None else "Standard deltas: 0","","Team score delta after TD:"]
 for k,v in sorted(r['score_deltas'].items(),key=lambda x:(-x[1],x[0])): lines.append(f"{('+'+k if not k.startswith('-') else k):.<18} {v:>8,}")
 lines.append("\nScore state on TD record:")
 for k,v in sorted(r['td_record_score_states'].items(),key=lambda x:-x[1]): lines.append(f"{k:.<32} {v:>8,}")
 lines.append("\nFirst later team-score observation:")
 for k,v in sorted(r['after_offsets'].items(),key=lambda x:-x[1]): lines.append(f"{k:.<24} {v:>8,}")
 unresolved=r['touchdowns']-r['resolved'];lines += ["",f"Unresolved touchdowns: {unresolved:,}","Diagnostic only: no points are attached and no data is modified.","Use --json --examples N to inspect non-6/7/8 and unresolved cases."]
 return "\n".join(lines)
