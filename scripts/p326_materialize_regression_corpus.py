from __future__ import annotations
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from p326_regression_corpus import materialize_p326_regression_corpus
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--out",type=Path,default=Path("artifacts/p326-regression-corpus"))
    a=p.parse_args()
    print(json.dumps(materialize_p326_regression_corpus(a.out),ensure_ascii=False))
if __name__=="__main__": main()
