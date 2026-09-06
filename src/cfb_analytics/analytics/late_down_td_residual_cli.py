from __future__ import annotations
import argparse,json
from pathlib import Path
from cfb_analytics.raw.audit import discover_partitions
from cfb_analytics.canonical.materialize import canonical_partition_dir
from cfb_analytics.analytics.late_down_td_residual import audit_td_residual,concise
SEASONS=(2014,2015,2016,2017,2018,2019,2021,2022,2023,2024,2025)
def main():
 p=argparse.ArgumentParser();p.add_argument("command",choices=("audit",));p.add_argument("--root",type=Path,default=Path("data/raw"));p.add_argument("--processed-root",type=Path,default=Path("data/processed"));p.add_argument("--season",type=int);p.add_argument("--json",action="store_true",dest="as_json");a=p.parse_args();plays=[]
 for s in ((a.season,) if a.season else SEASONS):
  for st,w in discover_partitions(a.root,s):plays.extend(json.loads((canonical_partition_dir(a.processed_root,s,st,w)/"plays.json").read_text()))
 r=audit_td_residual(plays);print(json.dumps(r,indent=2,sort_keys=True) if a.as_json else concise(r))
if __name__=="__main__":main()
