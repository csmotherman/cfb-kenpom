"""Conservative confidence audit for likely kneel plays.

Requires combinations of structural signals. Diagnostic only.
"""
from __future__ import annotations
from collections import Counter,defaultdict
from cfb_analytics.analytics.kneel_sequence_forensics import _candidate,_clock,_offense,_scrimmage,_modified,_source,_yards

def kneel_confidence_audit(plays):
 games=defaultdict(list)
 for p in plays: games[p.get("gameId")].append(p)
 c=Counter();examples={"high":[],"medium":[],"terminal_only":[]}
 for gid,rows in games.items():
  rows=sorted(rows,key=lambda p:(p.get("period") or 0,-(_clock(p) if _clock(p) is not None else 9999),p.get("playSequence") or p.get("sequence") or 0))
  for i,p in enumerate(rows):
   if not _candidate(p): continue
   c["risk_plays"]+=1;off=_offense(p);sec=_clock(p)
   nxt=rows[i+1] if i+1<len(rows) else None
   same_next=bool(nxt and _offense(nxt)==off and nxt.get("period")==p.get("period"))
   nsec=_clock(nxt) if nxt else None
   drain=bool(same_next and nsec is not None and sec is not None and sec-nsec>=20)
   repeated=False
   for q in rows[i+1:i+4]:
    qsec=_clock(q);qy=_yards(q)
    if _offense(q)==off and q.get("period")==p.get("period") and _source(q) in {"Rush","Rushing Touchdown"} and isinstance(qy,(int,float)) and -3<=qy<=-1 and qsec is not None and qsec<sec:
     repeated=True;break
   later=False
   for q in rows[i+1:]:
    if q.get("period")!=p.get("period"):break
    if _offense(q)==off and _scrimmage(q) and not _modified(q):later=True;break
   terminal=not later
   # High confidence requires repeated small-loss rush AND clock drain/same-possession evidence.
   high=repeated and drain
   # Medium requires repeated sequence OR clock drain, but not merely terminal status.
   medium=(repeated or drain) and not high
   terminal_only=terminal and not repeated and not drain
   if high:c["high_confidence"]+=1;bucket="high"
   elif medium:c["medium_confidence"]+=1;bucket="medium"
   elif terminal_only:c["terminal_only"]+=1;bucket="terminal_only"
   else:c["low_no_sequence_support"]+=1;bucket=None
   if terminal:c["terminal_total"]+=1
   if repeated:c["repeated_total"]+=1
   if drain:c["drain_total"]+=1
   if bucket and len(examples[bucket])<20:examples[bucket].append({"gameId":gid,"season":p.get("season"),"week":p.get("week"),"period":p.get("period"),"clock":p.get("clock"),"down":p.get("down"),"distance":p.get("distance"),"yards":_yards(p),"offense":off,"playText":p.get("playText"),"repeated":repeated,"clockDrain20":drain,"terminal":terminal})
 return {"counts":dict(c),"examples":examples}

def concise(r):
 c=r['counts'];return "\n".join(["KNEEL CONFIDENCE AUDIT",f"High-risk plays: {c.get('risk_plays',0):,}",f"HIGH confidence (repeat + >=20s drain): {c.get('high_confidence',0):,}",f"MEDIUM confidence (repeat OR drain): {c.get('medium_confidence',0):,}",f"Terminal-only (not enough to exclude): {c.get('terminal_only',0):,}",f"Low/no sequence support: {c.get('low_no_sequence_support',0):,}","",f"Repeated-small-loss signal total: {c.get('repeated_total',0):,}",f">=20s same-offense drain total: {c.get('drain_total',0):,}",f"Terminal-snap signal total: {c.get('terminal_total',0):,}","","Recommended production exclusion candidate is HIGH confidence only.","MEDIUM and terminal-only remain TFL candidates until stronger evidence exists.","Use --json for examples."])
