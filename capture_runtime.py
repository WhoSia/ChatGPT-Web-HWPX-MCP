"""Small, reproducible standalone pack runtime. Never copies environments/artifacts."""
import hashlib
import json
import shutil
from pathlib import Path


def attach_capture_runtime(pack: Path):
    repo=Path(__file__).resolve().parent
    destination=pack/'runtime'
    paths=[p for p in repo.glob('*.py') if not p.name.startswith('test')]
    paths += [p for p in (repo/'scripts').rglob('*') if p.suffix in {'.py','.ps1'} and '__pycache__' not in p.parts]
    paths += [repo/name for name in ('requirements.txt','requirements-capture.txt','requirements-dev.txt')]
    manifest=[]
    for source in sorted(paths):
        relative=source.relative_to(repo);target=destination/relative
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source,target)
        manifest.append({'path':relative.as_posix(),'sha256':hashlib.sha256(source.read_bytes()).hexdigest()})
    receipt={'schema':'hwpx-portable-capture-runtime/v1','files':manifest,
             'environment':'External shared HWPX_MCP_VENV or LOCALAPPDATA/ChatGPT-Web-HWPX-MCP/venv/py312',
             'usage':'For analysis use runtime/scripts/*analyze*.py --pack with the existing pack path. For new capture use the appropriate runtime/scripts/*.ps1 with a NEW -OutDir; do not rematerialize over native evidence.',
             'retention':'REGENERATE','contains_environment':False}
    (pack/'runtime-manifest.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return receipt
