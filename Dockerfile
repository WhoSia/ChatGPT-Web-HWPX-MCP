FROM rust:1.83-slim AS native-runtime-builder
WORKDIR /src
COPY rust/p344_gate rust/p344_gate
COPY benchmarks/p344_gate_golden.tsv benchmarks/p344_gate_golden.tsv
COPY rust/p345_replay rust/p345_replay
RUN cargo build --release --manifest-path rust/p344_gate/Cargo.toml
RUN cargo build --release --manifest-path rust/p345_replay/Cargo.toml

FROM node:22-slim AS p345-typescript-builder
WORKDIR /src
COPY contracts/p345_runtime.ts contracts/p345_runtime.ts
COPY contracts/p345_extension_sdk.ts contracts/p345_extension_sdk.ts
COPY scripts/p345_runtime_cli.ts scripts/p345_runtime_cli.ts
RUN mkdir -p /out && npx --yes -p typescript@5.9.2 tsc --strict --target ES2022 --module commonjs --rootDir . --outDir /out contracts/p345_runtime.ts contracts/p345_extension_sdk.ts scripts/p345_runtime_cli.ts

FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN apt-get update && apt-get install -y --no-install-recommends nodejs && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir -r requirements.txt
COPY --from=native-runtime-builder /src/rust/p344_gate/target/release/p344-gate /usr/local/bin/p344-gate
COPY --from=native-runtime-builder /src/rust/p345_replay/target/release/p345-replay /usr/local/bin/p345-replay
COPY --from=p345-typescript-builder /out /app/runtime
ENV P344_GATE_BIN=/usr/local/bin/p344-gate
ENV P345_REPLAY_BIN=/usr/local/bin/p345-replay
ENV P345_TS_RUNTIME=/app/runtime/scripts/p345_runtime_cli.js

COPY server.py server_p2.py p2_document.py p22_formatting.py p23_richtext.py p24_inline.py p25_controls.py p26_controls.py p27_tables.py p28_tables.py p29_objects.py p210_equations.py document_store.py oauth_provider.py auth_store.py hwp5_reader.py common_ir.py p39_textbox.py p311_layout_fidelity.py p312_render_harness.py p313_capture_custody.py p314_capture_intake.py p315_cross_version.py p315_replay_builder.py p316_version_indexed.py p316_stability_builder.py p317_fidelity_envelope.py p317_page_geometry.py p318_document_setup.py p319_structured_publishing.py p320_annotation_apparatus.py p321_document_composer.py p322_review_workflow.py p323_advanced_tables.py p324_story_layer.py p325_drawing_layer.py p326_drawing_style.py p327_diagram_composition.py p328_high_level_diagrams.py p329_diagram_lifecycle.py p330_diagram_design_system.py p331_diagram_quality_assurance.py p332_brownfield_diagrams.py p333_file_delivery.py p334_rare_feature_registry.py p334r1_column_insertion.py p334r2_tracked_resolution.py p334r2_package_validation.py p334r3_existing_group.py p335_typography.py p335_paragraph.py p335_corpus.py p335_registry.py p335_visual.py p335_atlas.py p335_mcp.py p336_corpus.py p336r2_design.py p337_product_workflow.py p338_rich_builder.py p339_design_intelligence.py p340_feedback_loop.py p341_page_composition.py p342_mutation_footprint.py p342_corpus_evidence.py p342_mcp.py p343_design_system.py p343_mcp.py p344_autonomous_authoring.py p344_mcp.py p345_runtime_bridge.py p345_mcp.py capture_runtime.py ./
COPY scripts/p321_release_smoke.py scripts/p321_release_smoke.py
COPY scripts/p322_release_smoke.py scripts/p322_release_smoke.py
COPY scripts/p323_release_smoke.py scripts/p323_release_smoke.py
COPY scripts/p324_release_smoke.py scripts/p324_release_smoke.py
COPY scripts/p325_release_smoke.py scripts/p325_release_smoke.py
COPY scripts/p326_release_smoke.py scripts/p326_release_smoke.py
COPY scripts/p327_release_smoke.py scripts/p327_release_smoke.py
COPY scripts/p328_release_smoke.py scripts/p328_release_smoke.py
COPY scripts/p329_release_smoke.py scripts/p329_release_smoke.py
COPY scripts/p330_release_smoke.py scripts/p330_release_smoke.py
COPY scripts/p331_release_smoke.py scripts/p331_release_smoke.py
COPY scripts/p332_release_smoke.py scripts/p332_release_smoke.py
RUN python scripts/p321_release_smoke.py
RUN python scripts/p322_release_smoke.py
RUN python scripts/p323_release_smoke.py
RUN python scripts/p324_release_smoke.py
RUN python scripts/p325_release_smoke.py
RUN python scripts/p326_release_smoke.py
RUN python scripts/p327_release_smoke.py
RUN python scripts/p328_release_smoke.py
RUN python scripts/p329_release_smoke.py
RUN python scripts/p330_release_smoke.py
RUN python scripts/p331_release_smoke.py
RUN python scripts/p332_release_smoke.py
COPY scripts/p333_release_smoke.py scripts/p333_release_smoke.py
RUN python scripts/p333_release_smoke.py
COPY scripts/p334_release_smoke.py scripts/p334_release_smoke.py
RUN python scripts/p334_release_smoke.py
COPY scripts/p335_release_smoke.py scripts/p335_release_smoke.py
RUN python scripts/p335_release_smoke.py
COPY scripts/p335r4_release_smoke.py scripts/p335r4_release_smoke.py
RUN python scripts/p335r4_release_smoke.py
COPY scripts/p336r1_release_smoke.py scripts/p336r1_release_smoke.py
RUN python scripts/p336r1_release_smoke.py
COPY scripts/p336r2_release_smoke.py scripts/p336r2_release_smoke.py
RUN python scripts/p336r2_release_smoke.py
COPY scripts/p336r2r2_release_smoke.py scripts/p336r2r2_release_smoke.py
RUN python scripts/p336r2r2_release_smoke.py
COPY scripts/p337_release_smoke.py scripts/p337_release_smoke.py
RUN python scripts/p337_release_smoke.py
COPY scripts/p338_release_smoke.py scripts/p338_release_smoke.py
RUN python scripts/p338_release_smoke.py
COPY scripts/p339_release_smoke.py scripts/p339_release_smoke.py
RUN python scripts/p339_release_smoke.py
COPY scripts/p340_release_smoke.py scripts/p340_release_smoke.py
RUN python scripts/p340_release_smoke.py
COPY scripts/p341_release_smoke.py scripts/p341_release_smoke.py
RUN python scripts/p341_release_smoke.py
COPY scripts/p342_release_smoke.py scripts/p342_release_smoke.py
RUN python scripts/p342_release_smoke.py
COPY scripts/p343_release_smoke.py scripts/p343_release_smoke.py
RUN python scripts/p343_release_smoke.py
COPY scripts/p344_release_smoke.py scripts/p344_release_smoke.py
RUN P344_REQUIRE_RUST_GATE=1 python scripts/p344_release_smoke.py
COPY scripts/p345_release_smoke.py scripts/p345_release_smoke.py
RUN python scripts/p345_release_smoke.py

ENV MCP_HOST=0.0.0.0
ENV MCP_PORT=8000
ENV MCP_PATH=/mcp
ENV P1_OBJECT_DIR=/tmp/chatgpt-web-hwpx-mcp-p1
ENV P1_DOC_TTL_SECONDS=1800
ENV P1_MAX_TEXT_CHARS=100000

EXPOSE 8000

CMD ["python", "server_p2.py"]
