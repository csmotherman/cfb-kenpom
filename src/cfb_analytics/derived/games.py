"""Derive one analytics row per team per game from validated possession drives."""
from __future__ import annotations
import hashlib,json,os
from collections import Counter,defaultdict
from pathlib import Path
from typing import Any
from cfb_analytics.raw.audit import discover_partitions
from cfb_analytics.canonical.materialize import canonical_partition_dir
from cfb_analytics.derived.drives import derived_drive_partition_dir
from cfb_analytics.analytics.success import classify_success,SUCCESS_VERSION
from cfb_analytics.analytics.explosiveness import classify_explosive,EXPLOSIVENESS_VERSION
from cfb_analytics.analytics.finishing_drives import team_finishing_metrics,FINISHING_DRIVES_VERSION
from cfb_analytics.analytics.field_position import team_field_position_metrics,FIELD_POSITION_VERSION
from cfb_analytics.analytics.turnovers import team_turnover_metrics,TURNOVERS_VERSION
from cfb_analytics.analytics.tfl import team_tfl_metrics,TFL_VERSION
GAME_SCHEMA_VERSION="team-game-v7-tfl"
def derived_game_partition_dir(root:Path,season:int,season_type:str,week:int)->Path:return root/"derived"/"games"/f"season={season}"/f"season_type={season_type}"/f"week={week:02d}"
def _atomic(path:Path,data:bytes):path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix(path.suffix+".tmp");tmp.write_bytes(data);os.replace(tmp,path)
def _sha(b:bytes)->str:return hashlib.sha256(b).hexdigest()
def _num(v:Any)->bool:return isinstance(v,(int,float)) and not isinstance(v,bool)
def _rate(n,d):return n/d if d else None
def _family(p):
 s=str(p.get("eventSubtype") or "").lower()
 if "rush" in s:return "rush"
 if any(x in s for x in ("pass","sack")):return "pass"
 return None
def _metric_counts(plays):
 c=Counter()
 for p in plays:
  fam=_family(p);success=classify_success(p)
  if success is not None:
   c["successEligible"]+=1;c["successful"]+=int(success);d=p.get("down")
   if fam:c[f"{fam}SuccessEligible"]+=1;c[f"{fam}Successful"]+=int(success)
   if d in (1,2,3,4):c[f"down{d}SuccessEligible"]+=1;c[f"down{d}Successful"]+=int(success)
   if success and _num(p.get("analyticsYardsGained")):
    y=p["analyticsYardsGained"];c["successfulYards"]+=y
    if fam:c[f"{fam}SuccessfulYards"]+=y
  explosive=classify_explosive(p)
  if explosive is not None:
   c["explosiveEligible"]+=1;c["explosive"]+=int(explosive)
   if fam:c[f"{fam}ExplosiveEligible"]+=1;c[f"{fam}Explosive"]+=int(explosive)
 return c
def _metric_fields(off,deff):
 oc,dc=_metric_counts(off),_metric_counts(deff);out={"successDefinitionVersion":SUCCESS_VERSION,"explosivenessDefinitionVersion":EXPLOSIVENESS_VERSION}
 for suffix,c in (("",oc),("Allowed",dc)):
  e=c["successEligible"];s=c["successful"];out[f"successEligiblePlays{suffix}"]=e;out[f"successfulPlays{suffix}"]=s;out[f"successRate{suffix}"]=_rate(s,e);out[f"successfulPlayYards{suffix}"]=c["successfulYards"];out[f"yardsPerSuccessfulPlay{suffix}"]=_rate(c["successfulYards"],s)
  ee=c["explosiveEligible"];ex=c["explosive"];out[f"explosiveEligiblePlays{suffix}"]=ee;out[f"explosivePlays{suffix}"]=ex;out[f"explosivePlayRate{suffix}"]=_rate(ex,ee)
  for fam in ("rush","pass"):
   e=c[f"{fam}SuccessEligible"];s=c[f"{fam}Successful"];out[f"{fam}SuccessEligiblePlays{suffix}"]=e;out[f"{fam}SuccessfulPlays{suffix}"]=s;out[f"{fam}SuccessRate{suffix}"]=_rate(s,e);out[f"{fam}SuccessfulPlayYards{suffix}"]=c[f"{fam}SuccessfulYards"];out[f"{fam}YardsPerSuccessfulPlay{suffix}"]=_rate(c[f"{fam}SuccessfulYards"],s);ee=c[f"{fam}ExplosiveEligible"];ex=c[f"{fam}Explosive"];out[f"{fam}ExplosiveEligiblePlays{suffix}"]=ee;out[f"{fam}ExplosivePlays{suffix}"]=ex;out[f"{fam}ExplosivePlayRate{suffix}"]=_rate(ex,ee)
  for d in (1,2,3,4):
   e=c[f"down{d}SuccessEligible"];s=c[f"down{d}Successful"];out[f"down{d}SuccessEligiblePlays{suffix}"]=e;out[f"down{d}SuccessfulPlays{suffix}"]=s;out[f"down{d}SuccessRate{suffix}"]=_rate(s,e)
 return out
def _allowed_finishing(fields):
 mapping={"scoringOpportunities":"scoringOpportunitiesAllowed","opportunityTouchdowns":"opportunityTouchdownsAllowed","opportunityFieldGoals":"opportunityFieldGoalsAllowed","emptyOpportunities":"emptyOpportunitiesForced","otherScoringOpportunities":"otherScoringOpportunitiesAllowed","resolvedPointOpportunities":"resolvedPointOpportunitiesAllowed","unresolvedPointOpportunities":"unresolvedPointOpportunitiesAllowed","opportunityPoints":"opportunityPointsAllowed","pointsPerOpportunity":"pointsPerOpportunityAllowed","touchdownRatePerOpportunity":"touchdownRatePerOpportunityAllowed","fieldGoalRatePerOpportunity":"fieldGoalRatePerOpportunityAllowed","emptyRatePerOpportunity":"emptyRatePerOpportunityAllowed"};return {dst:fields.get(src) for src,dst in mapping.items()}
def derive_team_games(plays,drives,season,season_type,week):
 by_game=defaultdict(list);play_games=defaultdict(list)
 for d in drives:by_game[str(d.get("gameId"))].append(d)
 for p in plays:play_games[str(p.get("gameId"))].append(p)
 out=[]
 for gid,ds in by_game.items():
  gp=play_games.get(gid,[]);teams={x for d in ds for x in (d.get("offense"),d.get("defense")) if x}|{x for p in gp for x in (p.get("offense"),p.get("defense")) if x};valid=[d for d in ds if d.get("isPossessionDrive") is True and d.get("driveValidationStatus")=="PASS" and d.get("offense") and d.get("defense")];review=[d for d in ds if d.get("isPossessionDrive") is True and d.get("driveValidationStatus")!="PASS"];finishing={team:team_finishing_metrics(team,ds,gp) for team in teams};fieldpos={team:team_field_position_metrics(team,ds) for team in teams};turnovers={team:team_turnover_metrics(team,ds,gp) for team in teams};tfl={team:team_tfl_metrics(team,gp) for team in teams}
  for team in sorted(teams):
   opps=[x for d in valid for x in (d.get("offense"),d.get("defense")) if x and x!=team];opponent=Counter(opps).most_common(1)[0][0] if opps else None;off=[d for d in valid if d.get("offense")==team];deff=[d for d in valid if d.get("defense")==team];oy=sum(d.get("analyticsYardsGained",0) for d in off if _num(d.get("analyticsYardsGained")));dy=sum(d.get("analyticsYardsGained",0) for d in deff if _num(d.get("analyticsYardsGained")))
   row={"season":season,"seasonType":season_type,"week":week,"gameId":gid,"team":team,"opponent":opponent,"validatedPossessions":len(off),"validatedDefensivePossessions":len(deff),"offensivePlays":sum(d.get("offensivePlayCount",0) for d in off),"defensivePlays":sum(d.get("offensivePlayCount",0) for d in deff),"offensiveYards":oy,"defensiveYardsAllowed":dy,"yardsPerPossession":_rate(oy,len(off)),"yardsAllowedPerPossession":_rate(dy,len(deff)),"reviewPossessionGroups":sum(team in {d.get("offense"),d.get("defense")} for d in review),"gameValidationStatus":"PASS" if len(teams)==2 else "REVIEW","gameValidationIssues":[] if len(teams)==2 else ["TEAM_IDENTITY_COUNT_NOT_TWO"],"gameSchemaVersion":GAME_SCHEMA_VERSION}
   row.update(_metric_fields([p for p in gp if p.get("offense")==team],[p for p in gp if p.get("defense")==team]));row.update(finishing[team]);row["finishingDrivesDefinitionVersion"]=FINISHING_DRIVES_VERSION;row.update(fieldpos[team]);row["fieldPositionDefinitionVersion"]=FIELD_POSITION_VERSION;row.update(turnovers[team]);row["turnoversDefinitionVersion"]=TURNOVERS_VERSION;row.update(tfl[team]);row["tflDefinitionVersion"]=TFL_VERSION
   if opponent in finishing:row.update(_allowed_finishing(finishing[opponent]))
   out.append(row)
 return out
def materialize_game_partition(processed_root,season,season_type,week,refresh=False):
 cp=canonical_partition_dir(processed_root,season,season_type,week)/"plays.json";dp=derived_drive_partition_dir(processed_root,season,season_type,week)/"drives.json"
 if not cp.exists() or not dp.exists():raise FileNotFoundError("Canonical plays and derived drives must exist first")
 cb,db=cp.read_bytes(),dp.read_bytes();target=derived_game_partition_dir(processed_root,season,season_type,week);path=target/"team_games.json";manifest=target/"team_games.manifest.json";sig=_sha(cb+db)
 if not refresh and path.exists() and manifest.exists():
  m=json.loads(manifest.read_text())
  if m.get("input_sha256")==sig and m.get("game_schema_version")==GAME_SCHEMA_VERSION:return {**m,"status":"REUSED"}
 rows=derive_team_games(json.loads(cb),json.loads(db),season,season_type,week);payload=json.dumps(rows,ensure_ascii=False,separators=(",",":")).encode();m={"entity":"team_games","layer":"derived","season":season,"season_type":season_type,"week":week,"record_count":len(rows),"game_count":len({r['gameId'] for r in rows}),"review_record_count":sum(r['gameValidationStatus']!='PASS' for r in rows),"input_sha256":sig,"output_sha256":_sha(payload),"game_schema_version":GAME_SCHEMA_VERSION};_atomic(path,payload);_atomic(manifest,json.dumps(m,indent=2,sort_keys=True).encode());return {**m,"status":"WRITTEN"}
def materialize_game_corpus(raw_root,processed_root,seasons,refresh=False):return [materialize_game_partition(processed_root,s,st,w,refresh) for s in seasons for st,w in discover_partitions(raw_root,s)]
def game_corpus_audit(raw_root,processed_root,seasons):
 records=[]
 for s in seasons:
  for st,w in discover_partitions(raw_root,s):records.extend(json.loads((derived_game_partition_dir(processed_root,s,st,w)/"team_games.json").read_text()))
 by=Counter(r['gameId'] for r in records);checks={"exactly_two_team_rows_per_game":all(n==2 for n in by.values()),"unique_team_game_rows":len({(r['gameId'],r['team']) for r in records})==len(records),"all_team_rows_have_opponent":all(r.get('opponent') for r in records),"success_offense_defense_eligible_reconciles":sum(r.get('successEligiblePlays',0) for r in records)==sum(r.get('successEligiblePlaysAllowed',0) for r in records),"success_offense_defense_successful_reconciles":sum(r.get('successfulPlays',0) for r in records)==sum(r.get('successfulPlaysAllowed',0) for r in records),"explosive_offense_defense_eligible_reconciles":sum(r.get('explosiveEligiblePlays',0) for r in records)==sum(r.get('explosiveEligiblePlaysAllowed',0) for r in records),"explosive_offense_defense_plays_reconcile":sum(r.get('explosivePlays',0) for r in records)==sum(r.get('explosivePlaysAllowed',0) for r in records),"successful_yards_offense_defense_reconcile":sum(r.get('successfulPlayYards',0) for r in records)==sum(r.get('successfulPlayYardsAllowed',0) for r in records),"finishing_opportunities_reconcile":sum(r.get('scoringOpportunities',0) for r in records)==sum(r.get('scoringOpportunitiesAllowed',0) for r in records),"finishing_points_reconcile":sum(r.get('opportunityPoints',0) for r in records)==sum(r.get('opportunityPointsAllowed',0) for r in records),"field_position_possessions_reconcile":sum(r.get('fieldPositionPossessions',0) for r in records)==sum(r.get('fieldPositionPossessionsAllowed',0) for r in records),"field_position_yards_reconcile":sum(r.get('startYardsToGoalTotal',0) for r in records)==sum(r.get('startYardsToGoalTotalAllowed',0) for r in records),"turnover_giveaways_takeaways_reconcile":sum(r.get('giveaways',0) for r in records)==sum(r.get('takeaways',0) for r in records),"turnover_interceptions_reconcile":sum(r.get('interceptionsThrown',0) for r in records)==sum(r.get('interceptionsMade',0) for r in records),"turnover_fumbles_reconcile":sum(r.get('fumblesLost',0) for r in records)==sum(r.get('fumblesRecovered',0) for r in records),"turnover_margin_sums_zero":sum(r.get('turnoverMargin',0) for r in records)==0,"tfl_offense_defense_reconcile":sum(r.get('tacklesForLoss',0) for r in records)==sum(r.get('tacklesForLossAllowed',0) for r in records)}
 return {"status":"PASS" if all(checks.values()) else "REVIEW","team_game_rows":len(records),"games":len(by),"review_rows":sum(r['gameValidationStatus']!='PASS' for r in records),"success_eligible_plays":sum(r.get('successEligiblePlays',0) for r in records),"successful_plays":sum(r.get('successfulPlays',0) for r in records),"explosive_eligible_plays":sum(r.get('explosiveEligiblePlays',0) for r in records),"explosive_plays":sum(r.get('explosivePlays',0) for r in records),"successful_play_yards":sum(r.get('successfulPlayYards',0) for r in records),"scoring_opportunities":sum(r.get('scoringOpportunities',0) for r in records),"opportunity_points":sum(r.get('opportunityPoints',0) for r in records),"unresolved_point_opportunities":sum(r.get('unresolvedPointOpportunities',0) for r in records),"field_position_possessions":sum(r.get('fieldPositionPossessions',0) for r in records),"giveaways":sum(r.get('giveaways',0) for r in records),"takeaways":sum(r.get('takeaways',0) for r in records),"interceptions":sum(r.get('interceptionsThrown',0) for r in records),"fumbles_lost":sum(r.get('fumblesLost',0) for r in records),"turnover_unresolved_possessions":sum(r.get('turnoverUnresolvedPossessions',0) for r in records),"tackles_for_loss":sum(r.get('tacklesForLoss',0) for r in records),"checks":checks}
def concise_game_audit(r):
 lines=[f"DERIVED TEAM-GAME CORPUS AUDIT: {r['status']}",f"Games: {r['games']:,}",f"Team-game rows: {r['team_game_rows']:,}",f"Review rows: {r['review_rows']:,}",f"Success eligible plays: {r['success_eligible_plays']:,}",f"Successful plays: {r['successful_plays']:,}",f"Explosive eligible plays: {r['explosive_eligible_plays']:,}",f"Explosive plays: {r['explosive_plays']:,}",f"Successful-play yards: {r['successful_play_yards']:,.0f}",f"Scoring opportunities: {r['scoring_opportunities']:,}",f"Adjudicated opportunity points: {r['opportunity_points']:,}",f"Unresolved point opportunities: {r['unresolved_point_opportunities']:,}",f"Field-position eligible possessions: {r['field_position_possessions']:,}",f"Giveaways: {r['giveaways']:,}",f"Takeaways: {r['takeaways']:,}",f"Interceptions: {r['interceptions']:,}",f"Fumbles lost: {r['fumbles_lost']:,}",f"Turnover-unresolved possessions: {r['turnover_unresolved_possessions']:,}",f"Tackles for loss: {r['tackles_for_loss']:,}","","Checks:"]+[f"{'PASS' if v else 'FAIL'} {k}" for k,v in r['checks'].items()];return "\n".join(lines)
