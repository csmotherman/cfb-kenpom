"""Production-candidate audit for First-Down Generation v1.

Candidate event rule is evidence-union, not agreement-only:
- structural line-to-gain conversion (analytics yards >= pre-snap distance), OR
- offensive touchdown, OR
- chronology-observed next clean offensive snap resets to down 1.

The sequence audit showed that requiring agreement is unsafe: split non-scrimmage
records (notably fumble-recovery/turnover records) can sit between valid series,
and terminal clean snaps can be followed by non-scrimmage terminal records.
This module audits the union rule and its offense/defense mirrors before any
propagation.
"""
from __future__ import annotations
from collections import Counter,defaultdict
from cfb_analytics.raw.sequence import _candidate_sort_key

def _clean(rows):return [p for p in sorted(rows,key=_candidate_sort_key) if p.get("isScrimmagePlay") is True and p.get("isOffensivePlay") is True and not p.get("hasNoPlayContext",False)]
def _text(p):return " ".join(str(p.get(k) or "") for k in ("sourcePlayType","eventCategory","eventSubtype")).upper()
def _td(p):return "TOUCHDOWN" in _text(p)
def audit_partition(drives,plays):
 bd=defaultdict(list);c=Counter();team=defaultdict(Counter)
 for p in plays:bd[(str(p.get("gameId")),str(p.get("driveId")))].append(p)
 for d in drives:
  if not (d.get("isPossessionDrive") is True and d.get("driveValidationStatus")=="PASS" and d.get("offense")):continue
  gid=str(d.get("gameId"));off=d.get("offense");deff=d.get("defense");snaps=_clean(bd[(gid,str(d.get("driveId")))])
  for i,p in enumerate(snaps):
   dist,y=p.get("distance"),p.get("analyticsYardsGained");struct=isinstance(dist,(int,float)) and isinstance(y,(int,float)) and y>=dist;td=_td(p);nxt=snaps[i+1] if i+1<len(snaps) else None;reset=nxt is not None and nxt.get("down")==1
   event=struct or td or reset
   c["eligible_snaps"]+=1;c["structural"]+=int(struct);c["touchdown"]+=int(td);c["observed_reset"]+=int(reset);c["candidate_first_downs"]+=int(event)
   c["struct_only"]+=int(struct and not td and not reset);c["reset_only"]+=int(reset and not struct and not td);c["td_only"]+=int(td and not struct and not reset);c["multiple_evidence"]+=int(event and sum((struct,td,reset))>=2)
   if event:
    team[(gid,off)]["firstDownsGenerated"]+=1
    if deff:team[(gid,deff)]["firstDownsAllowed"]+=1
 for x in team.values():c["team_offense_events"]+=x["firstDownsGenerated"];c["team_defense_events"]+=x["firstDownsAllowed"]
 return c
def merge(rs):
 c=Counter()
 for x in rs:c.update(x)
 return dict(c)
def concise(c):
 ok=c.get("candidate_first_downs",0)==c.get("team_offense_events",0)==c.get("team_defense_events",0)
 return "\n".join(["FIRST-DOWN GENERATION PRODUCTION-CANDIDATE FORENSICS",f"Clean offensive scrimmage snaps: {c.get('eligible_snaps',0):,}",f"Candidate first downs generated: {c.get('candidate_first_downs',0):,}","",f"Structural line-to-gain evidence: {c.get('structural',0):,}",f"Touchdown evidence: {c.get('touchdown',0):,}",f"Observed next-snap first-down reset: {c.get('observed_reset',0):,}",f"Multiple evidence signals: {c.get('multiple_evidence',0):,}","",f"Structural-only events: {c.get('struct_only',0):,}",f"Reset-only events: {c.get('reset_only',0):,}",f"TD-only events: {c.get('td_only',0):,}","",f"Offensive event mirror: {c.get('team_offense_events',0):,}",f"Defensive event mirror: {c.get('team_defense_events',0):,}",f"Event reconciliation: {'PASS' if ok else 'FAIL'}","","Candidate definition: structural line-to-gain OR offensive TD OR observed chronology-locked next-clean-snap reset to first down.","Diagnostic only. No propagation yet."])
