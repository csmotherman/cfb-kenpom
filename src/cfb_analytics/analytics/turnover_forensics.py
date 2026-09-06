"""Turnover v2 forensics.

Diagnostic possession-level turnover study. Plays are indexed once by
(gameId, driveId). The audit distinguishes true giveaway signals from return
records and retained fumbles, and reports record-combination signatures before
we lock production turnover rules.
"""
from __future__ import annotations
from collections import Counter, defaultdict

VERSION="turnover-forensics-v2"
INT_DIRECT={"INTERCEPTION"}
INT_RETURN={"INTERCEPTION_RETURN","INTERCEPTION_RETURN_TD"}
FUMBLE_LOST={"FUMBLE_RECOVERY_OPPONENT","FUMBLE_RETURN_TD"}
FUMBLE_OWN={"FUMBLE_RECOVERY_OWN"}
TURNOVER_SUBTYPES=INT_DIRECT|INT_RETURN|FUMBLE_LOST|FUMBLE_OWN|{"FUMBLE","DEFENSIVE_TWO_POINT"}

def _valid_possession(d):
 return d.get("isPossessionDrive") is True and d.get("driveValidationStatus")=="PASS" and d.get("offense") and d.get("defense")

def _key(game_id,drive_id):return (str(game_id),drive_id)

def build_play_index(plays):
 index=defaultdict(list)
 for p in plays:index[_key(p.get("gameId"),p.get("driveId"))].append(p)
 return index

def _drive_plays(drive,play_index):
 did=drive.get("sourceDriveId",drive.get("driveId"))
 return play_index.get(_key(drive.get("gameId"),did),())

def _signal_counts(ps):
 subs=[p.get("eventSubtype") for p in ps]
 return {
  "int_direct":sum(s in INT_DIRECT for s in subs),
  "int_return":sum(s in INT_RETURN for s in subs),
  "fumble_lost":sum(s in FUMBLE_LOST for s in subs),
  "fumble_own":sum(s in FUMBLE_OWN for s in subs),
  "fumble_base":sum(s=="FUMBLE" for s in subs),
  "turn_records":sum(bool(p.get("isTurnover")) for p in ps),
  "no_play":any(p.get("hasNoPlayContext") for p in ps),
 }

def turnover_signature(ps):
 subs=sorted({str(p.get("eventSubtype")) for p in ps if p.get("eventSubtype") in TURNOVER_SUBTYPES})
 return "+".join(subs) if subs else "NONE"

def classify_drive_turnover_from_plays(ps):
 s=_signal_counts(ps)
 has_int=s["int_direct"] or s["int_return"]
 has_flost=s["fumble_lost"]
 if s["no_play"] and (has_int or has_flost):return "MODIFIED_CONTEXT_REVIEW"
 if has_int and has_flost:return "MULTIPLE_TURNOVER_SIGNALS"
 if s["int_direct"]:return "INTERCEPTION_DIRECT"
 if s["int_return"]:return "INTERCEPTION_RETURN_ONLY"
 if has_flost:return "FUMBLE_LOST"
 if s["fumble_own"]:return "FUMBLE_RECOVERED_OWN"
 if s["fumble_base"]:return "FUMBLE_WITHOUT_RECOVERY_SIGNAL"
 if s["turn_records"]:return "OTHER_TURNOVER_RECORD"
 return "NO_EXPLICIT_TURNOVER"

def classify_drive_turnover(drive,plays_or_index):
 index=plays_or_index if isinstance(plays_or_index,dict) else build_play_index(plays_or_index)
 return classify_drive_turnover_from_plays(_drive_plays(drive,index))

def turnover_forensics(drives,plays):
 valid=[d for d in drives if _valid_possession(d)];play_index=build_play_index(plays);outcomes=Counter();raw=Counter();signatures=Counter();alignment=Counter();examples=[]
 for d in valid:
  ps=_drive_plays(d,play_index);out=classify_drive_turnover_from_plays(ps);outcomes[out]+=1
  sig=turnover_signature(ps)
  if sig!="NONE":signatures[sig]+=1
  for p in ps:
   if p.get("isTurnover"):
    raw[str(p.get("eventSubtype"))]+=1
    # Identity diagnostic: does the turnover-category record preserve the drive's
    # offense/defense labels or appear with teams reversed/other?
    po,pd=p.get("offense"),p.get("defense")
    if po==d.get("offense") and pd==d.get("defense"):alignment["SAME_AS_DRIVE"]+=1
    elif po==d.get("defense") and pd==d.get("offense"):alignment["REVERSED_FROM_DRIVE"]+=1
    else:alignment["OTHER_OR_MISSING"]+=1
  if out in {"INTERCEPTION_RETURN_ONLY","FUMBLE_WITHOUT_RECOVERY_SIGNAL","MODIFIED_CONTEXT_REVIEW","MULTIPLE_TURNOVER_SIGNALS","OTHER_TURNOVER_RECORD"} and len(examples)<30:
   examples.append({"gameId":d.get("gameId"),"driveId":d.get("driveId"),"offense":d.get("offense"),"defense":d.get("defense"),"outcome":out,"signature":sig,"plays":[{"playType":p.get("playType"),"eventSubtype":p.get("eventSubtype"),"offense":p.get("offense"),"defense":p.get("defense"),"playText":p.get("playText")} for p in ps if p.get("isTurnover") or p.get("hasFumbleContext") or p.get("hasInterceptionContext")]})
 clean=outcomes["INTERCEPTION_DIRECT"]+outcomes["FUMBLE_LOST"]
 likely=clean+outcomes["INTERCEPTION_RETURN_ONLY"]
 return {"version":VERSION,"validated_possessions":len(valid),"clean_giveaways":clean,"likely_giveaways_including_return_only":likely,"clean_giveaway_rate":clean/len(valid) if valid else None,"likely_giveaway_rate":likely/len(valid) if valid else None,"drive_outcomes":dict(outcomes),"turnover_records_by_subtype":dict(raw),"top_turnover_signatures":dict(signatures.most_common(20)),"turnover_record_team_alignment":dict(alignment),"review_examples":examples}

def concise_turnover_forensics(r):
 lines=["TURNOVER POSSESSION FORENSICS (v2)",f"Validated possession drives: {r['validated_possessions']:,}",f"Clean giveaways (direct INT + lost fumble): {r['clean_giveaways']:,} ({r['clean_giveaway_rate']:.2%})" if r['clean_giveaway_rate'] is not None else "Clean giveaways: 0",f"Likely giveaways including INT-return-only: {r['likely_giveaways_including_return_only']:,} ({r['likely_giveaway_rate']:.2%})" if r['likely_giveaway_rate'] is not None else "Likely giveaways: 0","","Drive-level outcomes:"]
 for k,v in sorted(r['drive_outcomes'].items(),key=lambda x:-x[1]):lines.append(f"{k:.<42} {v:>8,}")
 lines.append("\nTop turnover record combinations:")
 for k,v in r['top_turnover_signatures'].items():lines.append(f"{k:.<52} {v:>8,}")
 lines.append("\nTurnover-record team alignment vs possession drive:")
 for k,v in sorted(r['turnover_record_team_alignment'].items(),key=lambda x:-x[1]):lines.append(f"{k:.<42} {v:>8,}")
 lines.append("\nTurnover-category records (diagnostic; not giveaway counts):")
 for k,v in sorted(r['turnover_records_by_subtype'].items(),key=lambda x:-x[1]):lines.append(f"{k:.<42} {v:>8,}")
 lines += ["","Diagnostic only. INT-return-only possessions are reported as likely, not yet promoted to production giveaways.","No data is modified. Use --json to inspect examples."]
 return "\n".join(lines)
