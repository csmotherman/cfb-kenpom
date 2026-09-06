"""Residual audit for the exact shared three-and-out residual population."""
from __future__ import annotations
from collections import Counter,defaultdict
from cfb_analytics.analytics.three_and_out_forensics import classify_possession
EXPECTED_CORPUS_RESIDUAL=870

def audit_partition(drives,plays):
 by_drive=defaultdict(list);by_game=defaultdict(list);c=Counter();examples=[]
 for p in plays:by_drive[(str(p.get("gameId")),str(p.get("driveId")))].append(p);by_game[str(p.get("gameId"))].append(p)
 for d in drives:
  if not (d.get("isPossessionDrive") is True and d.get("driveValidationStatus")=="PASS" and d.get("offense")):continue
  gid=str(d.get("gameId"));did=str(d.get("driveId"));rows=by_drive[(gid,did)];x=classify_possession(d,rows,by_game[gid])
  if not x["residual"]:continue
  c["residual"]+=1;last=x["snaps"][-1];dist=last.get("distance");yards=last.get("analyticsYardsGained")
  if isinstance(dist,(int,float)) and isinstance(yards,(int,float)):
   c["terminal_structural_conversion" if yards>=dist else "terminal_failed_to_convert"]+=1
  if any(p.get("down")==4 and p.get("isOffensivePlay") is True and not p.get("hasNoPlayContext",False) for p in rows):c["fourth_down_record_same_drive"]+=1
  period=last.get("period") or last.get("quarter");clock=last.get("clock") or last.get("clockDisplayValue") or last.get("clockText")
  if period in (2,4):c["terminal_q2_q4"]+=1
  cs=str(clock or "");c["near_zero_clock_text"]+=int(cs.startswith("0:") or cs.startswith("00:") or cs in {"0","0.0","00:00"})
  game=by_game[gid];idxs=[i for i,p in enumerate(game) if str(p.get("driveId"))==did];nxt=None
  if idxs:
   for p in game[max(idxs)+1:max(idxs)+6]:
    if p.get("offense") and p.get("offense")!=d.get("offense"):nxt=p;break
  c["next_opponent_possession_signal" if nxt else "no_next_opponent_signal"]+=1
  if len(examples)<60:examples.append({"season":d.get("season"),"gameId":d.get("gameId"),"driveId":d.get("driveId"),"offense":d.get("offense"),"defense":d.get("defense"),"terminalDistance":dist,"terminalYards":yards,"period":period,"clock":clock,"driveResult":d.get("driveResult") or d.get("result"),"nextOpponentSignal":bool(nxt)})
 return c,examples
def merge(results):
 c=Counter();examples=[]
 for x,e in results:c.update(x);examples.extend(e[:max(0,60-len(examples))])
 return {"counts":dict(c),"examples":examples,"corpus_residual_matches_expected":c.get("residual",0)==EXPECTED_CORPUS_RESIDUAL}
def concise(r):
 c=r["counts"];ok=r["corpus_residual_matches_expected"];return "\n".join([f"THREE-AND-OUT RESIDUAL FORENSICS: {'PASS' if ok else 'REVIEW'}",f"Shared-classifier residuals: {c.get('residual',0):,}",f"Expected locked diagnostic residual: {EXPECTED_CORPUS_RESIDUAL:,}",f"Population assertion: {'PASS' if ok else 'FAIL'}","",f"Terminal failed-to-convert by yards/distance: {c.get('terminal_failed_to_convert',0):,}",f"Terminal structural conversion: {c.get('terminal_structural_conversion',0):,}",f"Fourth-down record in same drive: {c.get('fourth_down_record_same_drive',0):,}",f"Terminal in Q2/Q4: {c.get('terminal_q2_q4',0):,}",f"Near-zero clock text: {c.get('near_zero_clock_text',0):,}",f"Next-opponent-possession signal: {c.get('next_opponent_possession_signal',0):,}",f"No next-opponent signal: {c.get('no_next_opponent_signal',0):,}","","Residual analysis is valid only when the population assertion passes.","Use --json for representative residual possessions."])
