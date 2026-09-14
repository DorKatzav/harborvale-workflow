"""Crew 2 on paper: three agents, five wired tasks, no temperature, and no LLM call anywhere here."""

from pathlib import Path

import yaml

CONFIG = Path(__file__).resolve().parent.parent / "crews" / "scientist" / "config"
AGENTS = ["feature_engineer", "ml_engineer", "model_governance_officer"]
TASKS = ["validate", "engineer_features", "train_compare", "evaluation_report", "model_card"]


def test_agents_yaml_defines_the_scientist_crew():
    agents = yaml.safe_load((CONFIG / "agents.yaml").read_text(encoding="utf-8"))
    assert set(agents) >= set(AGENTS)
    for name, spec in agents.items():
        assert spec["role"] and spec["goal"] and spec["backstory"], name
        assert "temperature" not in spec, name


def test_tasks_yaml_wires_tasks_to_agents_in_the_planned_order():
    tasks = yaml.safe_load((CONFIG / "tasks.yaml").read_text(encoding="utf-8"))
    agents = yaml.safe_load((CONFIG / "agents.yaml").read_text(encoding="utf-8"))
    assert list(tasks) == TASKS
    for name, spec in tasks.items():
        assert spec["agent"] in agents, name
        assert "{out_dir}" in spec["description"] or "{contract_json}" in spec["description"], name
        assert spec["expected_output"], name


def test_the_crew_never_points_an_agent_at_the_raw_data():
    """The seam in prose as well as in code: nothing in Crew 2's instructions mentions the workbook."""
    text = "".join(
        (CONFIG / f).read_text(encoding="utf-8") for f in ("agents.yaml", "tasks.yaml")
    ).lower()
    assert "data/raw" not in text and ".xlsx" not in text


def test_crew_builds_without_calling_the_llm(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
    from crews.scientist.crew import ScientistCrew

    crew = ScientistCrew().crew()
    assert len(crew.agents) == 3 and len(crew.tasks) == 5
    assert all(a.max_iter == 8 for a in crew.agents)
    assert all(not a.allow_delegation for a in crew.agents)
    assert {t.name for t in crew.tasks[-1].tools} == {"write_model_card"}
    assert {t.name for t in crew.tasks[2].tools} == {"train_and_evaluate"}
