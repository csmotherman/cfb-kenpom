from __future__ import annotations
import argparse,json
from pathlib import Path
from cfb_analytics.raw.audit import discover_partitions
from cfb_analytics.canonical.materialize import canonical_partition_dir
from cfb_analytics.analytics.tfl import corpus_tfl_audit
SEASONS=(2014,2015,2016,2017,2018,2019,2021,2022,2023,2024,2025)
def main():
    p=argparse.ArgumentParser();p.add_argument("command",choices=("audit",));p.add_argument("--root",type=Path,default=Path("data/raw"));p.add_argument("--processed-root",type=Path,default=Path("data/processed"));p.add_argument("--season",type=int);p.add_argument("--json",action="store_true",dest="as_json");a=p.parse_args();plays=[]
    for s in ((a.season,) if a.season else SEASONS):
        for st,w in discover_partitions(a.root,s):plays.extend(json.loads((canonical_partition_dir(a.processed_root,s,st,w)/"plays.json").read_text()))
    r=corpus_tfl_audit(plays)
    if a.as_json:print(json.dumps(r,indent=2));return
    print("TACKLE FOR LOSS AUDIT (v1)")
    print(f"Structural candidates: {r['structural_candidates']:,}")
    print(f"High-confidence kneels excluded: {r['high_confidence_kneels_excluded']:,}")
    print(f"Production non-sack TFLs: {r['tackles_for_loss']:,}")
    print(f"Rush TFLs: {r['rush_tfls']:,}")
    print(f"Completed-pass TFLs: {r['completion_tfls']:,}")
    print("Definition: clean negative rush/completed pass, excluding high-confidence structural kneels; sacks remain separate.")
if __name__=="__main__":main()
