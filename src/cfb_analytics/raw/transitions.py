"""Cross-play state transition diagnostics.

Raw CFBD data is never mutated. This audit reconciles adjacent candidate-ordered
plays, classifies football context, and profiles the remaining ordinary
unexplained mismatches so source errors can be separated from validator limits.
"""
from __future__ import annotations
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable
from cfb_analytics.raw.audit import discover_partitions, partition_dir
from cfb_analytics.raw.sequence import _candidate_sort_key

def _load(path: Path) -> list[dict[str, Any]]: return json.loads(path.read_text(encoding="utf-8"))
def _scrimmage(p): return isinstance(p.get("down"),(int,float)) and 1 <= p["down"] <= 4
def _context(p): return {k:p.get(k) for k in ("id","driveId","driveNumber","playNumber","offense","defense","offenseScore","defenseScore","period","clock","down","distance","yardsToGoal","yardsGained","scoring","playType","playText")}
def _combined(p): return f"{p.get('playType','')} {p.get('playText','')}".lower()
def _play_type(p): return str(p.get("playType") or "<missing>")
def _penalty_signal(p):
 t=str(p.get("playType") or "").lower(); x=str(p.get("playText") or "").lower(); a="penalty" in t; b="penalty" in x
 return "playtype_and_text" if a and b else "playtype_only" if a else "text_only" if b else None
def _penalty_context(a,b):
 aa,bb=_penalty_signal(a),_penalty_signal(b); loc="both" if aa and bb else "previous" if aa else "next" if bb else "none"
 return {"location":loc,"previous_signal":aa,"next_signal":bb}
def _football_context(a,b):
 tags=set(); ta,tb=_combined(a),_combined(b); joined=f"{ta} {tb}"
 if _penalty_signal(a) or _penalty_signal(b): tags.add("penalty")
 if "incomplete" in joined: tags.add("incomplete_pass")
 if "sack" in joined: tags.add("sack")
 if "interception" in joined: tags.add("interception")
 if "fumble" in joined: tags.add("fumble")
 if any(x in joined for x in ("kickoff","punt","field goal","extra point","pat ")): tags.add("special_teams")
 if any(x in joined for x in ("end period","end of quarter","end of half","end of game")): tags.add("period_boundary")
 if any(x in joined for x in ("review","replay","overturned","confirmed","stands")): tags.add("review")
 if any(x in joined for x in ("no play","no-play")): tags.add("no_play")
 if a.get("scoring") or b.get("scoring") or "touchdown" in joined or " td" in joined: tags.add("scoring")
 if a.get("offense") and b.get("offense") and a.get("offense") != b.get("offense"): tags.add("possession_change")
 if a.get("driveId") != b.get("driveId"): tags.add("drive_change")
 if a.get("period") != b.get("period"): tags.add("period_change")
 if any(isinstance(p.get("yardsToGoal"),(int,float)) and isinstance(p.get("distance"),(int,float)) and p["yardsToGoal"] <= p["distance"] for p in (a,b)): tags.add("goal_to_go")
 if any(x in joined for x in ("timeout","time out")): tags.add("timeout")
 if not tags: tags.add("ordinary_unexplained")
 return tags
def _audit_pair(a,b):
 flags=[]; same_drive=a.get("driveId") is not None and a.get("driveId")==b.get("driveId"); same_offense=a.get("offense") is not None and a.get("offense")==b.get("offense")
 if same_offense:
  aos,bos=a.get("offenseScore"),b.get("offenseScore"); ads,bds=a.get("defenseScore"),b.get("defenseScore")
  if all(isinstance(x,(int,float)) and x>=0 for x in (aos,bos)) and bos<aos: flags.append("same_team_offense_score_decrease")
  if all(isinstance(x,(int,float)) and x>=0 for x in (ads,bds)) and bds<ads: flags.append("same_team_defense_score_decrease")
 if not (same_drive and same_offense and _scrimmage(a) and _scrimmage(b)) or a.get("scoring") or b.get("scoring"): return flags
 if any(x in _combined(a) for x in ("penalty","interception","fumble","sack","timeout","kick","punt","end period")): return flags
 da,db=int(a["down"]),int(b["down"]); dista,distb=a.get("distance"),b.get("distance"); ya,yb,g=a.get("yardsToGoal"),b.get("yardsToGoal"),a.get("yardsGained"); expected=None
 if all(isinstance(x,(int,float)) for x in (dista,g)):
  if g<dista and da<4: expected=da+1; flags += ["expected_next_down_mismatch"] if db!=expected else []
  elif g>=dista: expected=1; flags += ["expected_first_down_mismatch"] if db!=1 else []
 if expected is not None and db==expected and all(isinstance(x,(int,float)) for x in (dista,distb,g)) and g<dista and da<4:
  ed=dista-g
  if ed>=0 and abs(distb-ed)>1: flags.append("distance_transition_mismatch")
 if all(isinstance(x,(int,float)) for x in (ya,yb,g)) and 0<=ya<=100 and 0<=yb<=100 and -100<=g<=100:
  ey=ya-g
  if ey>=0 and abs(yb-ey)>1: flags.append("field_position_transition_mismatch")
 return flags
def _bucket(delta):
 d=abs(delta)
 return "2 yards" if d==2 else "3 yards" if d==3 else "4-5 yards" if d<=5 else "6-10 yards" if d<=10 else "11-20 yards" if d<=20 else ">20 yards"
def _ordinary_profile(a,b,flags):
 out={"play_type_pair":f"{_play_type(a)} -> {_play_type(b)}","previous_down":str(a.get("down")),"season_period":str(a.get("period"))}
 if "field_position_transition_mismatch" in flags and all(isinstance(x,(int,float)) for x in (a.get("yardsToGoal"),b.get("yardsToGoal"),a.get("yardsGained"))):
  expected=a["yardsToGoal"]-a["yardsGained"]; out["field_position_error"]=_bucket(b["yardsToGoal"]-expected)
 if "distance_transition_mismatch" in flags and all(isinstance(x,(int,float)) for x in (a.get("distance"),b.get("distance"),a.get("yardsGained"))):
  expected=a["distance"]-a["yardsGained"]; out["distance_error"]=_bucket(b["distance"]-expected)
 return out
def transition_audit(root:Path,seasons:Iterable[int],examples:int=10):
 counts=Counter(); by_season=defaultdict(Counter); samples=defaultdict(list); penalty_by_flag=defaultdict(Counter); context_by_flag=defaultdict(Counter); pair_context=Counter(); ordinary_types=Counter(); ordinary_field=Counter(); ordinary_distance=Counter(); ordinary_seasons=Counter(); ordinary_downs=Counter(); games=pairs=conservative=0; flagged=set(); ordinary=set()
 for season in seasons:
  for st,week in discover_partitions(root,season):
   d=partition_dir(root,season,st,week); game_rows={str(g["id"]):g for g in _load(d/"games.json")}; grouped=defaultdict(list)
   for p in _load(d/"plays.json"): grouped[str(p.get("gameId"))].append(p)
   for gid,raw in grouped.items():
    games+=1; ordered=sorted(raw,key=_candidate_sort_key)
    for a,b in zip(ordered,ordered[1:]):
     pairs+=1
     if a.get("driveId")==b.get("driveId") and a.get("offense")==b.get("offense") and _scrimmage(a) and _scrimmage(b): conservative+=1
     flags=_audit_pair(a,b)
     if not flags: continue
     contexts=_football_context(a,b); penalty=_penalty_context(a,b); key=(gid,str(a.get("id")),str(b.get("id")))
     if key not in flagged:
      flagged.add(key)
      for x in contexts: pair_context[x]+=1
      if "ordinary_unexplained" in contexts:
       ordinary.add(key); prof=_ordinary_profile(a,b,flags); ordinary_types[prof["play_type_pair"]]+=1; ordinary_seasons[season]+=1; ordinary_downs[prof["previous_down"]]+=1
       if "field_position_error" in prof: ordinary_field[prof["field_position_error"]]+=1
       if "distance_error" in prof: ordinary_distance[prof["distance_error"]]+=1
     for flag in flags:
      counts[flag]+=1; by_season[season][flag]+=1; penalty_by_flag[flag][penalty["location"]]+=1
      for x in contexts: context_by_flag[flag][x]+=1
      if len(samples[flag])<examples:
       g=game_rows.get(gid,{}); samples[flag].append({"season":season,"season_type":st,"week":week,"gameId":gid,"game":f"{g.get('awayTeam')} @ {g.get('homeTeam')}","contexts":sorted(contexts),"penalty_context":penalty,"previous":_context(a),"next":_context(b)})
 return {"candidate_order":["gameId","driveNumber","playNumber"],"games_scanned":games,"adjacent_pairs":pairs,"conservative_scrimmage_pairs":conservative,"flagged_unique_pairs":len(flagged),"ordinary_unexplained_unique_pairs":len(ordinary),"counts":dict(counts),"pair_context_counts":dict(pair_context),"context_by_flag":{k:dict(v) for k,v in context_by_flag.items()},"penalty_context_by_flag":{k:dict(v) for k,v in penalty_by_flag.items()},"by_season":{str(s):dict(c) for s,c in by_season.items()},"ordinary_profile":{"play_type_pairs":dict(ordinary_types.most_common()),"field_position_error_magnitude":dict(ordinary_field),"distance_error_magnitude":dict(ordinary_distance),"by_season":{str(k):v for k,v in sorted(ordinary_seasons.items())},"by_previous_down":dict(ordinary_downs)},"examples":dict(samples),"note":"Diagnostic only. Ordinary profiles describe flagged pairs with no detected special football context."}
def concise_transitions(r):
 c=r["counts"]; ctx=r["pair_context_counts"]; op=r["ordinary_profile"]; labels=(("expected_next_down_mismatch","expected next-down mismatch"),("expected_first_down_mismatch","expected first-down mismatch"),("distance_transition_mismatch","distance transition mismatch"),("field_position_transition_mismatch","field-position transition mismatch"),("same_team_offense_score_decrease","same-team offense-score decrease"),("same_team_defense_score_decrease","same-team defense-score decrease"))
 lines=["PLAY STATE TRANSITION AUDIT",f"Games scanned: {r['games_scanned']:,}",f"Adjacent candidate-ordered pairs: {r['adjacent_pairs']:,}",f"Conservative scrimmage pairs: {r['conservative_scrimmage_pairs']:,}",f"Unique flagged pairs: {r['flagged_unique_pairs']:,}",f"Ordinary unexplained unique pairs: {r['ordinary_unexplained_unique_pairs']:,}","","Flagged-pair football context (non-exclusive):"]
 for key in ("penalty","incomplete_pass","sack","interception","fumble","special_teams","scoring","possession_change","drive_change","period_boundary","period_change","review","no_play","goal_to_go","timeout","ordinary_unexplained"): lines.append(f"  {key:.<38} {ctx.get(key,0):>7,}")
 lines.append("\nReconciliation flags:")
 for key,label in labels:
  total=c.get(key,0); unexpl=r["context_by_flag"].get(key,{}).get("ordinary_unexplained",0); lines.append(f"  {label:.<40} {total:>7,}  ordinary-unexplained={unexpl:>6,}")
 lines.extend(["","Ordinary unexplained profile:","  Top play-type pairs:"])
 for k,v in list(op["play_type_pairs"].items())[:12]: lines.append(f"    {k[:48]:.<50} {v:>6,}")
 lines.append("  Field-position error magnitude:")
 for k in ("2 yards","3 yards","4-5 yards","6-10 yards","11-20 yards",">20 yards"): lines.append(f"    {k:.<20} {op['field_position_error_magnitude'].get(k,0):>6,}")
 lines.append("  Distance error magnitude:")
 for k in ("2 yards","3 yards","4-5 yards","6-10 yards","11-20 yards",">20 yards"): lines.append(f"    {k:.<20} {op['distance_error_magnitude'].get(k,0):>6,}")
 lines.extend(["","Context tags may overlap. No raw values are corrected by this command.","Use --json --examples N for full season/down/type profiles and contextual examples."])
 return "\n".join(lines)
