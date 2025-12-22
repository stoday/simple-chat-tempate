import asyncio
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Union
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, UploadFile, status, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr, Field

from .database import get_connection, get_db, init_db

import akasha
from .tools import agent

load_dotenv()
ak = akasha.ask(model='gemini:gemini-3-flash-preview',
                temperature=1.0,
                max_input_tokens=1048576,
                max_output_tokens=65536)

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
    simulated_reply: Optional[MessageResponse] = None


BASE_DIR = Path(__file__).resolve().parent
UPLOAD_ROOT = Path(os.environ.get("CHAT_UPLOAD_ROOT", BASE_DIR / "chat_uploads"))
UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
app.mount("/chat_uploads", StaticFiles(directory=str(UPLOAD_ROOT)), name="chat_uploads")
SIMULATED_REPLY_DELAY = float(os.environ.get("SIMULATED_REPLY_DELAY", "1.5"))
DOWNLOAD_LINKS_PLACEHOLDER = "__DOWNLOAD_LINKS__"
pending_generations: Dict[int, asyncio.Task] = {}


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


def get_message_row_or_404(message_id: int, db: sqlite3.Connection) -> sqlite3.Row:
    row = db.execute("SELECT * FROM message WHERE id = ?", (message_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")
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


async def persist_upload_file(upload_file: UploadFile, user_id: int, display_name: Optional[str] = None) -> tuple[str, str, int]:
    dest_dir = ensure_user_upload_dir(user_id, display_name)
    safe_name = Path(upload_file.filename or "upload").name
    unique_name = f"{uuid4().hex}_{safe_name}"
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
        unique_name = f"{uuid4().hex}_{safe_name}"
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


def build_simulated_reply(
    content: str,
    files: List[MessageFileResponse],
    db: sqlite3.Connection,
    conversation_id: int,
    exclude_message_id: Optional[int] = None,
) -> Union[str, tuple[str, List[AssistantGeneratedFile]]]:
    """Placeholder assistant response until an LLM is connected."""
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
    prompt = f"# 歷史對話紀錄\n{history_block}\n\n# 使用者提問\n{text}"
    lines = [f"收到的文字訊息: {text}"]
        
    print("start akasha")
    print(prompt)
    lines = agent(question=prompt)
    print("end akasha")
    
    # 開頭為 [THOUGTH]: / [ACTION]: / [OBSERVATION]: / [FINAL ANSWER]: 都濾除掉
    lines_filtered = []
    for line in lines:
        if line.startswith("\n[THOUGHT]:") or line.startswith("\n[ACTION]:") or line.startswith("\n[OBSERVATION]:") or line.startswith("\n[FINAL ANSWER]:"):
            continue
        else:
            lines_filtered.append(line)
        
    lines = lines_filtered
        
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
    
    return "\n".join(lines)


# def build_simulated_reply(
#     content: str, files: List[MessageFileResponse]
# ) -> Union[str, tuple[str, List[AssistantGeneratedFile]]]:
#     """Placeholder assistant response until an LLM is connected."""
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
    pending_generations[message_id] = task


async def run_assistant_reply(
    message_id: int,
    conversation_id: int,
    content: str,
    files: List[MessageFileResponse],
    owner_user_id: int,
    owner_display_name: Optional[str],
) -> None:
    try:
        await asyncio.sleep(SIMULATED_REPLY_DELAY)
        conn = get_connection()
        try:
            parent_row = conn.execute(
                "SELECT parent_message_id FROM message WHERE id = ?",
                (message_id,),
            ).fetchone()
            parent_message_id = parent_row["parent_message_id"] if parent_row else None
            reply_payload = build_simulated_reply(content, files, conn, conversation_id, parent_message_id)
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
            conn.execute(
                "UPDATE message SET content = ?, status = 'completed', stopped_at = NULL WHERE id = ?",
                (final_text, message_id),
            )
            conn.execute("UPDATE conversation SET updated_at = datetime('now') WHERE id = ?", (conversation_id,))
            conn.commit()
        finally:
            conn.close()
    except asyncio.CancelledError:
        raise
    finally:
        pending_generations.pop(message_id, None)


def cancel_pending_generation(message_id: int) -> None:
    task = pending_generations.pop(message_id, None)
    if task:
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
    role = "admin" if total_users == 0 else "user"
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
    return MessageCreateResponse(message=user_message, simulated_reply=assistant_message)


@app.get("/api/messages", response_model=List[MessageResponse])
def list_messages(
    user_id: Optional[int] = None,
    conversation_id: Optional[int] = None,
    include_assistant: bool = False,
    db: sqlite3.Connection = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
) -> List[MessageResponse]:
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
        return []

    if current_user.role != "admin" and base_conversation["user_id"] != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    sql = "SELECT * FROM message WHERE conversation_id = ?"
    params: List[Union[int, str]] = [base_conversation["id"]]
    if not include_assistant:
        sql += " AND sender_type = ?"
        params.append("user")
    sql += " ORDER BY created_at ASC"
    rows = db.execute(sql, tuple(params)).fetchall()
    return [row_to_message(row, get_message_files(db, row["id"])) for row in rows]


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
