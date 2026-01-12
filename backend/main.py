import asyncio
import json
import re
from urllib.parse import urlparse
import multiprocessing
import queue as py_queue
import traceback
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Union
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, UploadFile, status, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr, Field, validator

from .database import get_connection, get_db, init_db, load_llm_config
from .rag_state import (
    get_index_status,
    get_indexed_files,
    set_index_status,
    set_indexed_files,
    set_rag_instance,
)

import akasha
from .tools import get_agent

load_dotenv()

SECRET_KEY = os.environ.get("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY environment variable is not set")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer_scheme = HTTPBearer(auto_error=False)

app = FastAPI(title="SimpleChat Auth API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class UserResponse(BaseModel):
    id: int
    email: EmailStr
    display_name: Optional[str] = None
    role: str
    created_at: str
    last_login_at: Optional[str] = None


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: Optional[str] = Field(default=None, max_length=120)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class UpdateUserRequest(BaseModel):
    display_name: Optional[str] = Field(default=None, max_length=120)
    role: Optional[str] = Field(default=None)
    password: Optional[str] = Field(default=None, min_length=8, max_length=128)
    email: Optional[EmailStr] = None

    @validator("password", pre=True)
    def empty_password_to_none(cls, value):
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        return value


class DeleteResponse(BaseModel):
    detail: str


class ConversationResponse(BaseModel):
    id: int
    user_id: int
    title: str
    created_at: str
    updated_at: str
    message_count: Optional[int] = None


class ConversationCreateRequest(BaseModel):
    title: Optional[str] = Field(default=None, max_length=200)


class ConversationUpdateRequest(BaseModel):
    title: Optional[str] = Field(default=None, max_length=200)


class MessageFileResponse(BaseModel):
    id: int
    file_name: str
    file_path: str
    mime_type: Optional[str] = None
    size_bytes: Optional[int] = None


class RagFileResponse(BaseModel):
    id: int
    file_name: str
    file_path: str
    mime_type: Optional[str] = None
    size_bytes: Optional[int] = None
    uploaded_by: Optional[int] = None
    created_at: str


class RagIndexRequest(BaseModel):
    file_ids: Optional[List[int]] = None
    rebuild: bool = False


class RagIndexResponse(BaseModel):
    ok: bool
    detail: str
    file_ids: List[int] = Field(default_factory=list)
    indexing: bool = False
    started_at: Optional[str] = None


class RagIndexedFile(BaseModel):
    file_id: int
    indexed_at: str


class RagIndexStatusResponse(BaseModel):
    indexing: bool
    started_at: Optional[str] = None
    indexed_files: List[RagIndexedFile] = Field(default_factory=list)


class MssqlConfigResponse(BaseModel):
    server: Optional[str] = None
    database: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    use_trusted: bool = False
    updated_at: Optional[str] = None


class MssqlConfigUpdateRequest(BaseModel):
    server: Optional[str] = None
    database: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    use_trusted: Optional[bool] = None


class MssqlTestResponse(BaseModel):
    ok: bool
    detail: str


class LlmConfigResponse(BaseModel):
    model_name: str
    temperature: float
    max_input_tokens: int
    max_output_tokens: int
    system_prompt: Optional[str] = None
    updated_at: Optional[str] = None


class LlmConfigUpdateRequest(BaseModel):
    model_name: Optional[str] = None
    temperature: Optional[float] = None
    max_input_tokens: Optional[int] = None
    max_output_tokens: Optional[int] = None
    system_prompt: Optional[str] = None


@dataclass
class AssistantGeneratedFile:
    file_name: str
    content: Optional[bytes] = None
    text: Optional[str] = None
    mime_type: Optional[str] = None
    source_path: Optional[str] = None


class MessageResponse(BaseModel):
    id: int
    user_id: int
    conversation_id: Optional[int] = None
    sender_type: str
    content: str
    status: str = "completed"
    parent_message_id: Optional[int] = None
    stopped_at: Optional[str] = None
    created_at: str
    files: List[MessageFileResponse] = Field(default_factory=list)


class MessageCreateResponse(BaseModel):
    message: MessageResponse
    reply: Optional[MessageResponse] = None


class MessageListResponse(BaseModel):
    messages: List[MessageResponse]
    conversation_title: Optional[str] = None


BASE_DIR = Path(__file__).resolve().parent
APP_CONFIG_PATH = Path(os.environ.get("APP_CONFIG_PATH", BASE_DIR.parent / "config.toml"))
UPLOAD_ROOT = Path(os.environ.get("CHAT_UPLOAD_ROOT", BASE_DIR / "chat_uploads"))
UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
app.mount("/chat_uploads", StaticFiles(directory=str(UPLOAD_ROOT)), name="chat_uploads")
RAG_UPLOAD_ROOT = Path(os.environ.get("RAG_UPLOAD_ROOT", BASE_DIR / "rag_files"))
RAG_UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
SIMULATED_REPLY_DELAY = float(os.environ.get("SIMULATED_REPLY_DELAY", "1.5"))
DOWNLOAD_LINKS_PLACEHOLDER = "__DOWNLOAD_LINKS__"
pending_generations: Dict[int, Dict[str, object]] = {}


def _fix_missing_upload_links(text: str) -> str:
    if not text:
        return text
    patterns = [
        r"(?:\.\/)?backend\/chat_uploads\/[^\s)\]]+",
        r"\/chat_uploads\/[^\s)\]]+",
        r"https?:\/\/[^\s)\]]+\/chat_uploads\/[^\s)\]]+",
    ]
    matches = []
    for pattern in patterns:
        matches.extend(re.findall(pattern, text))
    cleaned = []
    for raw in matches:
        cleaned.append(raw.rstrip(").,;]"))
    for raw in set(cleaned):
        prefix = None
        rel = None
        if raw.startswith("http"):
            parsed = urlparse(raw)
            if "/chat_uploads/" not in parsed.path:
                continue
            rel = parsed.path.split("/chat_uploads/", 1)[1]
            prefix = raw.split("/chat_uploads/", 1)[0] + "/chat_uploads/"
        elif "backend/chat_uploads/" in raw:
            rel = raw.split("backend/chat_uploads/", 1)[1]
            prefix = raw.split("backend/chat_uploads/", 1)[0] + "backend/chat_uploads/"
        elif "/chat_uploads/" in raw:
            rel = raw.split("/chat_uploads/", 1)[1]
            prefix = raw.split("/chat_uploads/", 1)[0] + "/chat_uploads/"
        elif "chat_uploads/" in raw:
            rel = raw.split("chat_uploads/", 1)[1]
            prefix = raw.split("chat_uploads/", 1)[0] + "chat_uploads/"
        if not rel or prefix is None:
            continue
        current_path = UPLOAD_ROOT / rel
        if current_path.exists():
            continue
        candidates = list(current_path.parent.glob(f"{current_path.stem}_*{current_path.suffix}"))
        if not candidates:
            continue
        latest = max(candidates, key=lambda path: path.stat().st_mtime)
        new_rel = latest.relative_to(UPLOAD_ROOT).as_posix()
        text = text.replace(raw, f"{prefix}{new_rel}")
    return text


def _load_app_config() -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "branding": {
            "title": "SimpleChat",
            "brand_icon": "ph-chat-teardrop-text",
            "empty_state_icon": "ph-sparkle",
            "login_subtitle": "Your premium AI assistant",
        },
        "roles": {
            "allowed": ["admin", "user"],
            "default_role": "user",
        },
        "app": {
            "version": "1.0.1",
        },
        "uploads": {
            "user_extensions": [
                ".pdf",
                ".doc",
                ".docx",
                ".md",
                ".csv",
                ".txt",
                ".xls",
                ".xlsx",
                ".png",
                ".jpg",
                ".jpeg",
            ],
            "rag_extensions": [".pdf", ".doc", ".docx", ".md", ".csv", ".txt", ".xls", ".xlsx"],
        },
        "theme": {
            "profile": "tech",
            "bg_primary": "#0f172a",
            "bg_secondary": "#1e293b",
            "bg_surface": "#334155",
            "bg_input": "rgba(30, 41, 59, 0.7)",
            "text_primary": "#f8fafc",
            "text_secondary": "#94a3b8",
            "text_tertiary": "#64748b",
            "primary": "#8b5cf6",
            "primary_hover": "#7c3aed",
            "accent": "#06b6d4",
            "gradient_primary": "linear-gradient(135deg, #8b5cf6 0%, #06b6d4 100%)",
            "success": "#10b981",
            "warning": "#f59e0b",
            "error": "#ef4444",
            "border_subtle": "rgba(148, 163, 184, 0.1)",
            "border_focus": "rgba(139, 92, 246, 0.5)",
        },
        "theme_presets": {
            "tech": {
                "bg_primary": "#0f172a",
                "bg_secondary": "#1e293b",
                "bg_surface": "#334155",
                "bg_input": "rgba(30, 41, 59, 0.7)",
                "text_primary": "#f8fafc",
                "text_secondary": "#94a3b8",
                "text_tertiary": "#64748b",
                "primary": "#8b5cf6",
                "primary_hover": "#7c3aed",
                "accent": "#06b6d4",
                "gradient_primary": "linear-gradient(135deg, #8b5cf6 0%, #06b6d4 100%)",
                "success": "#10b981",
                "warning": "#f59e0b",
                "error": "#ef4444",
                "border_subtle": "rgba(148, 163, 184, 0.1)",
                "border_focus": "rgba(139, 92, 246, 0.5)",
            },
            "warm": {
                "bg_primary": "#1b1410",
                "bg_secondary": "#2a1f19",
                "bg_surface": "#3a2d26",
                "bg_input": "rgba(58, 45, 38, 0.7)",
                "text_primary": "#fdf6f1",
                "text_secondary": "#d6c1b6",
                "text_tertiary": "#b59d91",
                "primary": "#f97316",
                "primary_hover": "#ea580c",
                "accent": "#facc15",
                "gradient_primary": "linear-gradient(135deg, #f97316 0%, #facc15 100%)",
                "success": "#22c55e",
                "warning": "#f59e0b",
                "error": "#ef4444",
                "border_subtle": "rgba(214, 193, 182, 0.18)",
                "border_focus": "rgba(249, 115, 22, 0.5)",
            },
            "minimal": {
                "bg_primary": "#f8fafc",
                "bg_secondary": "#eef2f6",
                "bg_surface": "#e2e8f0",
                "bg_input": "rgba(226, 232, 240, 0.8)",
                "text_primary": "#0f172a",
                "text_secondary": "#475569",
                "text_tertiary": "#64748b",
                "primary": "#0f172a",
                "primary_hover": "#111827",
                "accent": "#0ea5e9",
                "gradient_primary": "linear-gradient(135deg, #0f172a 0%, #0ea5e9 100%)",
                "success": "#16a34a",
                "warning": "#d97706",
                "error": "#dc2626",
                "border_subtle": "rgba(71, 85, 105, 0.2)",
                "border_focus": "rgba(14, 165, 233, 0.5)",
            },
        },
    }
    if not APP_CONFIG_PATH.exists():
        return defaults
    try:
        try:
            import tomllib  # type: ignore
            with APP_CONFIG_PATH.open("rb") as handle:
                parsed = tomllib.load(handle)
        except ModuleNotFoundError:
            def _simple_toml_load(path: Path) -> dict[str, Any]:
                data: dict[str, Any] = {}
                current = data
                with path.open("r", encoding="utf-8") as handle:
                    for raw_line in handle:
                        line = raw_line.strip()
                        if not line or line.startswith("#"):
                            continue
                        if line.startswith("[") and line.endswith("]"):
                            section_path = line[1:-1].strip().split(".")
                            current = data
                            for part in section_path:
                                current = current.setdefault(part, {})
                            continue
                        if "=" not in line:
                            continue
                        key, value = line.split("=", 1)
                        key = key.strip()
                        value = value.strip()
                        if value.startswith("#"):
                            continue
                        if value.startswith("[") and value.endswith("]"):
                            inner = value[1:-1].strip()
                            if not inner:
                                current[key] = []
                                continue
                            items = []
                            for part in inner.split(","):
                                item = part.strip()
                                if (
                                    (item.startswith('"') and item.endswith('"'))
                                    or (item.startswith("'") and item.endswith("'"))
                                ):
                                    item = item[1:-1]
                                if item:
                                    items.append(item)
                            current[key] = items
                            continue
                        if (value.startswith('"') and value.endswith('"')) or (
                            value.startswith("'") and value.endswith("'")
                        ):
                            value = value[1:-1]
                        current[key] = value
                return data

            parsed = _simple_toml_load(APP_CONFIG_PATH)
        if not isinstance(parsed, dict):
            return defaults
        for section in ("app", "branding", "roles", "uploads", "theme", "theme_presets"):
            section_data = parsed.get(section)
            if isinstance(section_data, dict):
                defaults[section].update(section_data)
        theme_profile = defaults["theme"].get("profile")
        presets = defaults.get("theme_presets", {})
        if isinstance(theme_profile, str) and theme_profile in presets:
            defaults["theme"].update(presets[theme_profile])
        roles_cfg = defaults.get("roles", {})
        allowed = roles_cfg.get("allowed")
        if isinstance(allowed, str):
            roles_cfg["allowed"] = [r.strip() for r in allowed.split(",") if r.strip()]
        elif not isinstance(allowed, list):
            roles_cfg["allowed"] = ["admin", "user"]
        default_role = roles_cfg.get("default_role")
        if not isinstance(default_role, str) or default_role not in roles_cfg["allowed"]:
            roles_cfg["default_role"] = "user"
        uploads_cfg = defaults.get("uploads", {})
        for key in ("user_extensions", "rag_extensions"):
            value = uploads_cfg.get(key)
            if isinstance(value, str):
                items = [v.strip() for v in value.split(",") if v.strip()]
                uploads_cfg[key] = items
            elif not isinstance(value, list):
                uploads_cfg[key] = []
            uploads_cfg[key] = [
                (v if v.startswith(".") else f".{v}").lower() for v in uploads_cfg[key]
            ]
        return defaults
    except Exception:
        return defaults


@app.get("/api/config")
def get_app_config() -> dict[str, Any]:
    return _load_app_config()


def _generate_conversation_title(content: str) -> str:
    """Generate a brief conversation title based on the first message content using akasha."""
    try:
        db = get_connection()
        try:
            cfg = load_llm_config(db)
        finally:
            db.close()
        
        ask_obj = akasha.ask(
            model=cfg["model_name"],
            temperature=cfg["temperature"],
            max_output_tokens=1000,
            verbose=True
        )
        prompt = f"請根據以下使用者的提問，產生一個不超過 10 個字的簡短對話主題（例如：代碼除錯、美食推薦）。請使用使用者所使用的語系（預設繁體中文），並且只輸出標題文字，不要有任何標點符號或解釋。\n\n提問內容：{content}"
        title = ask_obj(prompt).strip()
        # Remove common wrapping like quotes
        title = re.sub(r'["\'「」『』]', '', title)
        return title[:50]
    except Exception as e:
        print(f"Error generating title: {e}")
        return "New Chat"


def _run_reply_worker(
    content: str,
    files_payload: List[dict],
    conversation_id: int,
    parent_message_id: Optional[int],
    owner_user_id: int,
    owner_display_name: Optional[str],
    result_queue: multiprocessing.Queue,
) -> None:
    try:
        conn = get_connection()
        try:
            # 1. 檢查是否需要自動命名對話標題 (僅在標題仍為 "New Chat" 時)
            row = conn.execute(
                "SELECT title FROM conversation WHERE id = ?", (conversation_id,)
            ).fetchone()
            if row and row["title"] == "New Chat":
                new_title = _generate_conversation_title(content)
                if new_title and new_title != "New Chat":
                    conn.execute(
                        "UPDATE conversation SET title = ?, updated_at = datetime('now') WHERE id = ?",
                        (new_title, conversation_id),
                    )
                    conn.commit()

            # 2. 進行正式的回覆生成
            files = [MessageFileResponse(**item) for item in files_payload]
            reply_payload = build_reply(
                content,
                files,
                conn,
                conversation_id,
                parent_message_id,
                owner_user_id,
                owner_display_name,
            )
            result_queue.put(("ok", reply_payload))
        finally:
            conn.close()
    except Exception:
        result_queue.put(("error", traceback.format_exc()))


def normalize_email(email: str) -> str:
    return email.strip().lower()


def create_access_token(subject: str, expires_minutes: int = ACCESS_TOKEN_EXPIRE_MINUTES) -> str:
    expire = datetime.utcnow() + timedelta(minutes=expires_minutes)
    to_encode = {"sub": subject, "exp": expire}
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def row_to_user(row: sqlite3.Row) -> UserResponse:
    return UserResponse(
        id=row["id"],
        email=row["email"],
        display_name=row["display_name"],
        role=row["role"],
        created_at=row["created_at"],
        last_login_at=row["last_login_at"],
    )


def verify_password(plain_password: str, password_hash: str) -> bool:
    return pwd_context.verify(plain_password, password_hash)


def hash_password(password: str) -> str:
    if len(password.encode("utf-8")) > 72:
        raise ValueError("password cannot be longer than 72 bytes")
    return pwd_context.hash(password)


def require_admin(user: UserResponse) -> None:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")


def get_user_row_or_404(user_id: int, db: sqlite3.Connection) -> sqlite3.Row:
    row = db.execute("SELECT * FROM user WHERE id = ?", (user_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return row


def row_to_conversation(row: sqlite3.Row) -> ConversationResponse:
    message_count = None
    if "message_count" in row.keys():
        message_count = row["message_count"]
    return ConversationResponse(
        id=row["id"],
        user_id=row["user_id"],
        title=row["title"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        message_count=message_count,
    )


def get_message_files(db: sqlite3.Connection, message_id: int) -> List[MessageFileResponse]:
    rows = db.execute("SELECT * FROM message_file WHERE message_id = ?", (message_id,)).fetchall()
    return [
        MessageFileResponse(
            id=row["id"],
            file_name=row["file_name"],
            file_path=row["file_path"],
            mime_type=row["mime_type"],
            size_bytes=row["size_bytes"],
        )
        for row in rows
    ]


def row_to_message(row: sqlite3.Row, files: Optional[List[MessageFileResponse]] = None) -> MessageResponse:
    return MessageResponse(
        id=row["id"],
        user_id=row["user_id"],
        conversation_id=row["conversation_id"],
        sender_type=row["sender_type"],
        content=row["content"],
        status=row["status"],
        parent_message_id=row["parent_message_id"],
        stopped_at=row["stopped_at"],
        created_at=row["created_at"],
        files=files or [],
    )


def row_to_rag_file(row: sqlite3.Row) -> RagFileResponse:
    return RagFileResponse(
        id=row["id"],
        file_name=row["file_name"],
        file_path=row["file_path"],
        mime_type=row["mime_type"],
        size_bytes=row["size_bytes"],
        uploaded_by=row["uploaded_by"],
        created_at=row["created_at"],
    )


def load_mssql_config(db: sqlite3.Connection) -> MssqlConfigResponse:
    row = db.execute("SELECT * FROM mssql_config WHERE id = 1").fetchone()
    if not row:
        return MssqlConfigResponse(
            server=os.environ.get("MSSQL_SERVER"),
            database=os.environ.get("MSSQL_DATABASE"),
            username=os.environ.get("MSSQL_USER"),
            password=os.environ.get("MSSQL_PASSWORD"),
            use_trusted=os.environ.get("MSSQL_USE_TRUSTED", "false").lower() in ("1", "true", "yes"),
            updated_at=None,
        )
    return MssqlConfigResponse(
        server=row["server"],
        database=row["database"],
        username=row["username"],
        password=row["password"],
        use_trusted=bool(row["use_trusted"]),
        updated_at=row["updated_at"],
    )


def build_mssql_conn_str(
    server: str,
    database: str,
    username: Optional[str],
    password: Optional[str],
    use_trusted: bool,
) -> str:
    if use_trusted:
        return (
            f"DRIVER={{ODBC Driver 18 for SQL Server}};"
            f"SERVER={server};"
            f"DATABASE={database};"
            "Trusted_Connection=yes;"
            "Encrypt=no;"
        )
    return (
        f"DRIVER={{ODBC Driver 18 for SQL Server}};"
        f"SERVER={server};"
        f"DATABASE={database};"
        f"UID={username or ''};"
        f"PWD={password or ''};"
        "Encrypt=no;"
    )


def get_message_row_or_404(message_id: int, db: sqlite3.Connection) -> sqlite3.Row:
    row = db.execute("SELECT * FROM message WHERE id = ?", (message_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")
    return row


def get_rag_file_row_or_404(file_id: int, db: sqlite3.Connection) -> sqlite3.Row:
    row = db.execute("SELECT * FROM rag_file WHERE id = ?", (file_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RAG file not found")
    return row


def ensure_user_upload_dir(user_id: int, display_name: Optional[str] = None) -> Path:
    suffix = ""
    if display_name:
        slug = "".join(ch.lower() if ch.isalnum() else "_" for ch in display_name).strip("_")
        if slug:
            suffix = f"_{slug}"
    folder = UPLOAD_ROOT / f"user_{user_id}{suffix}"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def get_conversation_or_404(conversation_id: int, db: sqlite3.Connection) -> sqlite3.Row:
    row = db.execute("SELECT * FROM conversation WHERE id = ?", (conversation_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    return row


def _allowed_extensions(kind: str) -> set[str]:
    app_config = _load_app_config()
    uploads_cfg = app_config.get("uploads", {}) if isinstance(app_config, dict) else {}
    key = "rag_extensions" if kind == "rag" else "user_extensions"
    values = uploads_cfg.get(key) if isinstance(uploads_cfg, dict) else None
    if isinstance(values, list) and values:
        return {str(v).lower() for v in values}
    if kind == "rag":
        return {".pdf", ".doc", ".docx", ".md", ".csv", ".txt", ".xls", ".xlsx"}
    return {".pdf", ".doc", ".docx", ".md", ".csv", ".txt", ".xls", ".xlsx", ".png", ".jpg", ".jpeg"}


async def persist_rag_file(upload_file: UploadFile) -> tuple[str, str, int, Optional[str]]:
    safe_name = Path(upload_file.filename or "upload").name
    suffix = Path(safe_name).suffix.lower()
    allowed = _allowed_extensions("rag")
    if suffix not in allowed:
        detail = f"Unsupported file type. Allowed: {', '.join(sorted(allowed))}"
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)
    unique_name = f"{uuid4().hex}_{safe_name}"
    dest_path = RAG_UPLOAD_ROOT / unique_name
    size = 0
    with dest_path.open("wb") as buffer:
        while True:
            chunk = await upload_file.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            buffer.write(chunk)
    await upload_file.close()
    return safe_name, dest_path.relative_to(RAG_UPLOAD_ROOT).as_posix(), size, upload_file.content_type


def ensure_default_conversation(db: sqlite3.Connection, user_id: int) -> sqlite3.Row:
    row = (
        db.execute(
            "SELECT * FROM conversation WHERE user_id = ? ORDER BY updated_at DESC, id ASC LIMIT 1",
            (user_id,),
        ).fetchone()
    )
    if row:
        return row
    cursor = db.execute(
        "INSERT INTO conversation (user_id, title) VALUES (?, ?)",
        (user_id, "New Chat"),
    )
    db.commit()
    return get_conversation_or_404(cursor.lastrowid, db)


def create_conversation_for_user(
    db: sqlite3.Connection, user_id: int, title: Optional[str] = None
) -> sqlite3.Row:
    final_title = (title or "New Chat").strip() or "New Chat"
    cursor = db.execute(
        "INSERT INTO conversation (user_id, title) VALUES (?, ?)",
        (user_id, final_title),
    )
    db.commit()
    return get_conversation_or_404(cursor.lastrowid, db)


def touch_conversation(db: sqlite3.Connection, conversation_id: int) -> None:
    db.execute(
        "UPDATE conversation SET updated_at = datetime('now') WHERE id = ?",
        (conversation_id,),
    )


def make_unique_name(file_name: str) -> str:
    path = Path(file_name)
    suffix = uuid4().hex[:8]
    stem = path.stem or "upload"
    return f"{stem}_{suffix}{path.suffix}"


async def persist_upload_file(upload_file: UploadFile, user_id: int, display_name: Optional[str] = None) -> tuple[str, str, int]:
    dest_dir = ensure_user_upload_dir(user_id, display_name)
    safe_name = Path(upload_file.filename or "upload").name
    suffix = Path(safe_name).suffix.lower()
    allowed = _allowed_extensions("user")
    if suffix not in allowed:
        detail = f"Unsupported file type. Allowed: {', '.join(sorted(allowed))}"
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)
    unique_name = make_unique_name(safe_name)
    dest_path = dest_dir / unique_name
    size = 0
    with dest_path.open("wb") as buffer:
        while True:
            chunk = await upload_file.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            buffer.write(chunk)
    await upload_file.close()
    relative_path = dest_path.relative_to(UPLOAD_ROOT).as_posix()
    return safe_name, relative_path, size


def persist_assistant_files(
    db: sqlite3.Connection,
    message_id: int,
    user_id: int,
    display_name: Optional[str],
    generated_files: List[AssistantGeneratedFile],
) -> List[MessageFileResponse]:
    if not generated_files:
        return []
    dest_dir = ensure_user_upload_dir(user_id, display_name)
    saved_files: List[MessageFileResponse] = []
    for generated_file in generated_files:
        raw_name = generated_file.file_name or "assistant_file"
        safe_name = Path(raw_name).name
        unique_name = make_unique_name(safe_name)
        dest_path = dest_dir / unique_name
        if generated_file.source_path:
            source_path = Path(generated_file.source_path)
            if not source_path.is_absolute():
                source_path = UPLOAD_ROOT / source_path
            dest_path.write_bytes(source_path.read_bytes())
        else:
            payload: bytes
            if generated_file.content is not None:
                payload = generated_file.content
            else:
                payload = (generated_file.text or "").encode("utf-8")
            dest_path.write_bytes(payload)
        size = dest_path.stat().st_size
        relative_path = dest_path.relative_to(UPLOAD_ROOT).as_posix()
        cursor = db.execute(
            "INSERT INTO message_file (message_id, file_name, file_path, mime_type, size_bytes) VALUES (?, ?, ?, ?, ?)",
            (message_id, safe_name, relative_path, generated_file.mime_type, size),
        )
        saved_files.append(
            MessageFileResponse(
                id=cursor.lastrowid,
                file_name=safe_name,
                file_path=relative_path,
                mime_type=generated_file.mime_type,
                size_bytes=size,
            )
        )
    return saved_files


def build_reply(
    content: str,
    files: List[MessageFileResponse],
    db: sqlite3.Connection,
    conversation_id: int,
    exclude_message_id: Optional[int] = None,
    owner_user_id: Optional[int] = None,
    owner_display_name: Optional[str] = None,
) -> Union[str, tuple[str, List[AssistantGeneratedFile]]]:
    """Generate assistant response via LLM."""
    text = content.strip() if content and content.strip() else "(no text provided)"
    history_rows = db.execute(
        """
        SELECT id, sender_type, content, status
        FROM message
        WHERE conversation_id = ?
          AND status != 'pending'
        ORDER BY created_at ASC, id ASC
        """,
        (conversation_id,),
    ).fetchall()
    history_lines = []
    for row in history_rows:
        if exclude_message_id and row["id"] == exclude_message_id:
            continue
        content_text = (row["content"] or "").strip()
        if not content_text:
            continue
        speaker = "使用者" if row["sender_type"] == "user" else "AI"
        history_lines.append(f"{speaker}: {content_text}")
    history_block = "\n".join(history_lines)
    user_upload_dir = None
    if owner_user_id is not None:
        upload_dir_path = ensure_user_upload_dir(owner_user_id, owner_display_name)
        user_upload_dir = (Path("backend") / upload_dir_path.relative_to(BASE_DIR)).as_posix()
    display_name = owner_display_name or "未提供"
    role = "未提供"
    if owner_user_id is not None:
        owner_row = db.execute(
            "SELECT display_name, role FROM user WHERE id = ?",
            (owner_user_id,),
        ).fetchone()
        if owner_row:
            display_name = owner_row["display_name"] or display_name
            role = owner_row["role"] or role

    # 載入管理員設定的模型配置
    cfg = load_llm_config(db)
    admin_system_prompt = cfg.get("system_prompt") or "請根據上述歷史對話紀錄與使用者提問，產生適當的回覆內容。如果有多項資訊，可以用表格或是條列式呈現。"

    prompt = f'''
# 歷史對話紀錄
{history_block}

# 環境資訊
- 現在時間：{datetime.now():%Y年%m月%d日}
- 當前使用者：id={owner_user_id}, name={display_name}, role={role}
- 檔案路徑：{user_upload_dir} (若執行 Python 產生檔案請存放於此)

# 任務規範
{admin_system_prompt}

# 使用者提問
{text}
'''
    
    
    print("start akasha")
    print(prompt)
    agent = get_agent()
    result = agent(question=prompt)
    print("end akasha")

    if isinstance(result, str):
        response_text = result
    elif isinstance(result, (list, tuple)):
        response_text = "\n".join(str(item) for item in result)
    else:
        try:
            response_text = "\n".join(str(item) for item in result)
        except TypeError:
            response_text = str(result)

    try:
        parsed = json.loads(response_text)
    except json.JSONDecodeError:
        parsed = None
        if "{" in response_text and "}" in response_text:
            start = response_text.find("{")
            end = response_text.rfind("}")
            if start >= 0 and end > start:
                candidate = response_text[start : end + 1]
                try:
                    parsed = json.loads(candidate)
                except json.JSONDecodeError:
                    parsed = None
    if isinstance(parsed, dict) and "action" in parsed and "action_input" in parsed:
        action = str(parsed.get("action", "")).lower()
        if action in {"answer", "final", "final_answer", "final answer"}:
            action_input = parsed.get("action_input", "")
            if isinstance(action_input, (dict, list)):
                response_text = json.dumps(action_input, ensure_ascii=False)
            else:
                response_text = str(action_input)
        else:
            response_text = "系統尚未產生最終答案，已完成工具查詢，請稍後再試。"
    elif isinstance(parsed, (dict, list)):
        response_text = json.dumps(parsed, ensure_ascii=False)

    # 開頭為 [THOUGHT]: / [ACTION]: / [OBSERVATION]: / [FINAL ANSWER]: 都濾除掉
    lines = []
    for line in response_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("[THOUGHT]:") or stripped.startswith("[ACTION]:") or stripped.startswith("[OBSERVATION]:") or stripped.startswith("[FINAL ANSWER]:"):
            continue
        lines.append(line)

    if not any(line.strip() for line in lines):
        lines = [response_text]

    normalized_lines = []
    last_blank = False
    for line in lines:
        if line.strip():
            normalized_lines.append(line)
            last_blank = False
        else:
            if not last_blank:
                normalized_lines.append("")
            last_blank = True

    normalized_text = "\n".join(normalized_lines)
    normalized_text = re.sub(r"(?:\r?\n[ \t]*){2,}", "\n\n", normalized_text).strip()

    # if files:
    #     lines.append("收到的檔案訊息:")
    #     for file in files:
    #         mime = file.mime_type or "unknown type"
    #         lines.append(f"- {file.file_name} ({mime})")
    # else:
    #     lines.append("未收到檔案訊息。")

    # files_summary = "\n".join(f"- {file.file_name}" for file in files) if files else "- (none)"
    # generated_files = [
    #     AssistantGeneratedFile(
    #         file_name="assistant_reply.txt",
    #         text=f"Echo: {text}\nReceived files:\n{files_summary}\n",
    #         mime_type="text/plain",
    #     )
    # ]

    # lines.append("可供下載的檔案:")
    # for generated in generated_files:
    #     lines.append(f"- {generated.file_name}")
    # lines.append("下載連結:")
    # lines.append(DOWNLOAD_LINKS_PLACEHOLDER)
    # return "\n".join(lines), generated_files
    
    return normalized_text


# def build_reply(
#     content: str, files: List[MessageFileResponse]
# ) -> Union[str, tuple[str, List[AssistantGeneratedFile]]]:
#     """Generate assistant response via LLM."""
#     text = content.strip() if content and content.strip() else "(no text provided)"
#     lines = [f"收到的文字訊息: {text}"]
#     if files:
#         lines.append("收到的檔案訊息:")
#         for file in files:
#             mime = file.mime_type or "unknown type"
#             lines.append(f"- {file.file_name} ({mime})")
#     else:
#         lines.append("未收到檔案訊息。")

#     files_summary = "\n".join(f"- {file.file_name}" for file in files) if files else "- (none)"
#     generated_files = [
#         AssistantGeneratedFile(
#             file_name="assistant_reply.txt",
#             text=f"Echo: {text}\nReceived files:\n{files_summary}\n",
#             mime_type="text/plain",
#         )
#     ]

#     lines.append("可供下載的檔案:")
#     for generated in generated_files:
#         lines.append(f"- {generated.file_name}")
#     lines.append("下載連結:")
#     lines.append(DOWNLOAD_LINKS_PLACEHOLDER)
#     return "\n".join(lines), generated_files


def schedule_assistant_reply(
    message_id: int,
    conversation_id: int,
    content: str,
    files: List[MessageFileResponse],
    owner_user_id: int,
    owner_display_name: Optional[str],
) -> None:
    loop = asyncio.get_running_loop()
    task = loop.create_task(
        run_assistant_reply(message_id, conversation_id, content, files, owner_user_id, owner_display_name)
    )
    pending_generations[message_id] = {"task": task, "process": None}


async def run_assistant_reply(
    message_id: int,
    conversation_id: int,
    content: str,
    files: List[MessageFileResponse],
    owner_user_id: int,
    owner_display_name: Optional[str],
) -> None:
    process: Optional[multiprocessing.Process] = None
    try:
        await asyncio.sleep(SIMULATED_REPLY_DELAY)
        conn = get_connection()
        try:
            parent_row = conn.execute(
                "SELECT parent_message_id FROM message WHERE id = ?",
                (message_id,),
            ).fetchone()
            parent_message_id = parent_row["parent_message_id"] if parent_row else None
        finally:
            conn.close()
        ctx = multiprocessing.get_context("spawn")
        result_queue: multiprocessing.Queue = ctx.Queue()
        files_payload = [
            file.dict() if hasattr(file, "dict") else dict(file)  # type: ignore[arg-type]
            for file in files
        ]
        process = ctx.Process(
            target=_run_reply_worker,
            args=(
                content,
                files_payload,
                conversation_id,
                parent_message_id,
                owner_user_id,
                owner_display_name,
                result_queue,
            ),
        )
        process.start()
        pending_entry = pending_generations.get(message_id)
        if pending_entry is not None:
            pending_entry["process"] = process

        reply_payload = None
        while True:
            if process.exitcode is not None:
                try:
                    status_label, payload = result_queue.get_nowait()
                    if status_label == "ok":
                        reply_payload = payload
                    else:
                        raise RuntimeError(payload)
                except py_queue.Empty:
                    raise RuntimeError("Assistant worker exited without a result")
                break
            try:
                status_label, payload = result_queue.get_nowait()
                if status_label == "ok":
                    reply_payload = payload
                else:
                    raise RuntimeError(payload)
                break
            except py_queue.Empty:
                await asyncio.sleep(0.1)

        if reply_payload is None:
            raise RuntimeError("Assistant worker returned no payload")

        conn = get_connection()
        try:
            status_row = conn.execute(
                "SELECT status FROM message WHERE id = ?",
                (message_id,),
            ).fetchone()
            if not status_row or status_row["status"] != "pending":
                return
            if isinstance(reply_payload, tuple):
                reply_text, generated_files = reply_payload
            else:
                reply_text, generated_files = reply_payload, []
            saved_files = persist_assistant_files(conn, message_id, owner_user_id, owner_display_name, generated_files)
            final_text = reply_text
            if saved_files:
                link_lines = [f"- /chat_uploads/{file.file_path}" for file in saved_files]
                if DOWNLOAD_LINKS_PLACEHOLDER in final_text:
                    final_text = final_text.replace(DOWNLOAD_LINKS_PLACEHOLDER, "\n".join(link_lines))
                else:
                    final_text = f"{final_text}\n下載連結:\n" + "\n".join(link_lines)
            else:
                final_text = final_text.replace(f"\n{DOWNLOAD_LINKS_PLACEHOLDER}", "")
            final_text = _fix_missing_upload_links(final_text)
            for attempt in range(3):
                try:
                    conn.execute(
                        "UPDATE message SET content = ?, status = 'completed', stopped_at = NULL WHERE id = ?",
                        (final_text, message_id),
                    )
                    conn.execute("UPDATE conversation SET updated_at = datetime('now') WHERE id = ?", (conversation_id,))
                    conn.commit()
                    break
                except sqlite3.OperationalError as exc:
                    if "locked" not in str(exc).lower() or attempt == 2:
                        raise
                    await asyncio.sleep(0.2 * (attempt + 1))
        finally:
            conn.close()
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        print(f"Assistant reply failed: {exc}")
        try:
            conn = get_connection()
            try:
                status_row = conn.execute(
                    "SELECT status, content FROM message WHERE id = ?",
                    (message_id,),
                ).fetchone()
                if status_row and status_row["status"] == "pending":
                    fallback_text = status_row["content"] or "Response failed."
                    conn.execute(
                        "UPDATE message SET content = ?, status = 'failed', stopped_at = datetime('now') WHERE id = ?",
                        (fallback_text, message_id),
                    )
                    conn.commit()
            finally:
                conn.close()
        except Exception as update_exc:
            print(f"Failed to persist assistant failure state: {update_exc}")
    finally:
        if process is not None and process.is_alive():
            process.terminate()
            process.join(timeout=1.0)
        pending_generations.pop(message_id, None)


def cancel_pending_generation(message_id: int) -> None:
    entry = pending_generations.pop(message_id, None)
    if not entry:
        return
    process = entry.get("process")
    task = entry.get("task")
    if isinstance(process, multiprocessing.Process) and process.is_alive():
        process.terminate()
        process.join(timeout=1.0)
    if isinstance(task, asyncio.Task):
        task.cancel()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: sqlite3.Connection = Depends(get_db),
) -> UserResponse:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing credentials")
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    if not email:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    row = db.execute("SELECT * FROM user WHERE email = ?", (email,)).fetchone()
    if row is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return row_to_user(row)


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.post("/api/auth/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register_user(payload: RegisterRequest, db: sqlite3.Connection = Depends(get_db)) -> UserResponse:
    email = normalize_email(payload.email)
    exists = db.execute("SELECT 1 FROM user WHERE email = ?", (email,)).fetchone()
    if exists:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    try:
        hashed = hash_password(payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    total_users = db.execute("SELECT COUNT(*) FROM user").fetchone()[0]
    app_config = _load_app_config()
    roles_cfg = app_config.get("roles", {}) if isinstance(app_config, dict) else {}
    allowed_roles = roles_cfg.get("allowed") if isinstance(roles_cfg, dict) else None
    default_role = roles_cfg.get("default_role") if isinstance(roles_cfg, dict) else None
    if not isinstance(default_role, str):
        default_role = "user"
    if isinstance(allowed_roles, list) and default_role not in allowed_roles:
        default_role = "user"
    role = "admin" if total_users == 0 else default_role
    cursor = db.execute(
        "INSERT INTO user (email, password_hash, role, display_name) VALUES (?, ?, ?, ?)",
        (email, hashed, role, payload.display_name),
    )
    db.commit()
    new_user = db.execute("SELECT * FROM user WHERE id = ?", (cursor.lastrowid,)).fetchone()
    create_conversation_for_user(db, new_user["id"], (payload.display_name or "New Chat"))
    return row_to_user(new_user)


@app.post("/api/auth/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: sqlite3.Connection = Depends(get_db)) -> TokenResponse:
    email = normalize_email(payload.email)
    row = db.execute("SELECT * FROM user WHERE email = ?", (email,)).fetchone()
    if row is None or not verify_password(payload.password, row["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")

    now_iso = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    db.execute("UPDATE user SET last_login_at = ? WHERE id = ?", (now_iso, row["id"]))
    db.commit()

    token = create_access_token(subject=email)
    refreshed_row = db.execute("SELECT * FROM user WHERE id = ?", (row["id"],)).fetchone()
    return TokenResponse(access_token=token, user=row_to_user(refreshed_row))


@app.get("/api/auth/me", response_model=UserResponse)
async def read_current_user(current_user: UserResponse = Depends(get_current_user)) -> UserResponse:
    return current_user


@app.get("/api/users", response_model=List[UserResponse])
def list_users(
    db: sqlite3.Connection = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
) -> List[UserResponse]:
    require_admin(current_user)
    rows = db.execute("SELECT * FROM user ORDER BY id").fetchall()
    return [row_to_user(row) for row in rows]


@app.get("/api/users/{user_id}", response_model=UserResponse)
def get_user(
    user_id: int,
    db: sqlite3.Connection = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
) -> UserResponse:
    if current_user.role != "admin" and current_user.id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    row = get_user_row_or_404(user_id, db)
    return row_to_user(row)


@app.patch("/api/users/{user_id}", response_model=UserResponse)
def update_user(
    user_id: int,
    payload: UpdateUserRequest,
    db: sqlite3.Connection = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
) -> UserResponse:
    if current_user.role != "admin" and current_user.id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    updates = []
    params: List[object] = []

    if payload.display_name is not None:
        updates.append("display_name = ?")
        params.append(payload.display_name)

    if payload.email is not None:
        new_email = normalize_email(payload.email)
        exists = db.execute(
            "SELECT 1 FROM user WHERE email = ? AND id != ?",
            (new_email, user_id),
        ).fetchone()
        if exists:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")
        updates.append("email = ?")
        params.append(new_email)

    if payload.password is not None:
        try:
            hashed = hash_password(payload.password)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        updates.append("password_hash = ?")
        params.append(hashed)

    if payload.role is not None:
        if current_user.role != "admin":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only admins can change roles")
        app_config = _load_app_config()
        roles_cfg = app_config.get("roles", {}) if isinstance(app_config, dict) else {}
        allowed_roles = roles_cfg.get("allowed") if isinstance(roles_cfg, dict) else None
        if isinstance(allowed_roles, list) and payload.role not in allowed_roles:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid role")
        updates.append("role = ?")
        params.append(payload.role)

    if not updates:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update")

    params.append(user_id)
    db.execute(f"UPDATE user SET {', '.join(updates)} WHERE id = ?", params)
    db.commit()
    row = get_user_row_or_404(user_id, db)
    return row_to_user(row)


@app.delete("/api/users/{user_id}", response_model=DeleteResponse)
def delete_user(
    user_id: int,
    db: sqlite3.Connection = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
) -> DeleteResponse:
    require_admin(current_user)
    if current_user.id == user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete your own account")
    _ = get_user_row_or_404(user_id, db)
    db.execute("DELETE FROM user WHERE id = ?", (user_id,))
    db.commit()
    return DeleteResponse(detail="User deleted")


@app.get("/api/admin/rag-files", response_model=List[RagFileResponse])
def list_rag_files(
    db: sqlite3.Connection = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
) -> List[RagFileResponse]:
    require_admin(current_user)
    rows = db.execute("SELECT * FROM rag_file ORDER BY created_at DESC").fetchall()
    return [row_to_rag_file(row) for row in rows]


@app.post("/api/admin/rag-files", response_model=List[RagFileResponse], status_code=status.HTTP_201_CREATED)
async def upload_rag_files(
    request: Request,
    db: sqlite3.Connection = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
) -> List[RagFileResponse]:
    require_admin(current_user)
    form = await request.form()
    raw_files = form.getlist("files") if hasattr(form, "getlist") else []
    upload_list: List[UploadFile] = [file for file in raw_files if getattr(file, "filename", None)]
    if not upload_list:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No files uploaded")
    saved_rows: List[RagFileResponse] = []
    for upload_file in upload_list:
        original_name, relative_path, size, mime_type = await persist_rag_file(upload_file)
        cursor = db.execute(
            "INSERT INTO rag_file (file_name, file_path, mime_type, size_bytes, uploaded_by) VALUES (?, ?, ?, ?, ?)",
            (original_name, relative_path, mime_type, size, current_user.id),
        )
        row = get_rag_file_row_or_404(cursor.lastrowid, db)
        saved_rows.append(row_to_rag_file(row))
    db.commit()
    return saved_rows


@app.post("/api/admin/rag-files/index", response_model=RagIndexResponse)
def index_rag_files(
    payload: RagIndexRequest,
    db: sqlite3.Connection = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
) -> RagIndexResponse:
    require_admin(current_user)
    if payload.file_ids:
        rows = db.execute(
            "SELECT id, file_path FROM rag_file WHERE id IN ({})".format(
                ",".join("?" for _ in payload.file_ids)
            ),
            payload.file_ids,
        ).fetchall()
    else:
        rows = db.execute("SELECT id, file_path FROM rag_file").fetchall()
    file_ids = [row["id"] for row in rows]
    if not file_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No RAG files to index")

    data_sources = []
    for row in rows:
        file_path = RAG_UPLOAD_ROOT / row["file_path"]
        if file_path.exists():
            relative_path = (Path("backend") / "rag_files" / row["file_path"]).as_posix()
            data_sources.append(relative_path)
    if not data_sources:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No RAG files found on disk")
    
    print(data_sources)

    started_at = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    set_index_status(True, started_at)
    
    ak = akasha.RAG(
        embeddings="gemini:gemini-embedding-001",
        model="gemini:gemini-2.5-flash",
        max_input_tokens=3000,
        keep_logs=True,
        verbose=True)

    completed_at = None
    indexed_ok = False
    try:
        set_rag_instance(ak, data_sources)
        print('*** ' + str(data_sources))
        test_response = ak(data_sources=data_sources, prompt="測試")
        if test_response:
            print("Akasha RAG test response:", test_response)
        indexed_ok = True
        completed_at = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
        set_indexed_files(file_ids, completed_at)
        summarizer = akasha.summary(
            model="openai:gpt-4o",
            sum_type="map_reduce",
            chunk_size=1000,
            sum_len=100,
            language="zh",
            keep_logs=True,
            verbose=True,
            max_input_tokens=8000,
        )
        for row in rows:
            file_path = RAG_UPLOAD_ROOT / row["file_path"]
            if not file_path.exists():
                continue
            try:
                summary_result = summarizer(content=[str(file_path)])
            except Exception as exc:
                print(f"Summary failed for {file_path}: {exc}")
                continue
            if isinstance(summary_result, (list, tuple)):
                summary_text = "\n".join(str(item) for item in summary_result)
            else:
                summary_text = str(summary_result)
            db.execute(
                "UPDATE rag_file SET summary = ?, summary_updated_at = datetime('now') WHERE id = ?",
                (summary_text, row["id"]),
            )
        db.commit()
    finally:
        set_index_status(False, started_at)
    
    return RagIndexResponse(
        ok=True,
        detail="Indexing request accepted.",
        file_ids=file_ids,
        indexing=get_index_status().get("indexing", False),
        started_at=started_at,
    )


@app.get("/api/admin/rag-files/index/status", response_model=RagIndexStatusResponse)
def get_rag_index_status(
    current_user: UserResponse = Depends(get_current_user),
) -> RagIndexStatusResponse:
    require_admin(current_user)
    status_payload = get_index_status()
    indexed_files = get_indexed_files()
    indexed_list = [
        RagIndexedFile(file_id=file_id, indexed_at=ts) for file_id, ts in indexed_files.items()
    ]
    return RagIndexStatusResponse(
        indexing=bool(status_payload.get("indexing")),
        started_at=status_payload.get("started_at"),
        indexed_files=indexed_list,
    )


@app.get("/api/admin/rag-files/{file_id}/download")
def download_rag_file(
    file_id: int,
    db: sqlite3.Connection = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
):
    require_admin(current_user)
    row = get_rag_file_row_or_404(file_id, db)
    file_path = RAG_UPLOAD_ROOT / row["file_path"]
    if not file_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found on disk")
    return FileResponse(path=str(file_path), filename=row["file_name"])


@app.delete("/api/admin/rag-files/{file_id}", response_model=DeleteResponse)
def delete_rag_file(
    file_id: int,
    db: sqlite3.Connection = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
) -> DeleteResponse:
    require_admin(current_user)
    row = get_rag_file_row_or_404(file_id, db)
    file_path = RAG_UPLOAD_ROOT / row["file_path"]
    db.execute("DELETE FROM rag_file WHERE id = ?", (file_id,))
    db.commit()
    if file_path.exists():
        file_path.unlink()
    return DeleteResponse(detail="RAG file deleted")


@app.get("/api/admin/mssql-config", response_model=MssqlConfigResponse)
def get_mssql_config(
    db: sqlite3.Connection = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
) -> MssqlConfigResponse:
    require_admin(current_user)
    return load_mssql_config(db)


@app.put("/api/admin/mssql-config", response_model=MssqlConfigResponse)
def update_mssql_config(
    payload: MssqlConfigUpdateRequest,
    db: sqlite3.Connection = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
) -> MssqlConfigResponse:
    require_admin(current_user)
    existing = db.execute("SELECT * FROM mssql_config WHERE id = 1").fetchone()
    updates = []
    params: List[object] = []
    fields = {
        "server": payload.server,
        "database": payload.database,
        "username": payload.username,
        "password": payload.password,
        "use_trusted": payload.use_trusted,
    }
    for key, value in fields.items():
        if value is None:
            continue
        if key == "use_trusted":
            value = int(bool(value))
        updates.append(f"{key} = ?")
        params.append(value)
    if existing is None:
        db.execute(
            "INSERT INTO mssql_config (id, server, database, username, password, use_trusted) VALUES (1, ?, ?, ?, ?, ?)",
            (
                payload.server,
                payload.database,
                payload.username,
                payload.password,
                int(payload.use_trusted or False),
            ),
        )
    elif updates:
        params.append(1)
        db.execute(
            f"UPDATE mssql_config SET {', '.join(updates)}, updated_at = datetime('now') WHERE id = ?",
            params,
        )
    db.commit()
    return load_mssql_config(db)


@app.post("/api/admin/mssql-config/test", response_model=MssqlTestResponse)
def test_mssql_config(
    payload: MssqlConfigUpdateRequest,
    db: sqlite3.Connection = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
) -> MssqlTestResponse:
    require_admin(current_user)
    existing = load_mssql_config(db)
    server = payload.server or existing.server
    database = payload.database or existing.database
    username = payload.username or existing.username
    password = payload.password or existing.password
    use_trusted = payload.use_trusted if payload.use_trusted is not None else existing.use_trusted
    if not server or not database:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Server and database are required.")

    try:
        import pyodbc
        conn_str = build_mssql_conn_str(server, database, username, password, bool(use_trusted))
        with pyodbc.connect(conn_str, timeout=5) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return MssqlTestResponse(ok=True, detail="Connection successful.")
    except Exception as exc:
        return MssqlTestResponse(ok=False, detail=f"Connection failed: {exc}")


@app.get("/api/admin/llm-config", response_model=LlmConfigResponse)
def get_llm_config(
    db: sqlite3.Connection = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
) -> LlmConfigResponse:
    require_admin(current_user)
    row = db.execute("SELECT * FROM llm_config WHERE id = 1").fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="LLM config not found")
    return LlmConfigResponse(**dict(row))


@app.patch("/api/admin/llm-config", response_model=LlmConfigResponse)
def update_llm_config(
    payload: LlmConfigUpdateRequest,
    db: sqlite3.Connection = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
) -> LlmConfigResponse:
    require_admin(current_user)
    updates = []
    params: List[Any] = []
    if payload.model_name is not None:
        updates.append("model_name = ?")
        params.append(payload.model_name)
    if payload.temperature is not None:
        updates.append("temperature = ?")
        params.append(payload.temperature)
    if payload.max_input_tokens is not None:
        updates.append("max_input_tokens = ?")
        params.append(payload.max_input_tokens)
    if payload.max_output_tokens is not None:
        updates.append("max_output_tokens = ?")
        params.append(payload.max_output_tokens)
    if payload.system_prompt is not None:
        updates.append("system_prompt = ?")
        params.append(payload.system_prompt)
    
    if not updates:
        raise HTTPException(status_code=400, detail="No updates provided")
    
    updates.append("updated_at = datetime('now')")
    params.append(1) # ID = 1
    
    db.execute(f"UPDATE llm_config SET {', '.join(updates)} WHERE id = ?", params)
    db.commit()
    
    row = db.execute("SELECT * FROM llm_config WHERE id = 1").fetchone()
    return LlmConfigResponse(**dict(row))


@app.get("/api/conversations", response_model=List[ConversationResponse])
def list_conversations(
    user_id: Optional[int] = None,
    db: sqlite3.Connection = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
) -> List[ConversationResponse]:
    target_user_id = user_id or current_user.id
    if current_user.role != "admin" and target_user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    rows = db.execute(
        """
        SELECT c.*, (
            SELECT COUNT(*) FROM message m WHERE m.conversation_id = c.id
        ) AS message_count
        FROM conversation c
        WHERE c.user_id = ?
        ORDER BY c.updated_at DESC, c.id DESC
        """,
        (target_user_id,),
    ).fetchall()
    if not rows and target_user_id == current_user.id:
        default_row = create_conversation_for_user(db, current_user.id, "New Chat")
        rows = [
            db.execute(
                "SELECT c.*, 0 AS message_count FROM conversation c WHERE id = ?",
                (default_row["id"],),
            ).fetchone()
        ]
    return [row_to_conversation(row) for row in rows]


@app.post("/api/conversations", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
def create_conversation(
    payload: ConversationCreateRequest,
    db: sqlite3.Connection = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
) -> ConversationResponse:
    row = create_conversation_for_user(db, current_user.id, payload.title)
    return row_to_conversation(row)


@app.patch("/api/conversations/{conversation_id}", response_model=ConversationResponse)
def update_conversation(
    conversation_id: int,
    payload: ConversationUpdateRequest,
    db: sqlite3.Connection = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
) -> ConversationResponse:
    conversation = get_conversation_or_404(conversation_id, db)
    if current_user.role != "admin" and conversation["user_id"] != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    updates = []
    params: List[object] = []
    if payload.title is not None:
        updated_title = payload.title.strip() or "New Chat"
        updates.append("title = ?")
        params.append(updated_title)
    if not updates:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update")
    params.append(conversation_id)
    db.execute(
        f"UPDATE conversation SET {', '.join(updates)}, updated_at = datetime('now') WHERE id = ?",
        params,
    )
    db.commit()
    updated = get_conversation_or_404(conversation_id, db)
    return row_to_conversation(updated)


@app.delete("/api/conversations/{conversation_id}", response_model=DeleteResponse)
def delete_conversation(
    conversation_id: int,
    db: sqlite3.Connection = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
) -> DeleteResponse:
    conversation = get_conversation_or_404(conversation_id, db)
    if current_user.role != "admin" and conversation["user_id"] != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    db.execute("DELETE FROM conversation WHERE id = ?", (conversation_id,))
    db.commit()
    return DeleteResponse(detail="Conversation deleted")


@app.post("/api/messages", response_model=MessageCreateResponse)
async def create_message(
    request: Request,
    db: sqlite3.Connection = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
) -> MessageCreateResponse:
    form = await request.form()
    raw_content = form.get("content") or ""
    sender_type = (form.get("sender_type") or "user").lower()
    if sender_type not in {"user", "assistant"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid sender type")
    if sender_type == "assistant" and current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only admins can create assistant messages")

    raw_conversation_id = form.get("conversation_id")
    conversation_row: Optional[sqlite3.Row]
    if raw_conversation_id is not None:
        try:
            conversation_id = int(raw_conversation_id)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid conversation id") from exc
        conversation_row = get_conversation_or_404(conversation_id, db)
    else:
        if sender_type == "assistant" and current_user.role == "admin":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="conversation_id is required")
        conversation_row = ensure_default_conversation(db, current_user.id)

    if current_user.role != "admin" and conversation_row["user_id"] != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to conversation")

    conversation_owner_id = conversation_row["user_id"]
    sender_user_id = current_user.id

    cursor = db.execute(
        "INSERT INTO message (user_id, sender_type, content, conversation_id) VALUES (?, ?, ?, ?)",
        (sender_user_id, sender_type, raw_content, conversation_row["id"]),
    )
    message_id = cursor.lastrowid

    raw_files = form.getlist("files") if hasattr(form, "getlist") else []
    upload_list: List[UploadFile] = [file for file in raw_files if getattr(file, "filename", None)]

    saved_files: List[MessageFileResponse] = []
    for upload_file in upload_list:
        original_name, relative_path, size = await persist_upload_file(upload_file, sender_user_id, current_user.display_name)
        cursor = db.execute(
            "INSERT INTO message_file (message_id, file_name, file_path, mime_type, size_bytes) VALUES (?, ?, ?, ?, ?)",
            (message_id, original_name, relative_path, upload_file.content_type, size),
        )
        saved_files.append(
            MessageFileResponse(
                id=cursor.lastrowid,
                file_name=original_name,
                file_path=relative_path,
                mime_type=upload_file.content_type,
                size_bytes=size,
            )
        )

    message_row = db.execute("SELECT * FROM message WHERE id = ?", (message_id,)).fetchone()
    user_message = row_to_message(message_row, saved_files)
    touch_conversation(db, conversation_row["id"])

    assistant_message: Optional[MessageResponse] = None
    if sender_type == "user":
        owner_display_name = None
        if conversation_owner_id == current_user.id:
            owner_display_name = current_user.display_name
        else:
            owner_row = db.execute(
                "SELECT display_name FROM user WHERE id = ?",
                (conversation_owner_id,),
            ).fetchone()
            if owner_row:
                owner_display_name = owner_row["display_name"]
        reply_cursor = db.execute(
            "INSERT INTO message (user_id, sender_type, content, conversation_id, status, parent_message_id) VALUES (?, ?, ?, ?, ?, ?)",
            (conversation_owner_id, "assistant", "", conversation_row["id"], "pending", message_id),
        )
        pending_row = db.execute("SELECT * FROM message WHERE id = ?", (reply_cursor.lastrowid,)).fetchone()
        assistant_message = row_to_message(pending_row, [])
        schedule_assistant_reply(
            pending_row["id"],
            conversation_row["id"],
            raw_content,
            saved_files,
            conversation_owner_id,
            owner_display_name,
        )
    elif sender_type == "assistant":
        db.execute(
            "UPDATE message SET status = 'completed' WHERE id = ?",
            (message_id,),
        )

    touch_conversation(db, conversation_row["id"])
    db.commit()
    return MessageCreateResponse(message=user_message, reply=assistant_message)


@app.get("/api/messages", response_model=MessageListResponse)
def list_messages(
    user_id: Optional[int] = None,
    conversation_id: Optional[int] = None,
    include_assistant: bool = False,
    db: sqlite3.Connection = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
) -> MessageListResponse:
    target_user_id = user_id or current_user.id
    if current_user.role != "admin" and target_user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    base_conversation: Optional[sqlite3.Row] = None
    if conversation_id is not None:
        base_conversation = get_conversation_or_404(conversation_id, db)
    else:
        base_conversation = (
            db.execute(
                "SELECT * FROM conversation WHERE user_id = ? ORDER BY updated_at DESC, id DESC LIMIT 1",
                (target_user_id,),
            ).fetchone()
        )

    if base_conversation is None:
        return MessageListResponse(messages=[], conversation_title=None)

    if current_user.role != "admin" and base_conversation["user_id"] != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    sql = "SELECT * FROM message WHERE conversation_id = ?"
    params: List[Union[int, str]] = [base_conversation["id"]]
    if not include_assistant:
        sql += " AND sender_type = ?"
        params.append("user")
    sql += " ORDER BY created_at ASC"
    rows = db.execute(sql, tuple(params)).fetchall()
    messages = [row_to_message(row, get_message_files(db, row["id"])) for row in rows]
    return MessageListResponse(messages=messages, conversation_title=base_conversation["title"])


@app.post("/api/messages/{message_id}/stop", response_model=MessageResponse)
async def stop_generation(
    message_id: int,
    db: sqlite3.Connection = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
) -> MessageResponse:
    message_row = get_message_row_or_404(message_id, db)
    if message_row["sender_type"] != "assistant":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only assistant messages can be stopped")
    if message_row["status"] != "pending":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Message is not pending")
    conversation = get_conversation_or_404(message_row["conversation_id"], db)
    if current_user.role != "admin" and conversation["user_id"] != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    cancel_pending_generation(message_id)
    cancellation_text = message_row["content"] or "Response cancelled by user."
    db.execute(
        "UPDATE message SET status = 'cancelled', content = ?, stopped_at = datetime('now') WHERE id = ?",
        (cancellation_text, message_id),
    )
    touch_conversation(db, conversation["id"])
    db.commit()
    updated = get_message_row_or_404(message_id, db)
    return row_to_message(updated, get_message_files(db, message_id))
