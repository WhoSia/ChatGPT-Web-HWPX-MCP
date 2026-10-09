from pathlib import Path


def test_p414_keeps_consolidated_docker_run_layer_budget():
    dockerfile = (Path(__file__).resolve().parents[1] / "Dockerfile").read_text(encoding="utf-8")
    run_layers = sum(1 for line in dockerfile.splitlines() if line.lstrip().upper().startswith("RUN "))
    # Immutable P4.13 parent has 10 RUN instructions; P4.14 must not add layers.
    assert run_layers <= 10
    assert "python scripts/p413_release_smoke.py" in dockerfile
    assert "python scripts/p414_release_smoke.py" in dockerfile
    assert "COPY *.py p414_evidence_store.sql ./" in dockerfile
