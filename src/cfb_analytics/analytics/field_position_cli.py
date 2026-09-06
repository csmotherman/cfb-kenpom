from __future__ import annotations
import argparse,json
from pathlib import Path
from cfb_analytics.raw.audit import discover_partitions
from cfb_analytics.derived.drives import derived_drive_partition_dir
from cfb_analytics.analytics.field_position import field_position_audit,concise_field_position_audit
SEASONS=(2014,2015,2016,2017,2018,2019,2021,2022,2023,2024,2025)
def main():
 p=argparse.ArgumentParser();p.add_argument("command",choices=("audit",));p.add_argument("--root",type=Path,default=Path("data/raw"));p.add_argument("--processed-root",type=Path,default=Path("data/processed"));p.add_argument("--season",type=int);p.add_argument("--json",action="store_true",dest="as_json");a=p.parse_args();seasons=(a.season,) if a.season else SEASONS;drives=[]
 for s in seasons:
  for st,w in discover_partitions(a.root,s):drives.extend(json.loads((derived_drive_partition_dir(a.processed_root,s,st,w)/"drives.json").read_text()))
 r=field_position_audit(drives);print(json.dumps(r,indent=2) if a.as_json else concise_field_position_audit(r))
if __name__=="__main__":main()
