"""Validate and export the compiled site datasets for Next.js.

All inputs are validated before any published file is replaced. Metadata is
content-versioned, so unchanged runs do not create meaningless daily commits.
"""
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
from compile_site_data import read_js_assignment
from validate_site_data import require, validate_season

WEB_DATA = REPO / "web/public/data"


def encode(value):
    return json.dumps(value, separators=(",", ":"), allow_nan=False)


def atomic_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    os.replace(tmp, path)


def main():
    site = REPO / "site"
    datasets = {}
    for kind, filename, prefix in [("rankings", "data.js", "CFB"), ("advanced", "advanced-data.js", "CFF_ADV")]:
        values = {key: read_js_assignment(site / filename, f"{prefix}_{key}") for key in ("YEARS", "WEEKS", "WEEK_LABELS", "DATA")}
        require(all(v is not None for v in values.values()), f"Missing required assignments in {filename}")
        require(values["YEARS"] == sorted(set(values["YEARS"])) and bool(values["YEARS"]), "Invalid season catalog")
        datasets[kind] = values
    years = datasets["rankings"]["YEARS"]
    require(years == datasets["advanced"]["YEARS"], "Season catalogs differ")
    outputs = {}
    summaries = {}
    search = {}
    for year in years:
        key = str(year)
        payloads = {}
        for kind, data in datasets.items():
            payloads[kind] = {"weeks": data["WEEKS"][key], "weekLabels": data["WEEK_LABELS"].get(key, {}), "byWeek": data["DATA"][key]}
        previous_path = WEB_DATA / "rankings" / f"{key}.json"
        previous = json.loads(previous_path.read_text()) if previous_path.exists() else None
        summaries[key] = validate_season(payloads["rankings"], payloads["advanced"], previous=previous)
        for kind, payload in payloads.items():
            outputs[f"{kind}/{key}.json"] = encode(payload)
        latest = payloads["rankings"]
        for row in latest["byWeek"][str(latest["weeks"][-1])]:
            search[row["slug"]] = {k: row[k] for k in ("team", "slug", "teamId", "conf")}
    index = sorted(search.values(), key=lambda row: row["team"])
    outputs["search-index.json"] = encode(index)
    version = hashlib.sha256(encode(outputs).encode()).hexdigest()
    old_meta_path = WEB_DATA / "meta.json"
    old_meta = json.loads(old_meta_path.read_text()) if old_meta_path.exists() else {}
    generated = old_meta.get("generatedAt") if old_meta.get("dataVersion") == version else datetime.now(timezone.utc).isoformat()
    meta = {"rankingsYears": years, "advancedYears": years, "dataVersion": version, "generatedAt": generated, "scope": "Completed FBS-vs-FBS games", "seasons": summaries}
    for filename, text in outputs.items():
        atomic_write(WEB_DATA / filename, text)
    atomic_write(site / "search-index.js", "window.CFF_SEARCH_INDEX = " + encode(index) + ";\n")
    atomic_write(WEB_DATA / "meta.json", encode(meta))
    print(f"Validated and exported {len(years)} seasons; {len(index)} searchable teams; version {version[:12]}")


if __name__ == "__main__":
    main()
