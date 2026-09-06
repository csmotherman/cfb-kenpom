"""Publish a sourced 2026 Michigan player-importance board."""
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path
from typing import Any

SOURCE = {"name": "Ourlads Michigan depth chart", "url": "https://www.ourlads.com/ncaa-football/depth-charts/depth-chart/michigan/91119", "updated": "2026-08-08"}
STARTERS = {
    "bryceunderwood":"QB1","jordanmarshall":"RB1","andrewmarsh":"WR-X","jaimeffrench":"WR-Z","jjbuchanan":"SLOT","zackmarshall":"TE1",
    "blakefrazier":"LT","evanlink":"LG","jakeguarnera":"C","nathanefobi":"RG","andrewsprague":"RT",
    "cameronbrandt":"LDE","treypierce":"LDT","enowetta":"RDT","johnhenrydaley":"RDE","nathanielowusuboateng":"WLB","troybowles":"MLB",
    "zekeberry":"LCB","chrisbracy":"SS","rodmoore":"FS","jyairehill":"RCB","smithsnowden":"NB",
    "cambrown":"P1","treybutkowski":"K1","nicocrawford":"LS1",
}
SECOND = {
    "tommycarr":"QB2","savionhiter":"RB2","jamarbrowder":"WR-X2","salesimoa":"WR-Z2","channinggoodwin":"SLOT2","hoganhansen":"TE2",
    "andrewbabalola":"LT2","lukehamilton":"LG2","houstonkaahaainatorres":"C2","bradynorton":"RG2","malakailee":"RT2",
    "dominicnichols":"LDE2","deyvidpalepale":"LDT2","jonahleaea":"RDT2","natemarshall":"RDE2","nathanielstaehling":"WLB2","chasetaylor":"MLB2",
    "shamariearls":"LCB2","masoncurtis":"SS2","jordanyoung":"FS2","joziahedmond":"RCB2","jamarionvincent":"NB2",
}
POSITION_WEIGHT = {"QB":100,"RB":91,"WR":88,"TE":82,"OL":86,"OT":86,"OG":85,"C":87,"DE":90,"EDGE":90,"DT":89,"NT":89,"LB":88,"CB":90,"DB":88,"S":89,"K":72,"PK":72,"P":70,"LS":62}


def normalize(value: str) -> str:
    value=unicodedata.normalize("NFKD",value).encode("ascii","ignore").decode().lower()
    return re.sub(r"[^a-z0-9]","",value)


def build(roster: list[dict[str, Any]], grades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grade_by_id={str(row["playerId"]):row for row in grades}; rows=[]
    for player in roster:
        player_id=str(player["id"]); name=f'{player["firstName"]} {player["lastName"]}'; key=normalize(name); position=str(player.get("position") or "").upper(); grade=grade_by_id.get(player_id)
        if key in STARTERS: role,depth,tier=STARTERS[key],1,"PROJECTED STARTER"
        elif key in SECOND: role,depth,tier=SECOND[key],2,"PROJECTED SECOND UNIT"
        else: role,depth,tier=position or "ATH",3,"ROSTER DEPTH"
        score=(300 if depth==1 else 180 if depth==2 else 60)+POSITION_WEIGHT.get(position,75)+(float(grade.get("nationalPositionPercentile",0))*.12 if grade else 0)
        if key=="bryceunderwood": score=1000
        reason = "Starting quarterback and the highest-leverage player in Michigan's playoff path." if key=="bryceunderwood" else (f"Projected {role}; expected first-unit role carries more weight than raw box-score grade." if depth==1 else f"{tier.title()} at {role}; importance rises with a larger verified role.")
        rows.append({"playerId":player_id,"role":role,"depth":depth,"tier":tier,"importanceScore":round(score,2),"reason":reason})
    rows.sort(key=lambda row:(-row["importanceScore"],row["playerId"]));
    for rank,row in enumerate(rows,1):row["rank"]=rank
    return rows


def main()->None:
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--roster",type=Path,default=Path("data/published/2026/michigan/roster.json"));parser.add_argument("--grades",type=Path,default=Path("data/published/2026/michigan/player-production-grades.json"));parser.add_argument("--output",type=Path,default=Path("data/published/2026/michigan/player-importance.json"));args=parser.parse_args()
    rows=build(json.loads(args.roster.read_text()),json.loads(args.grades.read_text()));artifact={"season":2026,"team":"Michigan","valueType":"PROJECTED","definitionVersion":"player-importance-v1","source":SOURCE,"players":rows};args.output.write_text(json.dumps(artifact,indent=2,sort_keys=True)+"\n");print(json.dumps({"status":"PASS","players":len(rows),"first":rows[0]["playerId"],"output":str(args.output)}))


if __name__=="__main__":main()
