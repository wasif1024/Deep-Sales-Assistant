"""Compare two experiments' replies with a pairwise LLM judge.

Run evaluations.py once per version you want to compare (for example before
and after a prompt change, or with chinook-analyst on Haiku vs Sonnet), then
pass both experiment names. Both must be on the same dataset. The order of
the two replies is randomized for every example so the judge can't favour a
position.

Usage:
    uv run python evals/compare.py <experiment-a> <experiment-b>
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main() -> None:
    from dotenv import load_dotenv
    from langsmith import evaluate

    from evaluations import draft_preference

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("experiment_a")
    parser.add_argument("experiment_b")
    parser.add_argument("--max-concurrency", type=int, default=1)
    args = parser.parse_args()

    load_dotenv()
    evaluate(
        (args.experiment_a, args.experiment_b),
        evaluators=[draft_preference],
        randomize_order=True,
        max_concurrency=args.max_concurrency,
    )
    print("Done. Open either experiment in LangSmith to see the pairwise results.")


if __name__ == "__main__":
    main()
