from __future__ import annotations
import json
import tempfile
import zipfile
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from p336_corpus import build_native_style_census, derive_engineering_priorities, inspect_native_style

HEADER = b"""<root><fontface lang="HANGUL"><font id="0" face="SmokeFont"/></fontface><charPr id="0" height="1100"><fontRef hangul="0"/><spacing hangul="0"/></charPr><paraPr id="0"><align horizontal="JUSTIFY"/><heading type="NONE" level="0"/></paraPr></root>"""
SECTION = b"""<root><p paraPrIDRef="0"><run charPrIDRef="0"><t>Smoke body</t></run></p><tbl><tc><p paraPrIDRef="0"><run charPrIDRef="0"><t>Cell</t></run></p></tc></tbl></root>"""

with tempfile.TemporaryDirectory(prefix="p336r1-") as tmp:
    path = Path(tmp) / "AAAAAAAAAAAA.hwpx"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("Contents/header.xml", HEADER)
        z.writestr("Contents/section0.xml", SECTION)
    observation = inspect_native_style(path, blind_id="AAAAAAAAAAAA")
    assert observation["status"] == "PASS"
    census = build_native_style_census([observation])
    priorities = derive_engineering_priorities(census)
    assert census["selection_policy"] == "NO_AUTOMATIC_STYLE_WINNER"
    assert priorities["design_authority_ladder"][-1] == "EXPLICIT_HUMAN_DESIGN_TARGET"
    print(json.dumps({
        "status": "PASS",
        "phase": "P3.36-R1",
        "authority": census["authority"],
        "priority_count": len(priorities["priorities"]),
    }, ensure_ascii=False))
