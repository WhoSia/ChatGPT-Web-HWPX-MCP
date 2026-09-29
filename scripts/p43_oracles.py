from __future__ import annotations
import hashlib
import importlib.metadata as md
import zipfile
from pathlib import Path
from typing import Any

REQUIRED={"mimetype","version.xml","META-INF/container.xml","Contents/content.hpf","Contents/header.xml","Contents/section0.xml"}

def _raw_probe(path:Path)->dict:
    try:
        with zipfile.ZipFile(path,"r") as z:
            names=set(z.namelist())
            ok=REQUIRED.issubset(names) and z.infolist()[0].filename=="mimetype" and z.read("mimetype")==b"application/hwp+zip"
            sections=len([n for n in names if n.startswith("Contents/section") and n.endswith(".xml")])
            return {"pass":bool(ok),"section_count":sections,"entry_count":len(names)}
    except Exception as exc:
        return {"pass":False,"error_class":type(exc).__name__}

def _python_hwpx_probe(path:Path)->dict:
    try:
        from hwpx import HwpxDocument
        doc=HwpxDocument.open(str(path))
        try:
            return {"pass":True,"section_count":len(doc.sections),"paragraph_count":len(doc.paragraphs),"version":md.version("python-hwpx")}
        finally:
            doc.close()
    except Exception as exc:
        return {"pass":False,"error_class":type(exc).__name__,"version":md.version("python-hwpx")}

def _hwpxkit_probe(path:Path)->dict:
    try:
        import hwpxkit
        doc=hwpxkit.parse_file(str(path))
        section_count=int(getattr(doc,"section_count",0) or 0)
        warnings=list(getattr(doc,"warnings",[]) or [])
        return {"pass":True,"section_count":section_count,"warning_count":len(warnings),"version":md.version("hwpxkit")}
    except Exception as exc:
        try: version=md.version("hwpxkit")
        except Exception: version=None
        return {"pass":False,"error_class":type(exc).__name__,"version":version}

def probe_file(path:Path,*,feature_family:str,source_id:str,source_kind:str)->dict:
    path=Path(path)
    raw=_raw_probe(path);primary=_python_hwpx_probe(path);independent=_hwpxkit_probe(path)
    section_counts=[x.get("section_count") for x in (raw,primary,independent) if x.get("pass") and x.get("section_count") is not None]
    semantic_match=bool(section_counts) and len(set(section_counts))==1
    consensus=bool(raw.get("pass") and primary.get("pass") and independent.get("pass") and semantic_match)
    return {
        "source_id":source_id,"source_kind":source_kind,"feature_family":feature_family,
        "sha256":hashlib.sha256(path.read_bytes()).hexdigest(),"byte_size":path.stat().st_size,
        "raw_owpml":raw,"python_hwpx":primary,"hwpxkit":independent,
        "semantic_match":semantic_match,"oracle_consensus_pass":consensus,
    }
