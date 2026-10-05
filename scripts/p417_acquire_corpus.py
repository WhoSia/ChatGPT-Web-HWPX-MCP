from __future__ import annotations

import argparse
import html
import json
import re
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from p417_corpus import analyze_hwpx, build_dataset

UA = "ChatGPT-Web-HWPX-MCP-P4.17/1.0 corpus-research"
MAX_PAGE_BYTES = 5_000_000
MAX_DOCUMENT_BYTES = 15_000_000
MAX_ATTACHMENTS_PER_SOURCE = 12


def fetch(url: str, limit: int) -> tuple[bytes, dict]:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=40) as response:
        data = response.read(limit + 1)
        if len(data) > limit:
            raise RuntimeError("bounded fetch size exceeded")
        return data, {
            "content_type": response.headers.get("Content-Type", ""),
            "content_disposition": response.headers.get("Content-Disposition", ""),
            "final_url": response.geturl(),
        }


def discover_links(page_url: str, page: bytes) -> list[dict]:
    text = page.decode("utf-8", errors="replace")
    out: list[dict] = []
    for match in re.finditer(r"<a\b[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", text, flags=re.I | re.S):
        href = html.unescape(match.group(1))
        label = _strip_tags(html.unescape(match.group(2)))
        absolute = normalize_attachment_url(urllib.parse.urljoin(page_url, href))
        combined = (absolute + " " + label).lower()
        if ".hwpx" in combined or "filedown" in combined or "download" in combined:
            out.append({"url": absolute, "label": label})
    seen = set()
    deduped = []
    for row in out:
        key = row["url"]
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped[:MAX_ATTACHMENTS_PER_SOURCE]


def _strip_tags(value: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", value).split())


def normalize_attachment_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    query = urllib.parse.parse_qs(parsed.query)
    if parsed.path.endswith("/attachFiles/viewer/skin/doc.html"):
        fn = (query.get("fn") or [""])[0]
        rs = (query.get("rs") or [""])[0]
        if fn and rs:
            return urllib.parse.urljoin(url, rs.rstrip("/") + "/" + fn)
    return url


def _matches(label: str, patterns: list[str]) -> bool:
    if not patterns:
        return True
    lowered = label.lower()
    return any(str(p).lower() in lowered for p in patterns)


def _safe_name(source_id: str, index: int) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", source_id)[:80] + f"-{index:02d}.hwpx"


def acquire(seed: dict, *, sleep_seconds: float = 0.4) -> dict:
    records = []
    observations = []
    with tempfile.TemporaryDirectory(prefix="p417-corpus-") as td:
        root = Path(td)
        for source in seed.get("sources", []):
            source_id = str(source["source_id"])
            try:
                page, page_meta = fetch(source["source_page"], MAX_PAGE_BYTES)
                links = discover_links(source["source_page"], page)
                links = [x for x in links if _matches(x["label"], source.get("expected_attachment_patterns") or [])]
            except Exception as exc:
                observations.append({"source_id": source_id, "status": "SOURCE_PAGE_ERROR", "error_class": type(exc).__name__})
                continue
            accepted = 0
            for index, link in enumerate(links):
                try:
                    data, meta = fetch(link["url"], MAX_DOCUMENT_BYTES)
                    target = root / _safe_name(source_id, index)
                    target.write_bytes(data)
                    record = analyze_hwpx(
                        target,
                        source={
                            **source,
                            "title": link["label"],
                            "attachment_url": meta["final_url"],
                            "license_state": "SOURCE_TERMS_REVIEW_REQUIRED",
                        },
                    )
                    records.append(record)
                    observations.append({
                        "source_id": source_id,
                        "label": link["label"],
                        "status": "ACQUIRED_AND_ANALYZED",
                        "document_sha256": record["document_sha256"],
                        "record_sha256": record["record_sha256"],
                        "archetype": record["archetype"]["archetype"],
                    })
                    accepted += 1
                except Exception as exc:
                    observations.append({
                        "source_id": source_id,
                        "label": link["label"],
                        "status": "ATTACHMENT_ERROR",
                        "error_class": type(exc).__name__,
                    })
                time.sleep(max(0.0, sleep_seconds))
            if accepted == 0:
                observations.append({"source_id": source_id, "status": "NO_MATCHING_HWPX_ACQUIRED", "discovered_link_count": len(links)})
            time.sleep(max(0.0, sleep_seconds))
    dataset = build_dataset(records)
    dataset["acquisition_observations"] = observations
    dataset["source_seed_count"] = len(seed.get("sources", []))
    dataset["acquisition_mode"] = "BOUNDED_EPHEMERAL_OFFICIAL_SOURCE"
    return dataset


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="benchmarks/p417_public_corpus_seed.json")
    ap.add_argument("--out", required=True)
    ap.add_argument("--minimum-documents", type=int, default=1)
    ap.add_argument("--minimum-institutions", type=int, default=1)
    ap.add_argument("--sleep-seconds", type=float, default=0.4)
    args = ap.parse_args()
    seed = json.loads(Path(args.seed).read_text(encoding="utf-8"))
    dataset = acquire(seed, sleep_seconds=args.sleep_seconds)
    Path(args.out).write_text(json.dumps(dataset, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "record_count": dataset["record_count"],
        "institution_count": dataset["institution_count"],
        "archetype_counts": dataset["archetype_counts"],
        "dataset_sha256": dataset["dataset_sha256"],
    }, ensure_ascii=False))
    return 0 if (
        dataset["record_count"] >= args.minimum_documents
        and dataset["institution_count"] >= args.minimum_institutions
    ) else 2


if __name__ == "__main__":
    raise SystemExit(main())
