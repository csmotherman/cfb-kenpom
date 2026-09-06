"""Corrected forensic entry point for the five CFB Sandbox systems."""
from __future__ import annotations
import argparse
from pathlib import Path
from cfb_analytics.analytics.cfb_sandbox_forensics import forensic_audit, concise
from cfb_analytics.analytics.cfb_sandbox_systems import _points, _valid_drive, load_season

def forensic_audit_v2(plays,drives):
    r=forensic_audit(plays,drives)
    valid=[d for d in drives if _valid_drive(d) and _points(d) is not None]
    regulation=sum(d.get("startPeriod") in {1,2,3,4} for d in valid)
    overtime=sum(isinstance(d.get("startPeriod"),(int,float)) and not isinstance(d.get("startPeriod"),bool) and d.get("startPeriod")>=5 for d in valid)
    r["checks"].pop("ddr_overtime_excluded",None)
    r["checks"]["ddr_regulation_overtime_partition"]=regulation+overtime==len(valid)
    r["overtimeDrivesExcludedFromDDR"]=overtime
    r["status"]="PASS" if all(r["checks"].values()) else "REVIEW"
    return r

def render(r):
    base=concise(r)
    return base.replace("Close second-half drives:",f"OT possessions excluded from DDR: {r['overtimeDrivesExcludedFromDDR']:,}\nClose second-half drives:")

def main():
    p=argparse.ArgumentParser();p.add_argument("--season",type=int,default=2025);p.add_argument("--raw-root",type=Path,default=Path("data/raw"));p.add_argument("--processed-root",type=Path,default=Path("data/processed"));a=p.parse_args();plays,drives=load_season(a.raw_root,a.processed_root,a.season);print(render(forensic_audit_v2(plays,drives)))
if __name__=="__main__":main()
