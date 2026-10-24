#!/usr/bin/env python3
"""Opt-in local Ollama evaluation over a private image manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit

from PIL import Image

# Support direct execution from a source checkout without installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from local_eval_metrics import score_item, summarize

from moodtag_core.prompts import read_system_prompt, render_user_prompt
from moodtag_core.provider import OllamaVisionClient, moodtag_json_schema
from moodtag_core.taxonomy import load_profile_taxonomy


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="JSON array of {id, path} records")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--gold",
        type=Path,
        help="Optional human-authored JSON object keyed by image ID",
    )
    parser.add_argument("--model", required=True)
    parser.add_argument("--endpoint", default="http://127.0.0.1:11434")
    parser.add_argument(
        "--profile", choices=("editorial", "default"), default="editorial"
    )
    parser.add_argument(
        "--preset",
        choices=("smoke", "qwen-instruct", "mlx-default"),
        default="qwen-instruct",
    )
    parser.add_argument(
        "--think",
        choices=("preset", "true", "false"),
        default="preset",
        help="Override the preset thinking setting for controlled comparisons",
    )
    parser.add_argument(
        "--num-ctx",
        type=int,
        help="Optional requested context window; model capacity is reported separately",
    )
    parser.add_argument(
        "--num-predict",
        type=int,
        default=800,
        help="Maximum generated tokens (default: 800)",
    )
    parser.add_argument(
        "--image-edge",
        type=int,
        default=768,
        help="Resize to the product preview edge before evaluation",
    )
    parser.add_argument(
        "--timeout", type=int, default=120, help="Per-request timeout in seconds"
    )
    parser.add_argument(
        "--allow-local-images",
        action="store_true",
        help="Confirm that this run may read the manifest's local images",
    )
    args = parser.parse_args()
    if not args.allow_local_images:
        parser.error("pass --allow-local-images to opt in to reading local image files")
    if urlsplit(args.endpoint).hostname not in {"localhost", "127.0.0.1", "::1"}:
        parser.error("evaluation endpoint must be loopback")
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    if not isinstance(manifest, list):
        parser.error("manifest must be a JSON array")
    options = {"num_predict": args.num_predict}
    if args.num_ctx is not None:
        options["num_ctx"] = args.num_ctx
    client = OllamaVisionClient(
        base_url=args.endpoint,
        model=args.model,
        profile=args.profile,
        preset=args.preset,
        options=options,
        timeout=args.timeout,
    )
    if args.think != "preset":
        client.think = args.think == "true"
    ollama_version = client.preflight()
    gold_data = json.loads(args.gold.read_text(encoding="utf-8")) if args.gold else {}
    if not isinstance(gold_data, dict):
        parser.error("gold labels must be a JSON object keyed by image ID")
    taxonomy = load_profile_taxonomy(args.profile)
    taxonomy_bytes = json.dumps(taxonomy, ensure_ascii=False, sort_keys=True).encode()
    schema_bytes = json.dumps(
        moodtag_json_schema(args.profile), sort_keys=True
    ).encode()
    prompt_bytes = (
        read_system_prompt(profile=args.profile)
        + "\n"
        + render_user_prompt(taxonomy, profile=args.profile)
    ).encode()
    records = []
    with TemporaryDirectory(prefix="moodtag-eval-preview-") as preview_directory:
        for item_index, item in enumerate(manifest):
            if not isinstance(item, dict) or not item.get("id") or not item.get("path"):
                parser.error("each manifest record requires id and path")
            original = Path(item["path"]).expanduser()
            image = Path(preview_directory) / f"{item_index}.jpg"
            with Image.open(original) as opened:
                preview = opened.convert("RGB")
                preview.thumbnail(
                    (args.image_edge, args.image_edge), Image.Resampling.LANCZOS
                )
                preview.save(image, format="JPEG", quality=90)
                preview_dimensions = list(preview.size)
            preview_bytes = image.stat().st_size
            started = time.monotonic()
            try:
                result = client.analyze(image, taxonomy, retries=0, max_tags=15)
                analysis = result.__dict__
                gold = gold_data.get(str(item["id"]))
                metrics = score_item(analysis, gold) if isinstance(gold, dict) else None
                if metrics is not None:
                    metrics["duplicate_tag_count"] = client.runtime.get(
                        "raw_duplicate_tag_count", 0
                    )
                records.append(
                    {
                        "image_id": str(item["id"]),
                        "ok": True,
                        "analysis": analysis,
                        "runtime": dict(client.runtime),
                        "image": {
                            "preview_dimensions": preview_dimensions,
                            "preview_bytes": preview_bytes,
                            "preview_format": "JPEG",
                            "jpeg_quality": 90,
                        },
                        "metrics": metrics,
                        "elapsed_ms": round((time.monotonic() - started) * 1000),
                    }
                )
            except Exception as exc:  # report only a sanitized exception class/message
                records.append(
                    {
                        "image_id": str(item["id"]),
                        "ok": False,
                        "error_type": type(exc).__name__,
                        "image": {
                            "preview_dimensions": preview_dimensions,
                            "preview_bytes": preview_bytes,
                            "preview_format": "JPEG",
                            "jpeg_quality": 90,
                        },
                        "elapsed_ms": round((time.monotonic() - started) * 1000),
                    }
                )
            report = {
                "schema_version": 1,
                "created_at": datetime.now(UTC).isoformat(),
                "environment": {
                    "ollama_version": client.runtime.get("version", ollama_version),
                    "model": args.model,
                    "model_digest": client.runtime.get("digest", "unknown"),
                    "runner": client.runtime.get("runner", "unknown"),
                    "profile": args.profile,
                    "preset": args.preset,
                    "think": client.think,
                    "effective_options": client.options,
                    "model_context_capacity": client.runtime.get(
                        "model_context_capacity"
                    ),
                    "requested_num_ctx": client.options.get("num_ctx"),
                    "num_predict": client.options.get("num_predict"),
                    "image_edge": args.image_edge,
                    "prompt_chars": {
                        "system": len(read_system_prompt(profile=args.profile)),
                        "user": len(render_user_prompt(taxonomy, profile=args.profile)),
                    },
                    "schema_enabled": True,
                    "prompt_revision": hashlib.sha256(prompt_bytes).hexdigest(),
                    "schema_revision": hashlib.sha256(schema_bytes).hexdigest(),
                    "taxonomy_revision": hashlib.sha256(taxonomy_bytes).hexdigest(),
                    "manifest_sha256": hashlib.sha256(
                        args.manifest.read_bytes()
                    ).hexdigest(),
                },
                "summary": summarize(records),
                "records": records,
            }
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            print(
                f"Completed {item_index + 1}/{len(manifest)}: {item['id']}", flush=True
            )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Wrote {len(records)} local evaluation records to {args.output}")
    return 0 if all(record["ok"] for record in records) else 1


if __name__ == "__main__":
    sys.exit(main())
