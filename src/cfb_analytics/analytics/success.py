"""Deterministic success-rate classification for canonical offensive plays.

Definition:
* 1st down: gain >= 50% of distance to gain
* 2nd down: gain >= 70% of distance to gain
* 3rd/4th down: gain >= 100% of distance to gain

Only clean offensive scrimmage plays with usable down/distance/analytics yardage
are eligible. Modified/no-play contexts are excluded rather than guessed.
"""
from __future__ import annotations
import json
from collections import Counter, defaultdict
from pathlib import Path
from cfb_analytics.raw.audit import discover_partitions
from cfb_analytics.canonical.materialize import canonical_partition_dir

SUCCESS_VERSION="success-v1"
THRESHOLDS={1:0.50,2:0.70,3:1.00,4:1.00}

def classify_success(play):
 if not play.get("isScrimmagePlay") or not play.get("isOffensivePlay"): return None
 if play.get("hasStateTransitionModifier") or play.get("hasNoPlayContext"): return None
 down=play.get("down"); distance=play.get("distance"); yards=play.get("analyticsYardsGained")
 if down not in THRESHOLDS: return None
 if not isinstance(distance,(int,float)) or isinstance(distance,bool) or distance<=0: return None
 if not isinstance(yards,(int,float)) or isinstance(yards,bool): return None
 return yards >= distance*THRESHOLDS[down]

def annotate_success(play):
 out=dict(play); result=classify_success(play)
 out["successEligible"]=result is not None; out["isSuccessfulPlay"]=result; out["successDefinitionVersion"]=SUCCESS_VERSION
 return out

def success_audit(raw_root:Path,processed_root:Path,seasons):
 counts=Counter(); by_down=defaultdict(Counter); by_season=defaultdict(Counter); total=0
 for season in seasons:
  for st,w in discover_partitions(raw_root,season):
   p=canonical_partition_dir(processed_root,season,st,w)/"plays.json"
   for play in json.loads(p.read_text()):
    total+=1; result=classify_success(play)
    if result is None:
     if play.get("isScrimmagePlay") and play.get("isOffensivePlay"): counts["ineligible_offensive_scrimmage"]+=1
     continue
    counts["eligible"]+=1; counts["successful" if result else "unsuccessful"]+=1; by_down[play.get("down")]["eligible"]+=1; by_down[play.get("down")]["successful" if result else "unsuccessful"]+=1; by_season[season]["eligible"]+=1; by_season[season]["successful" if result else "unsuccessful"]+=1
 eligible=counts["eligible"]
 return {"plays_scanned":total,"eligible":eligible,"successful":counts["successful"],"unsuccessful":counts["unsuccessful"],"success_rate":counts["successful"]/eligible if eligible else None,"ineligible_offensive_scrimmage":counts["ineligible_offensive_scrimmage"],"by_down":{str(k):dict(v) for k,v in sorted(by_down.items())},"by_season":{str(k):dict(v) for k,v in sorted(by_season.items())},"version":SUCCESS_VERSION}
def concise_success_audit(r):
 lines=["CANONICAL SUCCESS-RATE AUDIT",f"Plays scanned: {r['plays_scanned']:,}",f"Eligible offensive plays: {r['eligible']:,}",f"Excluded offensive scrimmage plays: {r['ineligible_offensive_scrimmage']:,}",f"Successful: {r['successful']:,}",f"Unsuccessful: {r['unsuccessful']:,}",f"Overall success rate: {r['success_rate']:.2%}" if r['success_rate'] is not None else "Overall success rate: N/A","","By down:"]
 for d,c in r['by_down'].items(): lines.append(f"{d}: {c.get('successful',0):,}/{c.get('eligible',0):,} = {c.get('successful',0)/c.get('eligible',1):.2%}")
 lines += ["","Definition: 1st=50%, 2nd=70%, 3rd/4th=100% of distance to gain.","Modified/no-play contexts are excluded."]
 return "\n".join(lines)
