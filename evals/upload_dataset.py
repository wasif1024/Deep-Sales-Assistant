"""Sync evals/dataset.jsonl to a LangSmith dataset.

Each line is one example: `inputs.question`, the expectations in `outputs`
(see evaluations.py), and a unique `metadata.case` that identifies it.
Examples are matched by `case`: new cases are created and changed ones are
updated in place, so past experiments still point at the same examples.
Nothing is deleted; cases that are only in LangSmith are listed instead.

Usage:
    uv run python evals/upload_dataset.py
    uv run python evals/upload_dataset.py --dataset my-dataset --file my.jsonl
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

DEFAULT_FILE = Path(__file__).resolve().parent / "dataset.jsonl"
DEFAULT_DATASET = "deep-sales-assistant-regression"


def load_examples(path: Path) -> list[dict[str, Any]]:
    """Read and check the JSONL file. Raises ValueError on a malformed line."""
    examples: list[dict[str, Any]] = []
    seen: set[str] = set()
    for number, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        example = json.loads(line)
        case = (example.get("metadata") or {}).get("case")
        question = (example.get("inputs") or {}).get("question")
        if not isinstance(case, str) or not case:
            raise ValueError(f"Line {number}: metadata.case is required.")
        if case in seen:
            raise ValueError(f"Line {number}: duplicate case {case!r}.")
        if not isinstance(question, str) or not question.strip():
            raise ValueError(f"Line {number}: inputs.question is required.")
        seen.add(case)
        example.setdefault("outputs", {})
        examples.append(example)
    return examples


def plan_sync(
    local: list[Mapping[str, Any]], remote: Iterable[Any]
) -> tuple[list[Mapping[str, Any]], list[tuple[Any, Mapping[str, Any]]], list[str]]:
    """Return (to_create, to_update as (example_id, example), remote_only cases)."""
    remote_by_case = {
        (r.metadata or {}).get("case"): r for r in remote if (r.metadata or {}).get("case")
    }
    to_create, to_update = [], []
    for example in local:
        existing = remote_by_case.pop(example["metadata"]["case"], None)
        if existing is None:
            to_create.append(example)
        elif (existing.inputs, existing.outputs or {}) != (example["inputs"], example["outputs"]):
            to_update.append((existing.id, example))
    return to_create, to_update, sorted(remote_by_case)


def main() -> None:
    from dotenv import load_dotenv
    from langsmith import Client

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dataset", default=DEFAULT_DATASET, help="LangSmith dataset name")
    parser.add_argument("--file", type=Path, default=DEFAULT_FILE, help="JSONL file to upload")
    args = parser.parse_args()

    load_dotenv()
    examples = load_examples(args.file)
    client = Client()

    if client.has_dataset(dataset_name=args.dataset):
        dataset = client.read_dataset(dataset_name=args.dataset)
    else:
        dataset = client.create_dataset(
            args.dataset,
            description="Deep Sales Assistant regression set (synced from evals/dataset.jsonl).",
        )

    to_create, to_update, remote_only = plan_sync(
        examples, client.list_examples(dataset_id=dataset.id)
    )
    if to_create:
        client.create_examples(dataset_id=dataset.id, examples=to_create)
    for example_id, example in to_update:
        client.update_example(
            example_id,
            inputs=example["inputs"],
            outputs=example["outputs"],
            metadata=example["metadata"],
        )

    print(f"Dataset {args.dataset}: {len(to_create)} created, {len(to_update)} updated, "
          f"{len(examples) - len(to_create) - len(to_update)} unchanged.")
    if remote_only:
        print(f"Only in LangSmith (left as is): {', '.join(remote_only)}")


if __name__ == "__main__":
    main()
