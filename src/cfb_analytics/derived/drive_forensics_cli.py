from __future__ import annotations
import argparse, json
from pathlib import Path
from cfb_analytics.derived.drive_forensics import drive_ownership_forensics, concise_drive_ownership_forensics

SEASONS=(2014,2015,2016,2017,2018,2019,2021,2022,2023,2024,2025)

def main():
    p=argparse.ArgumentParser(prog="cfb-drive-forensics")
    p.add_argument("--root",type=Path,default=Path("data/raw"))
    p.add_argument("--processed-root",type=Path,default=Path("data/processed"))
    p.add_argument("--season",type=int)
    p.add_argument("--examples",type=int,default=4)
    p.add_argument("--json",action="store_true",dest="as_json")
    a=p.parse_args()
    seasons=(a.season,) if a.season else SEASONS
    r=drive_ownership_forensics(a.root,a.processed_root,seasons,a.examples)
    print(json.dumps(r,indent=2) if a.as_json else concise_drive_ownership_forensics(r))

if __name__=="__main__": main()
