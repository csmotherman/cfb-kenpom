"""Directional v2 label for the corrected raw-feature walk-forward baseline."""
from pathlib import Path
import argparse
from cfb_analytics.analytics.walk_forward_baseline import walk_forward


def main():
    p=argparse.ArgumentParser();p.add_argument("--raw-root",type=Path,default=Path("data/raw"));p.add_argument("--processed-root",type=Path,default=Path("data/processed"));a=p.parse_args();r=walk_forward(a.raw_root,a.processed_root)
    print("WALK-FORWARD BASELINE v2 DIRECTIONAL")
    print(f"Features: {len(r['features'])}")
    for season,x in r["results"].items():
        print(f"\nTEST {season}")
        print(f"Train games: {x['train_games']:,}")
        print(f"Test games: {x['test_games']:,}")
        print(f"Margin MAE: {x['margin_mae']:.3f}")
        print(f"Margin RMSE: {x['margin_rmse']:.3f}")
        print(f"Winner accuracy: {x['winner_accuracy']:.2%}")

if __name__=="__main__":main()
