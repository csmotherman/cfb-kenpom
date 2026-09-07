"""Re-export the already-built site/data.js, site/advanced-data.js and
site/search-index.js as per-season JSON under web/public/data/.

This does not recompute anything -- it reads the same generated artifacts
the static site (site/) already serves, and re-shapes them for the Next.js
app (web/) to fetch() at runtime instead of loading two ~5MB/~12MB <script>
globals up front. Run this after scripts/compile_site_data.py.
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
from compile_site_data import read_js_assignment  # noqa: E402

WEB_DATA = REPO / "web/public/data"


def main():
    site = REPO / "site"

    cfb_weeks = read_js_assignment(site / "data.js", "CFB_WEEKS") or {}
    cfb_data = read_js_assignment(site / "data.js", "CFB_DATA") or {}
    cfb_years = read_js_assignment(site / "data.js", "CFB_YEARS") or []

    adv_weeks = read_js_assignment(site / "advanced-data.js", "CFF_ADV_WEEKS") or {}
    adv_data = read_js_assignment(site / "advanced-data.js", "CFF_ADV_DATA") or {}
    adv_years = read_js_assignment(site / "advanced-data.js", "CFF_ADV_YEARS") or []

    search_index = read_js_assignment(site / "search-index.js", "CFF_SEARCH_INDEX") or []

    (WEB_DATA / "rankings").mkdir(parents=True, exist_ok=True)
    (WEB_DATA / "advanced").mkdir(parents=True, exist_ok=True)

    for year in cfb_years:
        key = str(year)
        payload = {"weeks": cfb_weeks.get(key, []), "byWeek": cfb_data.get(key, {})}
        (WEB_DATA / "rankings" / f"{key}.json").write_text(
            json.dumps(payload, separators=(",", ":"))
        )

    for year in adv_years:
        key = str(year)
        payload = {"weeks": adv_weeks.get(key, []), "byWeek": adv_data.get(key, {})}
        (WEB_DATA / "advanced" / f"{key}.json").write_text(
            json.dumps(payload, separators=(",", ":"))
        )

    (WEB_DATA / "meta.json").write_text(json.dumps({
        "rankingsYears": cfb_years,
        "advancedYears": adv_years,
    }, separators=(",", ":")))

    (WEB_DATA / "search-index.json").write_text(json.dumps(search_index, separators=(",", ":")))

    print(f"wrote {len(cfb_years)} rankings season files, {len(adv_years)} advanced season files")


if __name__ == "__main__":
    main()
