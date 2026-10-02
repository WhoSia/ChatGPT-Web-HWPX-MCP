FROM rust:1.83-slim AS native-runtime-builder
WORKDIR /src
COPY rust/p344_gate rust/p344_gate
COPY benchmarks/p344_gate_golden.tsv benchmarks/p344_gate_golden.tsv
COPY rust/p345_replay rust/p345_replay
COPY rust/p346_guard rust/p346_guard
COPY rust/p347_certifier rust/p347_certifier
COPY rust/p348_marketplace_verifier rust/p348_marketplace_verifier
RUN cargo build --release --manifest-path rust/p344_gate/Cargo.toml
RUN cargo build --release --manifest-path rust/p345_replay/Cargo.toml
RUN cargo build --release --manifest-path rust/p346_guard/Cargo.toml
RUN cargo build --release --manifest-path rust/p347_certifier/Cargo.toml
RUN cargo build --release --manifest-path rust/p348_marketplace_verifier/Cargo.toml

FROM node:22-slim AS platform-typescript-builder
WORKDIR /src
COPY contracts/p345_runtime.ts contracts/p345_runtime.ts
COPY contracts/p345_extension_sdk.ts contracts/p345_extension_sdk.ts
COPY scripts/p345_runtime_cli.ts scripts/p345_runtime_cli.ts
COPY contracts/p346_capability_kernel.ts contracts/p346_capability_kernel.ts
COPY contracts/p346_extension_sdk.ts contracts/p346_extension_sdk.ts
COPY scripts/p346_platform_cli.ts scripts/p346_platform_cli.ts
COPY contracts/p347_supply_chain_kernel.ts contracts/p347_supply_chain_kernel.ts
COPY scripts/p347_supply_chain_cli.ts scripts/p347_supply_chain_cli.ts
COPY contracts/p348_marketplace_kernel.ts contracts/p348_marketplace_kernel.ts
COPY scripts/p348_marketplace_cli.ts scripts/p348_marketplace_cli.ts
COPY contracts/p349_composition_kernel.ts contracts/p349_composition_kernel.ts
COPY scripts/p349_composition_cli.ts scripts/p349_composition_cli.ts
RUN mkdir -p /out && npx --yes -p typescript@5.9.2 tsc --strict --target ES2022 --module commonjs --rootDir . --outDir /out contracts/p345_runtime.ts contracts/p345_extension_sdk.ts scripts/p345_runtime_cli.ts contracts/p346_capability_kernel.ts contracts/p346_extension_sdk.ts scripts/p346_platform_cli.ts contracts/p347_supply_chain_kernel.ts scripts/p347_supply_chain_cli.ts contracts/p348_marketplace_kernel.ts scripts/p348_marketplace_cli.ts contracts/p349_composition_kernel.ts scripts/p349_composition_cli.ts

FROM python:3.12-slim

WORKDIR /app
ENV HWPX_PRODUCT_RELEASE=0.40.0-p4.15

COPY requirements.txt .
RUN apt-get update && apt-get install -y --no-install-recommends nodejs && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir -r requirements.txt
COPY --from=native-runtime-builder /src/rust/p344_gate/target/release/p344-gate /usr/local/bin/p344-gate
COPY --from=native-runtime-builder /src/rust/p345_replay/target/release/p345-replay /usr/local/bin/p345-replay
COPY --from=native-runtime-builder /src/rust/p346_guard/target/release/p346-guard /usr/local/bin/p346-guard
COPY --from=native-runtime-builder /src/rust/p347_certifier/target/release/p347-certifier /usr/local/bin/p347-certifier
COPY --from=native-runtime-builder /src/rust/p348_marketplace_verifier/target/release/p348-marketplace-verifier /usr/local/bin/p348-marketplace-verifier
COPY --from=platform-typescript-builder /out /app/runtime
ENV P344_GATE_BIN=/usr/local/bin/p344-gate
ENV P345_REPLAY_BIN=/usr/local/bin/p345-replay
ENV P345_TS_RUNTIME=/app/runtime/scripts/p345_runtime_cli.js
ENV P346_GUARD_BIN=/usr/local/bin/p346-guard
ENV P346_TS_RUNTIME=/app/runtime/scripts/p346_platform_cli.js
ENV P347_CERTIFIER_BIN=/usr/local/bin/p347-certifier
ENV P347_TS_RUNTIME=/app/runtime/scripts/p347_supply_chain_cli.js
ENV P348_VERIFIER_BIN=/usr/local/bin/p348-marketplace-verifier
ENV P348_TS_RUNTIME=/app/runtime/scripts/p348_marketplace_cli.js
ENV P349_TS_RUNTIME=/app/runtime/scripts/p349_composition_cli.js

COPY *.py p414_evidence_store.sql ./
COPY scripts/ scripts/
COPY benchmarks/ benchmarks/
COPY corpus/ corpus/

# Historical release-line smoke gates are intentionally retained, but executed
# in two layers so the production image stays below overlayfs layer-depth limits.
RUN set -eux; \
    python scripts/p321_release_smoke.py; \
    python scripts/p322_release_smoke.py; \
    python scripts/p323_release_smoke.py; \
    python scripts/p324_release_smoke.py; \
    python scripts/p325_release_smoke.py; \
    python scripts/p326_release_smoke.py; \
    python scripts/p327_release_smoke.py; \
    python scripts/p328_release_smoke.py; \
    python scripts/p329_release_smoke.py; \
    python scripts/p330_release_smoke.py; \
    python scripts/p331_release_smoke.py; \
    python scripts/p332_release_smoke.py; \
    python scripts/p333_release_smoke.py; \
    python scripts/p334_release_smoke.py; \
    python scripts/p335_release_smoke.py; \
    python scripts/p335r4_release_smoke.py; \
    python scripts/p336r1_release_smoke.py; \
    python scripts/p336r2_release_smoke.py; \
    python scripts/p336r2r2_release_smoke.py; \
    python scripts/p337_release_smoke.py; \
    python scripts/p338_release_smoke.py; \
    python scripts/p339_release_smoke.py; \
    python scripts/p340_release_smoke.py; \
    python scripts/p341_release_smoke.py; \
    python scripts/p342_release_smoke.py; \
    python scripts/p343_release_smoke.py; \
    P344_REQUIRE_RUST_GATE=1 python scripts/p344_release_smoke.py; \
    python scripts/p345_release_smoke.py; \
    python scripts/p346_release_smoke.py; \
    python scripts/p347_release_smoke.py; \
    python scripts/p348_release_smoke.py; \
    python scripts/p349_release_smoke.py

RUN set -eux; \
    python scripts/p41_release_smoke.py; \
    python scripts/p42_release_smoke.py; \
    python scripts/p43_release_smoke.py; \
    python scripts/p44_release_smoke.py; \
    python scripts/p45_release_smoke.py; \
    python scripts/p46_release_smoke.py; \
    python scripts/p47_release_smoke.py; \
    python scripts/p48_release_smoke.py; \
    python scripts/p48_component_benchmark.py --out /tmp/p48-component-benchmark >/dev/null; \
    python scripts/p49_release_smoke.py; \
    python scripts/p410_release_smoke.py; \
    python scripts/p411_release_smoke.py; \
    python scripts/p412_release_smoke.py; \
    python scripts/p413_release_smoke.py; \
    python scripts/p414_release_smoke.py

ENV MCP_HOST=0.0.0.0
ENV MCP_PORT=8000
ENV MCP_PATH=/mcp
ENV P1_OBJECT_DIR=/tmp/chatgpt-web-hwpx-mcp-p1
ENV P1_DOC_TTL_SECONDS=1800
ENV P1_MAX_TEXT_CHARS=100000

EXPOSE 8000

# P4.15 self-verifying release authority candidate
CMD ["python", "server_p2.py"]
