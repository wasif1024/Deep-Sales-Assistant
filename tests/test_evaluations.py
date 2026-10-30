from decimal import Decimal
from types import SimpleNamespace

import pytest

import evaluations
from evaluations import (
    DraftReview,
    PairwiseVerdict,
    _evaluation_output,
    agent_fingerprint,
    draft_preference,
    draft_quality,
    expected_pending_action,
    expected_quote,
    quote_accuracy,
    required_facts,
    required_tools,
    tool_call_order,
)


def test_evaluation_output_reads_final_answer_and_nested_tool_calls():
    chunks = [
        {
            "event": "values",
            "data": {
                "messages": [
                    {"type": "human", "content": "Find the customer."},
                    {
                        "type": "ai",
                        "content": "The customer is Jane Doe.",
                        "tool_calls": [{"name": "query_database"}],
                    },
                ]
            },
        },
        {
            "event": "debug",
            "data": {
                "payload": {
                    "messages": [
                        {
                            "type": "ai",
                            "tool_calls": [
                                {"function": {"name": "mail_search"}}
                            ],
                        }
                    ]
                }
            },
        },
    ]

    assert _evaluation_output(chunks) == {
        "answer": "The customer is Jane Doe.",
        "tool_calls": ["query_database", "mail_search"],
        "trajectory": [
            {"name": "query_database", "args": {}},
            {"name": "mail_search", "args": {}},
        ],
        "pending_actions": [],
    }


def _approval(name, **args):
    return {
        "value": {
            "action_requests": [{"name": name, "args": args, "description": "..."}],
            "review_configs": [{"action_name": name, "allowed_decisions": ["approve"]}],
        },
        "id": "interrupt-1",
    }


def test_evaluation_output_records_approval_requests_once():
    draft = _approval("mail_create_draft", to="a@b.example", subject="Quote", body="Total $1.00")
    chunks = [{"event": "values", "data": {"messages": [], "__interrupt__": [draft]}}]
    state = {"values": {}, "tasks": [{"interrupts": [draft]}], "interrupts": [draft]}

    output = _evaluation_output(chunks, state)

    assert output["pending_actions"] == [
        {"name": "mail_create_draft", "args": {"to": "a@b.example", "subject": "Quote", "body": "Total $1.00"}}
    ]


def test_evaluation_output_finds_approval_requests_in_thread_state_only():
    state = {"tasks": [{"interrupts": [_approval("add_customer", email="new@x.example")]}]}

    output = _evaluation_output([], state)

    assert output["pending_actions"] == [{"name": "add_customer", "args": {"email": "new@x.example"}}]


def test_required_tools_checks_dataset_expectations():
    run = {"outputs": {"tool_calls": ["query_database"]}}
    example = {"outputs": {"required_tools": ["query_database", "mail_search"]}}

    result = required_tools(run, example)

    assert result["score"] == 0
    assert "mail_search" in result["comment"]


def test_required_facts_checks_final_response():
    run = {"outputs": {"answer": "The 10% discount applies to 50 tracks."}}
    example = {"outputs": {"required_facts": ["10% discount", "50 tracks"]}}

    assert required_facts(run, example)["score"] == 1


def _run(answer="", pending=()):
    return {"outputs": {"answer": answer, "pending_actions": list(pending)}}


def _draft(body, to="Tim Goyer <tgoyer@apple.com>"):
    return {"name": "mail_create_draft", "args": {"to": to, "subject": "Your quote", "body": body}}


def test_pending_action_matches_name_and_contained_args():
    example = {"outputs": {"pending_action": {"name": "mail_create_draft", "args": {"to": "TGOYER@apple.com"}}}}

    assert expected_pending_action(_run(pending=[_draft("Hi")]), example)["score"] == 1


@pytest.mark.parametrize(
    "pending",
    [
        [],
        [{"name": "add_customer", "args": {"email": "tgoyer@apple.com"}}],
        [_draft("Hi", to="someone@else.example")],
    ],
    ids=["finished-without-pausing", "wrong-tool", "wrong-recipient"],
)
def test_pending_action_fails_on_the_wrong_pause(pending):
    example = {"outputs": {"pending_action": {"name": "mail_create_draft", "args": {"to": "tgoyer@apple.com"}}}}

    assert expected_pending_action(_run(pending=pending), example)["score"] == 0


def test_evaluators_skip_examples_without_expectations():
    assert expected_pending_action(_run(), {"outputs": {}})["score"] is None
    assert quote_accuracy(_run(), {"outputs": {}})["score"] is None


def test_expected_quote_prices_from_the_database(temp_db):
    quote = expected_quote([{"genre": "Blues", "quantity": 50}])

    assert quote["subtotal"] == Decimal("49.50")
    assert quote["discount"] == Decimal("4.95")
    assert quote["total"] == Decimal("44.55")


def test_expected_quote_uses_the_genres_real_price(temp_db):
    quote = expected_quote([{"genre": "TV Shows", "quantity": 10}])

    assert quote["lines"][0]["unit_price"] == Decimal("1.99")
    assert quote["discount"] == 0
    assert quote["total"] == Decimal("19.90")


@pytest.mark.parametrize(
    "lines",
    [[{"genre": "Opera", "quantity": 2}], [{"genre": "Polka", "quantity": 1}]],
    ids=["more-than-available", "unknown-genre"],
)
def test_expected_quote_rejects_unpriceable_lines(temp_db, lines):
    with pytest.raises(ValueError):
        expected_quote(lines)


BLUES_50 = {"outputs": {"quote": {"lines": [{"genre": "Blues", "quantity": 50}]}}}
CLASSICAL_49 = {"outputs": {"quote": {"lines": [{"genre": "Classical", "quantity": 49}]}}}


def test_quote_accuracy_passes_a_correct_draft(temp_db):
    body = "50 Blues tracks x $0.99 = $49.50\nVolume discount (10%): -$4.95\nTotal: $44.55"

    result = quote_accuracy(_run(pending=[_draft(body)]), BLUES_50)

    assert result["score"] == 1
    assert "draft" in result["comment"]


def test_quote_accuracy_fails_when_the_discount_is_missing(temp_db):
    body = "50 Blues tracks x $0.99 = $49.50\nTotal: $49.50"

    assert quote_accuracy(_run(pending=[_draft(body)]), BLUES_50)["score"] == 0


def test_quote_accuracy_fails_a_discount_below_the_threshold(temp_db):
    body = "49 Classical tracks x $0.99 = $48.51\nDiscount: -$4.85\nTotal: $43.66"

    result = quote_accuracy(_run(pending=[_draft(body)]), CLASSICAL_49)

    assert result["score"] == 0
    assert "below 50" in result["comment"]


def test_quote_accuracy_allows_a_cent_of_rounding_and_reads_the_answer(temp_db):
    answer = "The quote comes to 1,000.00 for something else, and 44.56 USD in total."

    result = quote_accuracy(_run(answer=answer), BLUES_50)

    assert result["score"] == 1
    assert "answer" in result["comment"]


def test_trajectory_keeps_order_args_and_dedupes_repeated_chunks():
    lookup = {"id": "c1", "name": "query_chinook", "args": {"sql": "SELECT 1"}}
    task = {"id": "c2", "function": {"name": "task", "arguments": '{"subagent_type": "quote-reviewer"}'}}
    chunks = [
        {"event": "values", "data": {"messages": [{"type": "ai", "tool_calls": [lookup]}]}},
        {"event": "values", "data": {"messages": [
            {"type": "ai", "tool_calls": [lookup]},
            {"type": "ai", "tool_calls": [task]},
        ]}},
    ]

    assert _evaluation_output(chunks)["trajectory"] == [
        {"name": "query_chinook", "args": {"sql": "SELECT 1"}},
        {"name": "task", "args": {"subagent_type": "quote-reviewer"}},
    ]


def _call(name, **args):
    return {"name": name, "args": args}


PRIYA = {"email": "priya.raman@pulsefit-studios.example", "last_name": "Raman"}
LOOKUP_PRIYA = _call("query_chinook", sql="SELECT * FROM Customer WHERE Email = 'priya.raman@pulsefit-studios.example'")
REVIEW = _call("task", subagent_type="quote-reviewer", description="Check the quote")
PRICED_DRAFT = _call("mail_create_draft", to="tgoyer@apple.com", subject="Quote", body="Total: $29.70")


def _order_run(trajectory=(), pending=()):
    return {"outputs": {"trajectory": list(trajectory), "pending_actions": list(pending)}}


def test_tool_order_passes_lookup_then_add_customer(temp_db):
    run = _order_run([LOOKUP_PRIYA], pending=[_call("add_customer", **PRIYA)])

    assert tool_call_order(run, {})["score"] == 1


def test_tool_order_accepts_a_lookup_by_last_name(temp_db):
    by_name = _call("query_chinook", sql="SELECT * FROM Customer WHERE LastName LIKE '%raman%'")
    run = _order_run([by_name], pending=[_call("add_customer", **PRIYA)])

    assert tool_call_order(run, {})["score"] == 1


def test_tool_order_fails_add_customer_without_a_lookup(temp_db):
    run = _order_run([_call("query_chinook", sql="SELECT * FROM Genre")], pending=[_call("add_customer", **PRIYA)])

    result = tool_call_order(run, {})

    assert result["score"] == 0
    assert "without first searching" in result["comment"]


def test_tool_order_fails_adding_an_existing_customer(temp_db):
    tim = {"email": "tgoyer@apple.com", "last_name": "Goyer"}
    lookup = _call("query_chinook", sql="SELECT * FROM Customer WHERE Email = 'tgoyer@apple.com'")

    result = tool_call_order(_order_run([lookup], pending=[_call("add_customer", **tim)]), {})

    assert result["score"] == 0
    assert "already exists" in result["comment"]


def test_tool_order_requires_review_before_a_priced_draft(temp_db):
    assert tool_call_order(_order_run([REVIEW], pending=[PRICED_DRAFT]), {})["score"] == 1
    assert tool_call_order(_order_run([], pending=[PRICED_DRAFT]), {})["score"] == 0
    # Reviewing after the draft doesn't count.
    assert tool_call_order(_order_run([PRICED_DRAFT, REVIEW]), {})["score"] == 0


def test_tool_order_skips_runs_without_gated_writes(temp_db):
    unpriced = _call("mail_create_draft", to="a@b.example", subject="Hi", body="Thanks, we'll be in touch.")

    assert tool_call_order(_order_run([LOOKUP_PRIYA], pending=[unpriced]), {})["score"] is None


class FakeJudge:
    def __init__(self, result):
        self.result, self.prompts = result, []

    def invoke(self, messages):
        self.prompts.append(messages)
        return self.result


@pytest.fixture
def judge(monkeypatch):
    """Replace the judge model; set `.result` to what it should return."""
    fake = FakeJudge(None)
    monkeypatch.setattr(evaluations, "_judge", lambda schema: fake)
    return fake


def _review(**failed):
    checks = {name: True for name in DraftReview.model_fields if name != "issues"}
    checks.update(failed)
    return DraftReview(**checks, issues=["No next step."] if failed else [])


def test_draft_quality_scores_the_fraction_of_checks_passed(judge, temp_db):
    judge.result = _review(next_step=False)
    run = _run(pending=[_draft("Total: $44.55")])
    example = {"inputs": {"question": "50 Blues tracks?"}, **BLUES_50}

    result = draft_quality(run, example)

    assert result["score"] == round(6 / 7, 3)
    assert "next_step" in result["comment"]
    # The judge is given the correct numbers to compare against.
    assert "Grand total: $44.55" in judge.prompts[0][1][1]


def test_draft_quality_skips_runs_without_a_draft(judge):
    assert draft_quality(_run(answer="Hi"), {"outputs": {}})["score"] is None
    assert judge.prompts == []


def _experiment_run(run_id, experiment, body):
    return SimpleNamespace(id=run_id, session_id=experiment, outputs={"pending_actions": [_draft(body)]})


def test_draft_preference_scores_the_preferred_run(judge, temp_db):
    judge.result = PairwiseVerdict(preferred=2, reason="B has the discount.")
    runs = [
        _experiment_run("a1", "exp-a", "Total: $49.50"),
        _experiment_run("a2", "exp-a", "repetition, ignored"),
        _experiment_run("b1", "exp-b", "Total: $44.55"),
    ]

    result = draft_preference(runs, SimpleNamespace(inputs={"question": "q"}, outputs=BLUES_50["outputs"]))

    assert result["scores"] == {"a1": 0, "b1": 1}
    assert result["comment"] == "B has the discount."
    assert "repetition" not in judge.prompts[0][1][1]


def test_draft_preference_needs_two_experiments(judge):
    with pytest.raises(ValueError):
        draft_preference([_experiment_run("a1", "exp-a", "x")], SimpleNamespace(inputs={}, outputs={}))


def test_agent_fingerprint_changes_with_any_prompt_file(tmp_path):
    (tmp_path / "skills" / "rfq-quote").mkdir(parents=True)
    skill = tmp_path / "skills" / "rfq-quote" / "SKILL.md"
    skill.write_text("v1")
    (tmp_path / "AGENTS.md").write_text("manual")
    (tmp_path / "unrelated.txt").write_text("x")

    before = agent_fingerprint(tmp_path)
    (tmp_path / "unrelated.txt").write_text("y")
    assert agent_fingerprint(tmp_path) == before

    skill.write_text("v2")
    assert agent_fingerprint(tmp_path) != before
