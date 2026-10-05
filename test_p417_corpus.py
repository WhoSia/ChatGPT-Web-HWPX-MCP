from __future__ import annotations

import zipfile
from pathlib import Path

from p417_corpus import analyze_hwpx, attach_render_pair, build_dataset, corpus_contract, infer_archetype


def make_hwpx(path: Path, text: str, *, table: bool = False, equation: bool = False) -> None:
    body = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<section xmlns="http://www.hancom.co.kr/hwpml/2011/section">',
        '<p><run><t>' + text + '</t></run></p>',
    ]
    if table:
        body.append('<tbl><tr><tc><p><run><t>cell</t></run></p></tc></tr></tbl>')
    if equation:
        body.append('<equation><script>x+y</script></equation>')
    body.append('</section>')
    header = '<?xml version="1.0" encoding="UTF-8"?><head><font id="1" face="Hamchorom"/><style id="1"/><charPr id="1" height="1000"/><paraPr id="1" align="LEFT"/><pagePr width="59528" height="84188"/></head>'
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("Contents/section0.xml", "".join(body))
        zf.writestr("Contents/header.xml", header)
        zf.writestr("mimetype", "application/hwp+zip")


def test_analyze_extracts_package_xml_and_style_grammar(tmp_path):
    path = tmp_path / "입찰공고.hwpx"
    make_hwpx(path, "입찰에 부치는 사항", table=True)
    record = analyze_hwpx(path, source={"institution": "TEST", "source_id": "a"})
    assert record["package_features"]["xml_part_count"] == 2
    assert record["package_features"]["table_like_count"] == 1
    assert record["style_grammar"]["has_tables"] is True
    assert record["style_grammar"]["font_faces"]["Hamchorom"] == 1
    assert len(record["style_grammar"]["char_property_signatures"]) == 1
    assert len(record["style_grammar"]["para_property_signatures"]) == 1
    assert len(record["style_grammar"]["page_property_signatures"]) == 1
    assert record["archetype"]["archetype"] == "BID_NOTICE"
    assert record["source"]["raw_bytes_persisted"] is False


def test_archetype_from_filename_and_hints():
    result = infer_archetype(filename="[제안요청서] 사업.hwpx")
    assert result["archetype"] == "RFP"
    hinted = infer_archetype(filename="neutral.hwpx", hints=["과제제안요구서 RFP"])
    assert hinted["archetype"] == "RFP_REQUIREMENT"


def test_dataset_deduplicates_by_document_sha(tmp_path):
    path = tmp_path / "a.hwpx"
    make_hwpx(path, "서식")
    a = analyze_hwpx(path, source={"institution": "A"})
    b = analyze_hwpx(path, source={"institution": "B"})
    dataset = build_dataset([a, b])
    assert dataset["record_count"] == 1
    assert dataset["duplicate_count"] == 1
    assert dataset["raw_document_bytes_persisted"] is False


def test_render_pair_remains_unadjudicated(tmp_path):
    path = tmp_path / "a.hwpx"
    make_hwpx(path, "보고서")
    record = analyze_hwpx(path)
    paired = attach_render_pair(record, pdf_sha256="a" * 64)
    assert paired["render_pair"]["status"] == "PAIRED_UNADJUDICATED"
    assert paired["render_pair"]["native_visual_authority"] is False


def test_contract_separates_structural_dataset_from_native_authority():
    contract = corpus_contract()
    assert contract["product"] == "0.42.0-p4.17"
    assert contract["raw_bytes_policy"] == "EPHEMERAL_ONLY_BY_DEFAULT"
    assert "RENDER_PAIR_UNADJUDICATED" in contract["ground_truth_layers"]
