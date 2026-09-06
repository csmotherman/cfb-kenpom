"""Sequence-level forensic audit for likely late-half kneel clusters.

Diagnostic only: deliberately conservative and does not mutate canonical data.
"""
from __future__ import annotations
from collections import Counter,defaultdict

def _scrimmage(p):return bool(p.get("isScrimmagePlay")) or p.get("eventCategory")=="SCRIMMAGE"
def _yards(p):return p.get("analyticsYardsGained",p.get("yardsGained"))
def _source(p):return str(p.get("sourcePlayType") or p.get("playType") or "UNKNOWN")
def _sack(p):return p.get("eventSubtype")=="SACK" or _source(p).lower()=="sack"
def _modified(p):return bool(p.get("hasNoPlayContext") or p.get("isModifiedContext") or p.get("isNoPlay"))
def _clock(p):
 for k in ("clockSeconds","secondsRemaining","periodSecondsRemaining"):
  v=p.get(k)
  if isinstance(v,(int,float)):return int(v)
 c=p.get("clock")
 if isinstance(c,dict) and isinstance(c.get("minutes"),(int,float)) and isinstance(c.get("seconds"),(int,float)):return int(c["minutes"])*60+int(c["seconds"])
 if isinstance(c,str) and ":" in c:
  try:m,s=c.split(":",1);return int(m)*60+int(s)
  except ValueError:return None
 return None

def _offense(p):return p.get("offense") or p.get("offenseTeam") or p.get("possessionTeam") or p.get("team")
def _candidate(p):
 y=_yards(p);sec=_clock(p)
 return _scrimmage(p) and isinstance(y,(int,float)) and -3<=y<=-1 and not _sack(p) and not _modified(p) and _source(p) in {"Rush","Rushing Touchdown"} and p.get("period") in (2,4) and sec is not None and sec<=90

def kneel_sequence_forensics(plays):
 games=defaultdict(list)
 for p in plays:games[p.get("gameId")].append(p)
 c=Counter();examples=[]
 for gid,rows in games.items():
  rows=sorted(rows,key=lambda p:(p.get("period") or 0,-(_clock(p) if _clock(p) is not None else 9999),p.get("playSequence") or p.get("sequence") or 0))
  for i,p in enumerate(rows):
   if not _candidate(p):continue
   c["risk_plays"]+=1;off=_offense(p);sec=_clock(p);y=_yards(p)
   prev=rows[i-1] if i else None;nxt=rows[i+1] if i+1<len(rows) else None
   same_next=bool(nxt and _offense(nxt)==off and nxt.get("period")==p.get("period"))
   next_sec=_clock(nxt) if nxt else None
   if same_next:c["same_offense_next_record"]+=1
   if same_next and next_sec is not None and sec is not None and sec-next_sec>=20:c["same_offense_clock_drain_20"]+=1
   # Strong sequence: another small-loss rush by same offense within next 3 records, clock lower.
   repeated=False
   for q in rows[i+1:i+4]:
    qsec=_clock(q);qy=_yards(q)
    if _offense(q)==off and q.get("period")==p.get("period") and _source(q) in {"Rush","Rushing Touchdown"} and isinstance(qy,(int,float)) and -3<=qy<=-1 and qsec is not None and sec is not None and qsec<sec:
     repeated=True;break
   if repeated:c["repeated_small_loss_rush"]+=1
   # Terminal signature: no later offensive scrimmage snap in this period/game.
   later_off_scrim=False
   for q in rows[i+1:]:
    if q.get("period")!=p.get("period"):break
    if _offense(q)==off and _scrimmage(q) and not _modified(q):later_off_scrim=True;break
   if not later_off_scrim:c["terminal_offensive_snap"]+=1
   strong=repeated or (same_next and next_sec is not None and sec-next_sec>=20) or not later_off_scrim
   if strong:c["structural_kneel_signature"]+=1
   if strong and len(examples)<30:examples.append({"gameId":gid,"season":p.get("season"),"week":p.get("week"),"period":p.get("period"),"clock":p.get("clock"),"down":p.get("down"),"distance":p.get("distance"),"yards":y,"offense":off,"playText":p.get("playText"),"repeatedSmallLoss":repeated,"terminal":not later_off_scrim})
 return {"counts":dict(c),"examples":examples}

def concise(r):
 c=r['counts'];return "\n".join(["KNEEL SEQUENCE FORENSICS",f"High-risk small-loss rushes: {c.get('risk_plays',0):,}",f"Same offense on next record: {c.get('same_offense_next_record',0):,}",f"Same offense + >=20s clock drain: {c.get('same_offense_clock_drain_20',0):,}",f"Repeated small-loss rush within next 3 records: {c.get('repeated_small_loss_rush',0):,}",f"Terminal offensive snap of period: {c.get('terminal_offensive_snap',0):,}",f"At least one structural kneel signature: {c.get('structural_kneel_signature',0):,}","","Diagnostic only. These are kneel signatures, not automatic exclusions yet.","Use --json for representative high-confidence sequences."])
