"""Corpus-wide audits for canonical play taxonomy and normalization."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Iterable

from cfb_analytics.canonical.play_types import RULES
from cfb_analytics.canonical.plays import normalize_play
from cfb_analytics.raw.audit import discover_partitions, partition_dir


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def play_type_coverage(root: Path, seasons: Iterable[int]) -> dict:
    counts = Counter(); total = 0
    for season in seasons:
        for season_type, week in discover_partitions(root, season):
            d = partition_dir(root, season, season_type, week)
            for play in _load(d / "plays.json"):
                play_type = play.get("playType"); counts[str(play_type)] += 1; total += 1
    observed = set(counts); classified = observed & set(RULES); unclassified = observed - set(RULES)
    return {"total_plays": total,"observed_play_types": len(observed),"classified_play_types": len(classified),"unclassified_play_types": {k: counts[k] for k in sorted(unclassified)},"unused_taxonomy_rules": sorted(set(RULES)-observed),"status": "PASS" if not unclassified else "REVIEW"}


def canonical_play_audit(root: Path, seasons: Iterable[int], examples: int = 5) -> dict:
    total=0; normalized=0; categories=Counter(); subtypes=Counter(); normalized_types=Counter(); failures=Counter(); samples={}
    source_mutations=0; source_field_changes=0; missing_category=0; missing_subtype=0; bad_admin_yards=0; unexpected_zeroing=0
    for season in seasons:
        for season_type, week in discover_partitions(root, season):
            d=partition_dir(root,season,season_type,week)
            for source in _load(d/"plays.json"):
                total+=1; before=dict(source)
                try: canon=normalize_play(source)
                except Exception as exc:
                    failures[type(exc).__name__]+=1
                    if "normalization_failure" not in samples and len(samples)<examples: samples["normalization_failure"]={"season":season,"season_type":season_type,"week":week,"play":before,"error":repr(exc)}
                    continue
                normalized+=1
                if source != before: source_mutations+=1
                for k,v in before.items():
                    if canon.get(k)!=v: source_field_changes+=1; break
                cat=canon.get("eventCategory"); sub=canon.get("eventSubtype")
                categories[str(cat)]+=1; subtypes[str(sub)]+=1
                if not cat: missing_category+=1
                if not sub: missing_subtype+=1
                source_yards=canon.get("sourceYardsGained"); analytics_yards=canon.get("analyticsYardsGained")
                if canon.get("isAdministrative"):
                    if analytics_yards != 0: bad_admin_yards+=1
                    if analytics_yards != source_yards: normalized_types[str(canon.get("sourcePlayType"))]+=1
                elif analytics_yards != source_yards:
                    unexpected_zeroing+=1
                    if "unexpected_zeroing" not in samples: samples["unexpected_zeroing"]={"season":season,"season_type":season_type,"week":week,"play":before,"canonical":canon}
    checks={
        "all_plays_normalized": normalized==total,
        "source_records_not_mutated": source_mutations==0,
        "source_fields_preserved": source_field_changes==0,
        "canonical_category_populated": missing_category==0,
        "canonical_subtype_populated": missing_subtype==0,
        "administrative_yards_zero": bad_admin_yards==0,
        "non_administrative_yards_preserved": unexpected_zeroing==0,
    }
    return {
        "status":"PASS" if all(checks.values()) else "REVIEW","plays_scanned":total,"plays_normalized":normalized,"checks":checks,
        "counts":{"normalization_failures":sum(failures.values()),"source_mutations":source_mutations,"source_field_changes":source_field_changes,"missing_category":missing_category,"missing_subtype":missing_subtype,"bad_administrative_yards":bad_admin_yards,"unexpected_non_administrative_zeroing":unexpected_zeroing},
        "categories":dict(categories),"subtypes":dict(subtypes),"administrative_yard_normalizations_by_type":dict(normalized_types),"failure_types":dict(failures),"examples":samples,
    }


def concise_play_type_coverage(r: dict) -> str:
    lines=[f"CANONICAL PLAY-TYPE COVERAGE: {r['status']}",f"Plays scanned: {r['total_plays']:,}",f"Observed play types: {r['observed_play_types']}",f"Classified play types: {r['classified_play_types']}",f"Unclassified play types: {len(r['unclassified_play_types'])}"]
    if r["unclassified_play_types"]:
        lines += ["","Unclassified source play types:"]
        for name,count in sorted(r["unclassified_play_types"].items(),key=lambda x:-x[1]): lines.append(f"  {count:>8,}  {name}")
    else: lines.append("All observed play types are explicitly classified.")
    return "\n".join(lines)


def concise_canonical_play_audit(r: dict) -> str:
    lines=[f"CANONICAL PLAY NORMALIZATION AUDIT: {r['status']}",f"Plays scanned: {r['plays_scanned']:,}",f"Plays normalized: {r['plays_normalized']:,}","","Checks:"]
    for key,ok in r["checks"].items(): lines.append(f"  {'PASS' if ok else 'FAIL'}  {key}")
    lines += ["","Canonical categories:"]
    for name,count in sorted(r["categories"].items(),key=lambda x:-x[1]): lines.append(f"  {count:>9,}  {name}")
    lines += ["","Administrative records whose source yardage was normalized to 0:"]
    if r["administrative_yard_normalizations_by_type"]:
        for name,count in sorted(r["administrative_yard_normalizations_by_type"].items(),key=lambda x:-x[1]): lines.append(f"  {count:>9,}  {name}")
    else: lines.append("  None")
    c=r["counts"]; lines += ["",f"Normalization failures: {c['normalization_failures']:,}",f"Source mutations: {c['source_mutations']:,}",f"Source-field changes: {c['source_field_changes']:,}",f"Unexpected non-administrative zeroing: {c['unexpected_non_administrative_zeroing']:,}"]
    return "\n".join(lines)
