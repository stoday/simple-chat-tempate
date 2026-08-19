from __future__ import annotations

import sqlite3
from pathlib import Path


def get_searchable_rag_sources(
    db: sqlite3.Connection,
    upload_root: Path,
    embedding_model: str,
) -> list[Path]:
    """Return existing files whose persisted index matches the active model."""
    rows = db.execute(
        "SELECT file_path FROM rag_file "
        "WHERE index_status = 'indexed' AND indexed_embedding_model = ? "
        "ORDER BY created_at DESC",
        (embedding_model,),
    ).fetchall()
    sources: list[Path] = []
    for row in rows:
        path = upload_root / row["file_path"]
        if path.exists() and path.is_file():
            sources.append(path)
    return sources
