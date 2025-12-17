import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable, List, Optional, Union
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr, Field

from .database import get_db, init_db

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


class DeleteResponse(BaseModel):
    detail: str


class MessageFileResponse(BaseModel):
    id: int
    file_name: str
    file_path: str
    mime_type: Optional[str] = None
    size_bytes: Optional[int] = None


class MessageResponse(BaseModel):
    id: int
    user_id: int
    sender_type: str
    content: str
    created_at: str
    files: List[MessageFileResponse] = []


BASE_DIR = Path(__file__).resolve().parent
UPLOAD_ROOT = Path(os.environ.get("CHAT_UPLOAD_ROOT", BASE_DIR / "chat_uploads"))
UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)


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
        sender_type=row["sender_type"],
        content=row["content"],
        created_at=row["created_at"],
        files=files or [],
    )


def ensure_user_upload_dir(user_id: int) -> Path:
    folder = UPLOAD_ROOT / f"user_{user_id}"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


async def persist_upload_file(upload_file: UploadFile, user_id: int) -> tuple[str, str, int]:
    dest_dir = ensure_user_upload_dir(user_id)
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


@app.post("/api/messages", response_model=MessageResponse)
async def create_message(
    content: str = Form(...),
    sender_type: str = Form("user"),
    files: Union[UploadFile, List[UploadFile], None] = File(default=None),
    db: sqlite3.Connection = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
) -> MessageResponse:
    sender_type = sender_type.lower()
    if sender_type not in {"user", "assistant"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid sender type")
    if sender_type == "assistant" and current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only admins can create assistant messages")

    cursor = db.execute(
        "INSERT INTO message (user_id, sender_type, content) VALUES (?, ?, ?)",
        (current_user.id, sender_type, content),
    )
    message_id = cursor.lastrowid

    upload_list: List[UploadFile] = []
    if files is None:
        upload_list = []
    elif isinstance(files, (list, tuple, set)):
        upload_list = [item for item in files if hasattr(item, "filename")]
    elif isinstance(files, dict):
        upload_list = [item for item in files.values() if hasattr(item, "filename")]
    elif hasattr(files, "filename"):
        upload_list = [files]  # treat single UploadFile-like object
    elif isinstance(files, Iterable):
        upload_list = [item for item in files if hasattr(item, "filename")]

    saved_files: List[MessageFileResponse] = []
    for upload_file in upload_list:
        original_name, relative_path, size = await persist_upload_file(upload_file, current_user.id)
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

    db.commit()
    message_row = db.execute("SELECT * FROM message WHERE id = ?", (message_id,)).fetchone()
    return row_to_message(message_row, saved_files)


@app.get("/api/messages", response_model=List[MessageResponse])
def list_messages(
    user_id: Optional[int] = None,
    db: sqlite3.Connection = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
) -> List[MessageResponse]:
    target_user_id = user_id or current_user.id
    if current_user.role != "admin" and target_user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    rows = db.execute(
        "SELECT * FROM message WHERE user_id = ? ORDER BY created_at ASC",
        (target_user_id,),
    ).fetchall()
    return [row_to_message(row, get_message_files(db, row["id"])) for row in rows]
