"""Deterministic explosiveness metrics for canonical offensive plays.

v1 deliberately separates two concepts:
* explosive-play rate: frequency of big gains (rush >=10, pass >=20)
* yards per successful play: magnitude on plays that satisfy Success Rate v1

Only clean offensive scrimmage plays with usable analytics yardage are eligible.
Modified/no-play contexts are excluded rather than guessed.
"""
from __future__ import annotations
import json
from collections import Counter, defaultdict
from pathlib import Path
from cfb_analytics.raw.audit import discover_partitions
from cfb_analytics.canonical.materialize import canonical_partition_dir
from cfb_analytics.analytics.success import classify_success

EXPLOSIVENESS_VERSION="explosiveness-v1"
RUSH_EXPLOSIVE_YARDS=10
PASS_EXPLOSIVE_YARDS=20

def _family(play):
 subtype=str(play.get("eventSubtype") or "").lower()
 if "rush" in subtype: return "RUSH"
 if any(x in subtype for x in ("pass","sack")): return "PASS"
 return None

def classify_explosive(play):
 if not play.get("isScrimmagePlay") or not play.get("isOffensivePlay"): return None
 if play.get("hasStateTransitionModifier") or play.get("hasNoPlayContext"): return None
 yards=play.get("analyticsYardsGained")
 if not isinstance(yards,(int,float)) or isinstance(yards,bool): return None
 family=_family(play)
 if family=="RUSH": return yards>=RUSH_EXPLOSIVE_YARDS
 if family=="PASS": return yards>=PASS_EXPLOSIVE_YARDS
 return None

def explosiveness_audit(raw_root:Path,processed_root:Path,seasons):
 c=Counter(); by_family=defaultdict(Counter); by_season=defaultdict(Counter); total=0
 for season in seasons:
  for st,w in discover_partitions(raw_root,season):
   p=canonical_partition_dir(processed_root,season,st,w)/"plays.json"
   for play in json.loads(p.read_text()):
    total+=1
    ex=classify_explosive(play)
    if ex is not None:
     fam=_family(play); c["eligible"]+=1; c["explosive" if ex else "nonexplosive"]+=1; by_family[fam]["eligible"]+=1; by_family[fam]["explosive" if ex else "nonexplosive"]+=1; by_season[season]["eligible"]+=1; by_season[season]["explosive" if ex else "nonexplosive"]+=1
    success=classify_success(play)
    if success:
     yards=play.get("analyticsYardsGained")
     c["successful_plays"]+=1; c["successful_yards"]+=yards
     fam=_family(play)
     if fam: by_family[fam]["successful_plays"]+=1; by_family[fam]["successful_yards"]+=yards
 return {"plays_scanned":total,"eligible":c["eligible"],"explosive":c["explosive"],"explosive_rate":c["explosive"]/c["eligible"] if c["eligible"] else None,"successful_plays":c["successful_plays"],"successful_yards":c["successful_yards"],"yards_per_successful_play":c["successful_yards"]/c["successful_plays"] if c["successful_plays"] else None,"by_family":{k:dict(v) for k,v in sorted(by_family.items())},"by_season":{str(k):dict(v) for k,v in sorted(by_season.items())},"version":EXPLOSIVENESS_VERSION}

def concise_explosiveness_audit(r):
 lines=["CANONICAL EXPLOSIVENESS AUDIT (v1)",f"Plays scanned: {r['plays_scanned']:,}",f"Explosive-eligible rush/pass plays: {r['eligible']:,}",f"Explosive plays: {r['explosive']:,}",f"Explosive-play rate: {r['explosive_rate']:.2%}" if r['explosive_rate'] is not None else "Explosive-play rate: N/A",f"Successful plays: {r['successful_plays']:,}",f"Yards on successful plays: {r['successful_yards']:,.0f}",f"Yards per successful play: {r['yards_per_successful_play']:.2f}" if r['yards_per_successful_play'] is not None else "Yards per successful play: N/A","","By play family:"]
 for fam,c in r['by_family'].items():
  rate=c.get('explosive',0)/c.get('eligible',1); yps=c.get('successful_yards',0)/c.get('successful_plays',1)
  lines.append(f"{fam}: explosive {c.get('explosive',0):,}/{c.get('eligible',0):,} = {rate:.2%}; successful-play YPP = {yps:.2f}")
 lines += ["",f"Definition: rush >= {RUSH_EXPLOSIVE_YARDS} yards; pass >= {PASS_EXPLOSIVE_YARDS} yards.","Yards per successful play uses the locked Success Rate v1 eligibility/classification.","Modified/no-play contexts are excluded. No data is modified."]
 return "\n".join(lines)
