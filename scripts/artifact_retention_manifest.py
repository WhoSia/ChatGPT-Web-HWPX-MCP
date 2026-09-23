"""Inventory only. Never deletes or uploads; uncertainty defaults to KEEP_REVIEW."""
import argparse
import hashlib
import json
from pathlib import Path

def classify(relative: Path):
    name=relative.name.lower();parts={p.lower() for p in relative.parts}
    if any(p.startswith('.venv') for p in parts) or parts & {'__pycache__','.pytest_cache','node_modules'}:
        return 'DISCARD','reconstructible environment/cache'
    if name.endswith('-captured.zip') or 'manifest' in name or 'summary' in name or 'receipt' in name:
        return 'KEEP','native/provenance candidate; verify archive SHA before deletion'
    if relative.suffix.lower() in {'.hwpx','.hwp','.pdf','.png','.jpg','.zip'}:
        return 'KEEP_REVIEW','may contain unique native or public evidence; provenance review required'
    if relative.suffix.lower() in {'.log','.pyc'}: return 'REGENERATE','ordinary generated log/cache unless specifically cited'
    return 'KEEP_REVIEW','unclassified; no deletion authority'

def manifest(root):
    root=root.resolve();rows=[]
    for p in sorted(root.rglob('*')):
        if not p.is_file() or p.is_symlink(): continue
        if not p.resolve().is_relative_to(root): continue
        relative=p.relative_to(root);kind,reason=classify(relative)
        with p.open('rb') as f: digest=hashlib.file_digest(f,'sha256').hexdigest()
        rows.append({'path':relative.as_posix(),'bytes':p.stat().st_size,'sha256':digest,'retention':kind,'reason':reason})
    return {'schema':'hwpx-retention-inventory/v1','mode':'INVENTORY_ONLY_NO_DELETE_NO_UPLOAD','files':rows}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    a.out.write_text(json.dumps(manifest(a.root),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
