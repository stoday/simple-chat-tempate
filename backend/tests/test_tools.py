from types import SimpleNamespace


def test_build_agent_normalizes_empty_system_prompt(client, monkeypatch):
    import backend.tools as tools

    captured = {}

    def fake_agents(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace()

    monkeypatch.setattr(tools, "build_documents_rag_tool", lambda: SimpleNamespace())
    monkeypatch.setattr(tools.akasha, "agents", fake_agents)

    tools.build_agent(stream=True)

    assert captured["system_prompt"] == ""
    assert captured["stream"] is True
