from types import SimpleNamespace

from pathlib import Path


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


def test_exec_python_code_writes_generated_files_to_configured_upload_root(tmp_path, monkeypatch):
    import backend.tools as tools

    upload_root = tmp_path / "configured-chat-uploads"
    monkeypatch.setenv("CHAT_UPLOAD_ROOT", str(upload_root))
    monkeypatch.chdir(tmp_path)

    result = tools.exec_python_code(
        "from pathlib import Path\n"
        "path = Path('./backend/chat_uploads/chart.png')\n"
        "path.parent.mkdir(parents=True, exist_ok=True)\n"
        "path.write_bytes(b'png')\n"
        "print(f'file_path: {path}')\n"
    )

    generated = list(upload_root.glob("chart_*.png"))
    assert len(generated) == 1
    assert generated[0].read_bytes() == b"png"
    assert generated[0].as_posix() in result
    assert not (tmp_path / "backend" / "chat_uploads" / "chart.png").exists()
