from __future__ import annotations

from typing import List, Optional, Any, Dict

_rag_instance: Optional[Any] = None
_rag_data_sources: List[str] = []
_rag_indexing: bool = False
_rag_started_at: Optional[str] = None
_rag_indexed_files: Dict[int, str] = {}


def set_rag_instance(instance: Any, data_source: List[str]) -> None:
    global _rag_instance, _rag_data_source
    _rag_instance = instance
    _rag_data_source = list(data_source)


def get_rag_instance() -> Optional[Any]:
    return _rag_instance


def get_rag_data_sources() -> List[str]:
    return list(_rag_data_sources)


def set_index_status(indexing: bool, started_at: Optional[str] = None) -> None:
    global _rag_indexing, _rag_started_at
    _rag_indexing = indexing
    if started_at is not None:
        _rag_started_at = started_at


def get_index_status() -> Dict[str, Optional[str] | bool]:
    return {"indexing": _rag_indexing, "started_at": _rag_started_at}


def set_indexed_files(file_ids: List[int], indexed_at: str) -> None:
    for file_id in file_ids:
        _rag_indexed_files[int(file_id)] = indexed_at


def get_indexed_files() -> Dict[int, str]:
    return dict(_rag_indexed_files)
