"""Derive drive-level records from canonical play-by-play.

Drive IDs define source grouping. Analytics possession ownership is conservative:
clean scrimmage evidence first, then non-scrimmage offensive evidence, then
neighbor inference. Event-only source groups are retained but explicitly marked
as non-possession records. Conflicting scrimmage labels are resolved only when a
strict majority and surrounding game evidence support the same two-team matchup.

The actual grouping/ownership logic (`derive_drive`, `derive_partition_drives`,
etc.) lives in `canonical/drive_grouping.py` now, not here -- moved so
`canonical/drive_ownership.py` (and, through it, `canonical/materialize.py`)
can call it without a circular import back through this module, which itself
depends on `canonical/materialize.py` for `canonical_partition_dir`. Every
name below is re-exported unchanged for any existing caller of this module.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Iterable

from cfb_analytics.canonical.drive_grouping import (
    DRIVE_SCHEMA_VERSION,
    derive_drive,
    derive_partition_drives,
)
from cfb_analytics.canonical.materialize import canonical_partition_dir
from cfb_analytics.raw.audit import discover_partitions
from collections import Counter


def derived_drive_partition_dir(root: Path, season: int, season_type: str, week: int) -> Path:
    return root / "derived" / "drives" / f"season={season}" / f"season_type={season_type}" / f"week={week:02d}"


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data); os.replace(tmp, path)


def _sha256(data: bytes) -> str: return hashlib.sha256(data).hexdigest()


def materialize_drive_partition(processed_root,season,season_type,week,refresh=False):
    source_path=canonical_partition_dir(processed_root,season,season_type,week)/"plays.json"
    if not source_path.exists(): raise FileNotFoundError(f"Canonical plays missing: {source_path}")
    target_dir=derived_drive_partition_dir(processed_root,season,season_type,week); target_path=target_dir/"drives.json"; manifest_path=target_dir/"drives.manifest.json"
    source_bytes=source_path.read_bytes(); source_sha=_sha256(source_bytes)
    if not refresh and target_path.exists() and manifest_path.exists():
        m=json.loads(manifest_path.read_text())
        if m.get("canonical_plays_sha256")==source_sha and m.get("drive_schema_version")==DRIVE_SCHEMA_VERSION: return {**m,"status":"REUSED"}
    rows=json.loads(source_bytes); drives,coverage=derive_partition_drives(rows,season,season_type,week); payload=json.dumps(drives,ensure_ascii=False,separators=(",", ":")).encode()
    m={"entity":"drives","layer":"derived","season":season,"season_type":season_type,"week":week,"drive_count":len(drives),"canonical_play_count":len(rows),**coverage,"review_drive_count":sum(d["driveValidationStatus"]!="PASS" for d in drives),"canonical_plays_sha256":source_sha,"derived_drives_sha256":_sha256(payload),"drive_schema_version":DRIVE_SCHEMA_VERSION,"source":"canonical_play_by_play","format":"json"}
    _atomic_write(target_path,payload); _atomic_write(manifest_path,json.dumps(m,indent=2,sort_keys=True).encode()); return {**m,"status":"WRITTEN"}


def materialize_drive_corpus(raw_root,processed_root,seasons,refresh=False):
    return [materialize_drive_partition(processed_root,s,st,w,refresh) for s in seasons for st,w in discover_partitions(raw_root,s)]


def drive_corpus_audit(raw_root,processed_root,seasons):
    totals=Counter(); issues=Counter(); sources=Counter(); profiles=Counter(); duplicate=0; seen=set(); partitions=0; games=set()
    for s in seasons:
      for st,w in discover_partitions(raw_root,s):
        partitions+=1; dp=derived_drive_partition_dir(processed_root,s,st,w)/"drives.json"; cp=canonical_partition_dir(processed_root,s,st,w)/"plays.json"
        drives=json.loads(dp.read_text()); plays=json.loads(cp.read_text()); totals["drives"]+=len(drives); totals["plays"]+=len(plays); totals["assigned_plays"]+=sum(d.get("playCount",0) for d in drives); totals["missing_drive_id_plays"]+=sum(r.get("driveId") is None for r in plays)
        for d in drives:
          key=(str(d.get("gameId")),str(d.get("driveId"))); duplicate+=key in seen; seen.add(key); games.add(str(d.get("gameId"))); sources[d.get("driveOwnershipSource")]+=1
          if not d.get("isPossessionDrive"): profiles[d.get("nonPossessionProfile")]+=1
          for x in d.get("driveValidationIssues",[]): issues[x]+=1
    checks={"all_drives_unique":duplicate==0,"play_membership_reconciles":totals["assigned_plays"]==totals["plays"]-totals["missing_drive_id_plays"],"no_multiple_ownership_offense_drives":issues["MULTIPLE_OWNERSHIP_OFFENSES"]==0,"no_multiple_ownership_defense_drives":issues["MULTIPLE_OWNERSHIP_DEFENSES"]==0,"no_multiple_drive_number_drives":issues["MULTIPLE_DRIVE_NUMBERS"]==0}
    return {"status":"PASS" if all(checks.values()) else "REVIEW","partitions":partitions,"games_with_drives":len(games),"totals":dict(totals),"issues":dict(issues),"ownership_sources":dict(sources),"non_possession_profiles":dict(profiles),"duplicate_drive_keys":duplicate,"checks":checks}


def concise_drive_audit(r):
    t=r["totals"]; lines=[f"DERIVED DRIVE CORPUS AUDIT: {r['status']}",f"Partitions: {r['partitions']}",f"Games with drives: {r['games_with_drives']:,}",f"Derived source groups: {t.get('drives',0):,}",f"Canonical plays: {t.get('plays',0):,}",f"Assigned to source groups: {t.get('assigned_plays',0):,}",f"Missing driveId plays: {t.get('missing_drive_id_plays',0):,}","","Ownership sources:"]
    for k,v in sorted(r.get("ownership_sources",{}).items(),key=lambda x:-x[1]): lines.append(f"  {str(k):.<40} {v:>7,}")
    lines += ["","Non-possession source groups:"]
    for k,v in sorted(r.get("non_possession_profiles",{}).items(),key=lambda x:-x[1]): lines.append(f"  {str(k):.<40} {v:>7,}")
    lines += ["","Checks:"]
    for k,v in r["checks"].items(): lines.append(f"  {'PASS' if v else 'FAIL'} {k}")
    lines += ["","Remaining validation issues:"]
    if r["issues"]:
      for k,v in sorted(r["issues"].items(),key=lambda x:-x[1]): lines.append(f"  {k:.<40} {v:>7,}")
    else: lines.append("  None")
    return "\n".join(lines)
