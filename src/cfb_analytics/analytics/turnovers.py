"""Production Turnovers v1.

Evidence rules locked from turnover forensics:
- direct interceptions and interception-return-only possessions are giveaways
- opponent fumble recoveries / fumble return TDs are fumbles lost
- own fumble recoveries are not giveaways
- nullified/modified turnover contexts are excluded
- unresolved fumbles and miscellaneous turnover records remain unresolved
"""
from __future__ import annotations
from collections import Counter
from cfb_analytics.analytics.turnover_forensics import build_play_index,_drive_plays,classify_drive_turnover_from_plays

TURNOVERS_VERSION="turnovers-v1"
GIVEAWAY_INT={"INTERCEPTION_DIRECT","INTERCEPTION_RETURN_ONLY"}
GIVEAWAY_FUMBLE={"FUMBLE_LOST"}
UNRESOLVED={"FUMBLE_WITHOUT_RECOVERY_SIGNAL","OTHER_TURNOVER_RECORD","MULTIPLE_TURNOVER_SIGNALS"}
EXCLUDED={"MODIFIED_CONTEXT_REVIEW"}

def classify_possession_turnover(drive,play_index):
 outcome=classify_drive_turnover_from_plays(_drive_plays(drive,play_index))
 if outcome in GIVEAWAY_INT:return {"turnoverOutcome":"INTERCEPTION","giveaway":1,"interceptionThrown":1,"fumbleLost":0,"turnoverResolved":True,"turnoverSource":outcome}
 if outcome in GIVEAWAY_FUMBLE:return {"turnoverOutcome":"FUMBLE_LOST","giveaway":1,"interceptionThrown":0,"fumbleLost":1,"turnoverResolved":True,"turnoverSource":outcome}
 if outcome=="FUMBLE_RECOVERED_OWN" or outcome=="NO_EXPLICIT_TURNOVER":return {"turnoverOutcome":"NO_GIVEAWAY","giveaway":0,"interceptionThrown":0,"fumbleLost":0,"turnoverResolved":True,"turnoverSource":outcome}
 if outcome in EXCLUDED:return {"turnoverOutcome":"EXCLUDED_NULLIFIED","giveaway":0,"interceptionThrown":0,"fumbleLost":0,"turnoverResolved":False,"turnoverSource":outcome}
 return {"turnoverOutcome":"UNRESOLVED","giveaway":0,"interceptionThrown":0,"fumbleLost":0,"turnoverResolved":False,"turnoverSource":outcome}

def team_turnover_metrics(team,drives,plays):
 index=build_play_index(plays);off=[d for d in drives if d.get("offense")==team and d.get("isPossessionDrive") is True and d.get("driveValidationStatus")=="PASS"];deff=[d for d in drives if d.get("defense")==team and d.get("isPossessionDrive") is True and d.get("driveValidationStatus")=="PASS"]
 def agg(ds):
  c=Counter()
  for d in ds:
   r=classify_possession_turnover(d,index);c["giveaways"]+=r["giveaway"];c["interceptions"]+=r["interceptionThrown"];c["fumbles"]+=r["fumbleLost"];c["resolved"]+=int(r["turnoverResolved"]);c["unresolved"]+=int(not r["turnoverResolved"])
  return c
 o=agg(off);a=agg(deff)
 return {"giveaways":o["giveaways"],"interceptionsThrown":o["interceptions"],"fumblesLost":o["fumbles"],"turnoverResolvedPossessions":o["resolved"],"turnoverUnresolvedPossessions":o["unresolved"],"takeaways":a["giveaways"],"interceptionsMade":a["interceptions"],"fumblesRecovered":a["fumbles"],"takeawayResolvedPossessions":a["resolved"],"takeawayUnresolvedPossessions":a["unresolved"],"turnoverMargin":a["giveaways"]-o["giveaways"],"turnoversDefinitionVersion":TURNOVERS_VERSION}

def turnover_corpus_audit(drives,plays):
 teams={d.get("offense") for d in drives if d.get("offense")};tot=Counter()
 for team in teams:
  m=team_turnover_metrics(team,drives,plays)
  for k in ("giveaways","interceptionsThrown","fumblesLost","takeaways","interceptionsMade","fumblesRecovered","turnoverUnresolvedPossessions","takeawayUnresolvedPossessions"):tot[k]+=m[k]
 return {"giveaways":tot["giveaways"],"interceptions":tot["interceptionsThrown"],"fumbles_lost":tot["fumblesLost"],"takeaways":tot["takeaways"],"interceptions_made":tot["interceptionsMade"],"fumbles_recovered":tot["fumblesRecovered"],"unresolved_offense":tot["turnoverUnresolvedPossessions"],"unresolved_defense":tot["takeawayUnresolvedPossessions"],"reconciles":tot["giveaways"]==tot["takeaways"] and tot["interceptionsThrown"]==tot["interceptionsMade"] and tot["fumblesLost"]==tot["fumblesRecovered"]}
