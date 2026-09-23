"""Offline bounded intake; no arbitrary URL downloader and no source redistribution."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from p335_registry import intake_source, registry_snapshot

def main():
    p=argparse.ArgumentParser();p.add_argument('--metadata',type=Path,required=True);p.add_argument('--source-dir',type=Path);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();items=json.loads(a.metadata.read_text(encoding='utf-8'))
    if not isinstance(items,list) or len(items)>500: raise ValueError('CORPUS_SOURCE_LIMIT')
    rows=[]
    for m in items:
        row=intake_source(m)
        if a.source_dir:
            path=a.source_dir/(m['source_id']+'.hwpx')
            if path.is_file(): row=intake_source(m,path)
        rows.append(row)
    snapshot=registry_snapshot(rows);a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(snapshot,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in snapshot.items() if k!='records'},ensure_ascii=False))
if __name__=='__main__': main()
