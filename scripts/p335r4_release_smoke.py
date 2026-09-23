"""Database-free Docker packaging and evidence-to-existing-operations smoke."""
import json
import sys
import tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from hwpx import HwpxDocument
from p335_registry import intake_source, registry_snapshot
from p335_atlas import build_style_atlas, synthesize_templates, compile_template
from p335_visual import control_descriptor, native_patterns
import p335_mcp

def main():
    with tempfile.TemporaryDirectory() as tmp:
        path=Path(tmp)/'source.hwpx';doc=HwpxDocument.new();doc.add_paragraph('R4 evidence to artifact');doc.save_to_path(path);doc.close()
        row=intake_source({'source_id':'smoke','original_filename':'source.hwpx','institution':'synthetic',
                           'retrieved_at':'2026-09-23T00:00:00Z','access_status':'LOCALLY_GENERATED_NATIVE_EVIDENCE'},path)
        assert row['parser_status']=='PASS'
        assert build_style_atlas([row])['roles']
        t=synthesize_templates([row],mode='EXPLICIT_EXEMPLAR',source_id='smoke')['templates'][0]
        assert compile_template(t,{'body':['p:0:1']},expected_revision=1)['operations']
        assert control_descriptor(row['sha256'])['status']=='NOT_PROVIDED'
        assert native_patterns(row)
        print(json.dumps({'status':'PASS','phase':'P3.35-R4','authority':t['authority'],'corpus_sha256':registry_snapshot([row])['corpus_sha256']}))
if __name__=='__main__': main()
