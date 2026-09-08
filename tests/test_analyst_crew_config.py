"""The crew definition is validated without any LLM call: agents on paper, wired tasks, no temperature."""

from pathlib import Path

import yaml

CONFIG = Path(__file__).resolve().parent.parent / "crews" / "analyst" / "config"


def test_agents_yaml_defines_the_analyst_crew():
    agents = yaml.safe_load((CONFIG / "agents.yaml").read_text())
    assert set(agents) >= {"data_quality_engineer", "business_analyst", "data_steward"}
    for name, spec in agents.items():
        assert spec["role"] and spec["goal"] and spec["backstory"], name
        assert "temperature" not in spec, name


def test_tasks_yaml_wires_tasks_to_agents_and_tools():
    tasks = yaml.safe_load((CONFIG / "tasks.yaml").read_text())
    assert list(tasks) == ["profile_and_clean", "explore", "write_insights", "author_contract"]
    agents = yaml.safe_load((CONFIG / "agents.yaml").read_text())
    for name, spec in tasks.items():
        assert spec["agent"] in agents, name
        assert "{raw_path}" in spec["description"] or "{out_dir}" in spec["description"], name
        assert spec["expected_output"], name


def test_crew_builds_without_calling_the_llm(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
    from crews.analyst.crew import AnalystCrew

    crew = AnalystCrew().crew()
    assert len(crew.agents) == 3 and len(crew.tasks) == 4
    assert all(a.max_iter == 8 for a in crew.agents)
    assert all(not a.allow_delegation for a in crew.agents)
    assert crew.tasks[0].tools and crew.tasks[2].tools and crew.tasks[3].tools
    assert {t.name for t in crew.tasks[3].tools} == {"build_contract_measured", "write_contract_human_fields"}
