FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py server_p2.py p2_document.py p22_formatting.py p23_richtext.py p24_inline.py p25_controls.py p26_controls.py p27_tables.py p28_tables.py p29_objects.py p210_equations.py document_store.py oauth_provider.py auth_store.py hwp5_reader.py common_ir.py p39_textbox.py p311_layout_fidelity.py p312_render_harness.py p313_capture_custody.py p314_capture_intake.py p315_cross_version.py p315_replay_builder.py p316_version_indexed.py p316_stability_builder.py p317_fidelity_envelope.py p317_page_geometry.py p318_document_setup.py p319_structured_publishing.py p320_annotation_apparatus.py p321_document_composer.py p322_review_workflow.py p323_advanced_tables.py p324_story_layer.py p325_drawing_layer.py p326_drawing_style.py p327_diagram_composition.py ./
COPY scripts/p321_release_smoke.py scripts/p321_release_smoke.py
COPY scripts/p322_release_smoke.py scripts/p322_release_smoke.py
COPY scripts/p323_release_smoke.py scripts/p323_release_smoke.py
COPY scripts/p324_release_smoke.py scripts/p324_release_smoke.py
COPY scripts/p325_release_smoke.py scripts/p325_release_smoke.py
COPY scripts/p326_release_smoke.py scripts/p326_release_smoke.py
COPY scripts/p327_release_smoke.py scripts/p327_release_smoke.py
RUN python scripts/p321_release_smoke.py
RUN python scripts/p322_release_smoke.py
RUN python scripts/p323_release_smoke.py
RUN python scripts/p324_release_smoke.py
RUN python scripts/p325_release_smoke.py
RUN python scripts/p326_release_smoke.py
RUN python scripts/p327_release_smoke.py

ENV MCP_HOST=0.0.0.0
ENV MCP_PORT=8000
ENV MCP_PATH=/mcp
ENV P1_OBJECT_DIR=/tmp/chatgpt-web-hwpx-mcp-p1
ENV P1_DOC_TTL_SECONDS=1800
ENV P1_MAX_TEXT_CHARS=100000

EXPOSE 8000

CMD ["python", "server_p2.py"]
