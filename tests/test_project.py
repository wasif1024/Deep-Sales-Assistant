"""Project wiring: graphs load, subagents are gated, skills are well-formed."""

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def test_langgraph_json_points_at_real_graphs():
    config = json.loads((ROOT / "langgraph.json").read_text())
    assert config["dependencies"] == ["."]
    for target in config["graphs"].values():
        module, attr = target.removeprefix("./").split(":")
        assert (ROOT / module).exists()
        assert attr


def test_newsletter_graph_builds():
    import newsletter_agent_graph

    assert newsletter_agent_graph.graph is not None


def test_agent_module_imports():
    import agent

    assert callable(agent.make_graph)


def test_gated_tools_only_live_on_their_specialists():
    from deepagents.backends import StateBackend

    from subagents import build_subagents

    specs = {s["name"]: s for s in build_subagents(StateBackend(), mail_tools=[])}
    assert set(specs) == {"chinook-analyst", "inbox-manager", "quote-reviewer"}
    assert set(specs["chinook-analyst"]["interrupt_on"]) == {"add_customer"}
    assert set(specs["inbox-manager"]["interrupt_on"]) == {"mail_create_draft"}
    assert "tools" not in specs["quote-reviewer"]


SKILLS = sorted((ROOT / "skills").glob("*/SKILL.md"))


@pytest.mark.parametrize("skill", SKILLS, ids=lambda p: p.parent.name)
def test_skill_front_matter(skill):
    text = skill.read_text()
    assert text.startswith("---\n")
    front_matter = text.split("---\n")[1]
    fields = dict(
        line.split(":", 1) for line in front_matter.strip().splitlines() if ":" in line
    )
    assert fields["name"].strip() == skill.parent.name
    assert len(fields["description"].strip()) > 40


def test_there_are_three_skills():
    assert [s.parent.name for s in SKILLS] == [
        "rfq-quote",
        "territory-report",
        "weekly-newsletter",
    ]
