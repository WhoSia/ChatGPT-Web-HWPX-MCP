FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py server_p2.py p2_document.py p22_formatting.py p23_richtext.py p24_inline.py p25_controls.py p26_controls.py p27_tables.py p28_tables.py p29_objects.py p210_equations.py document_store.py oauth_provider.py auth_store.py hwp5_reader.py common_ir.py p39_textbox.py p311_layout_fidelity.py p312_render_harness.py p313_capture_custody.py p314_capture_intake.py p315_cross_version.py p315_replay_builder.py p316_version_indexed.py p316_stability_builder.py p317_fidelity_envelope.py p317_page_geometry.py p318_document_setup.py p319_structured_publishing.py p320_annotation_apparatus.py ./

ENV MCP_HOST=0.0.0.0
ENV MCP_PORT=8000
ENV MCP_PATH=/mcp
ENV P1_OBJECT_DIR=/tmp/chatgpt-web-hwpx-mcp-p1
ENV P1_DOC_TTL_SECONDS=1800
ENV P1_MAX_TEXT_CHARS=100000

EXPOSE 8000

CMD ["python", "server_p2.py"]
