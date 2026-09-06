from __future__ import annotations
import argparse,json
from pathlib import Path
from cfb_analytics.analytics.post_touchdown_forensics import audit_post_touchdowns,concise_post_touchdown_audit
SEASONS=(2014,2015,2016,2017,2018,2019,2021,2022,2023,2024,2025)
def main():
 p=argparse.ArgumentParser(prog="python -m cfb_analytics.analytics.post_touchdown_forensics_cli");p.add_argument("command",choices=("audit",));p.add_argument("--root",type=Path,default=Path("data/raw"));p.add_argument("--processed-root",type=Path,default=Path("data/processed"));p.add_argument("--season",type=int);p.add_argument("--json",action="store_true",dest="as_json");p.add_argument("--examples",type=int,default=12);a=p.parse_args();seasons=(a.season,) if a.season else SEASONS;r=audit_post_touchdowns(a.root,a.processed_root,seasons,a.examples);print(json.dumps(r,indent=2) if a.as_json else concise_post_touchdown_audit(r))
if __name__=="__main__":main()
