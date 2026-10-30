"""The regression dataset in evals/ is well-formed and can be scored."""

from types import SimpleNamespace

import pytest

from evals.upload_dataset import DEFAULT_FILE, load_examples, plan_sync
from evaluations import expected_quote

EXAMPLES = load_examples(DEFAULT_FILE)
GATED_TOOLS = {"add_customer", "mail_create_draft"}


@pytest.mark.parametrize("example", EXAMPLES, ids=lambda e: e["metadata"]["case"])
def test_example_expectations_are_well_formed(example, temp_db):
    outputs = example["outputs"]
    assert set(outputs) <= {"required_tools", "required_facts", "pending_action", "quote"}
    assert outputs, "an example with no expectations scores nothing"
    if "pending_action" in outputs:
        assert outputs["pending_action"]["name"] in GATED_TOOLS
    if "quote" in outputs:
        # Raises if a line can't be priced exactly from the database.
        expected_quote(outputs["quote"]["lines"])


def test_dataset_covers_both_sides_of_the_discount_threshold(temp_db):
    quantities = {
        expected_quote(e["outputs"]["quote"]["lines"])["quantity"]
        for e in EXAMPLES
        if "quote" in e["outputs"]
    }
    assert {49, 50} <= quantities


def test_load_examples_rejects_duplicate_cases(tmp_path):
    line = '{"metadata": {"case": "a"}, "inputs": {"question": "q"}}\n'
    path = tmp_path / "d.jsonl"
    path.write_text(line * 2)

    with pytest.raises(ValueError, match="duplicate"):
        load_examples(path)


def test_plan_sync_creates_updates_and_never_deletes():
    local = [
        {"metadata": {"case": "same"}, "inputs": {"question": "q1"}, "outputs": {}},
        {"metadata": {"case": "changed"}, "inputs": {"question": "new"}, "outputs": {}},
        {"metadata": {"case": "added"}, "inputs": {"question": "q3"}, "outputs": {}},
    ]
    remote = [
        SimpleNamespace(id="1", metadata={"case": "same"}, inputs={"question": "q1"}, outputs={}),
        SimpleNamespace(id="2", metadata={"case": "changed"}, inputs={"question": "old"}, outputs={}),
        SimpleNamespace(id="3", metadata={"case": "removed"}, inputs={"question": "q"}, outputs={}),
    ]

    to_create, to_update, remote_only = plan_sync(local, remote)

    assert [e["metadata"]["case"] for e in to_create] == ["added"]
    assert [(i, e["metadata"]["case"]) for i, e in to_update] == [("2", "changed")]
    assert remote_only == ["removed"]
