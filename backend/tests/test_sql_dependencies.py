from pathlib import Path


def test_sql_markdown_dependency_is_declared():
    requirements = (
        Path(__file__).resolve().parents[1] / "requirements.txt"
    ).read_text(encoding="utf-8")

    assert "tabulate==0.9.0" in requirements.splitlines()
