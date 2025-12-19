---
> 📘 本文件補充 README 未詳述的內容：後端環境設定、API 行為、檔案儲存策略、測試與常見疑難排解。若只想快速啟動專案，可先閱讀 README，再回來查表。

## ✅ TODO / 後續優化想法

- [ ] **行動端體驗**：ChatView 側邊欄在手機上應改為抽屜式，按鈕與輸入區需放大。
- [ ] **Markdown / 程式碼高亮**：在 `ChatMessage.vue` 導入 `markdown-it` + `highlight.js`，並加上複製按鈕。
- [ ] **串流訊息**：將 `/api/messages` 的回覆改為 SSE/WebSocket，並在前端加入「停止」控制。
- [ ] **對話層模型設定**：conversation metadata 可包含 model、temperature、system prompt 等。
- [ ] **IndexedDB/LocalStorage 緩存**：未登入時可保留歷史紀錄並與雲端同步。
- [ ] **CI/CD**：建立 GitHub Actions 於 PR 執行 `npm run build` + `pytest`。
- [ ] **品牌化/i18n**：導入 `vue-i18n`；所有色票、文案抽出成設定檔。

可依專案需求在此清單上持續補充，以追蹤後續演進。

---

## ⚙️ 後端（FastAPI + SQLite）架構概覽

```
backend/
├── main.py               # FastAPI 單檔應用，內含 auth / conversations / messages APIs
├── database.py           # SQLite 初始化與連線工具，支援 SIMPLECHAT_DB_PATH 覆寫
├── chat_uploads/         # 使用者附件，會依 user_{id}[_displayname]/ 分類
├── tests/                # pytest 測試（auth + conversations + messages）
└── requirements.txt
```

- **認證**：`/api/auth/register`、`/api/auth/login`、`/api/auth/me`。第一位註冊者自動成為 `admin`；程式碼在 `backend/main.py` 的 `register_user()` 會檢查 `SELECT COUNT(*) FROM user`，若為 0 就設定 `role="admin"`。JWT 以 `SECRET_KEY` 簽署。
- **對話**：`conversation` 表保存每位使用者的多輪對話列表，API 提供 CRUD 並檢查擁有者／管理員權限。
- **訊息**：`message` 表與 `message_file` 表記錄每則訊息與附件，並與 `conversation_id` 關聯。
- **附件儲存**：所有上傳檔案存於 `backend/chat_uploads/user_<id>_<display_name_slug>/UUID_原檔名`。`display_name` 會做 sanitize（非英數轉 `_`、前後去除 `_`）；若沒有顯示名稱，則僅 `user_<id>`。靜態路徑由 `app.mount('/chat_uploads', ...)` 提供。
- **預設回覆**：`build_simulated_reply()` 目前只是示範；要串接實際 LLM 時，請替換該函式與相關儲存邏輯。

詳細 Schema 請參考 `DB_SCHEMA.md`。

---

## 🛠 後端環境設定

1. **建立虛擬環境並安裝依賴**
   ```powershell
   cd backend
   python -m venv .venv
   .\.venv\Scripts\activate
   pip install -r requirements.txt
   ```
2. **設定環境變數（.env）**
   ```
   SECRET_KEY=<請使用 openssl rand -hex 32 產生>
   SIMPLECHAT_DB_PATH=backend/simplechat.db        # 可選
   CHAT_UPLOAD_ROOT=backend/chat_uploads           # 可選
   ```
3. **啟動 API**
   ```powershell
   uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
   ```
   - `http://localhost:8000/docs` 為 Swagger UI。
   - 第一次啟動會自動建立 SQLite DB 與 `chat_uploads/` 目錄。

4. **依賴說明**
   - `fastapi`, `uvicorn[standard]`: 服務主架構。
   - `python-jose[cryptography]`: JWT。
   - `passlib[bcrypt]` + `bcrypt==4.1.2`: 密碼雜湊。
   - `python-multipart`: 處理上傳。
   - `python-dotenv`: 載入 `.env`。
   - `httpx==0.26.0`, `pytest`: 後端測試。

---

## 🔌 API 速覽

| 類別 | Method & Path | 說明 |
|------|---------------|------|
| Auth | `POST /api/auth/register` | 建立帳號；第一位使用者自動升為 admin（`register_user()` 內檢查 user 數量為 0 即設定 role=admin）。 |
|      | `POST /api/auth/login`    | 回傳 `{ access_token, user }`。 |
|      | `GET /api/auth/me`        | 取得登入者資訊。 |
| Users | `GET /api/users` (admin) | 列出所有使用者。 |
|      | `GET/PATCH/DELETE /api/users/{id}` | 本人可查/改自身，admin 可管理所有人。 |
| Conversations | `GET /api/conversations` | 回傳使用者的所有對話，並附上訊息數。 |
|               | `POST /api/conversations` | 建立新對話。 |
|               | `PATCH /api/conversations/{id}` | 修改標題。 |
|               | `DELETE /api/conversations/{id}` | 刪除對話（含訊息/附件）。 |
| Messages | `POST /api/messages` | 需要 `conversation_id`，同時支援多附件。回傳 `message` 以及模擬回覆（若助手回覆尚在生成則 `status=pending`）。 |
|          | `GET /api/messages` | 依 `conversation_id`、`user_id` 查詢。`include_assistant=true` 可取得助手訊息與其狀態。 |
|          | `POST /api/messages/{id}/stop` | 停止尚未完成的助手訊息，並在資料庫紀錄 `status='cancelled'` 與 `stopped_at`。 |

> 使用者角色規則：一般使用者只能操作自己的 conversation / messages；`admin` 可跨使用者查詢。

---

## 🗃️ 資料表 Schema 摘要

詳見 `DB_SCHEMA.md`，以下為重點對照：

| 表名 | 主要欄位 | 說明 |
|------|----------|------|
| `user` | `id, email, password_hash, role, display_name, created_at, last_login_at` | 登入帳號；第一位註冊者會被 `register_user()` 設為 `admin`，同時自動建立一個預設 conversation。 |
| `conversation` | `id, user_id, title, created_at, updated_at` | 每位使用者可以有多個對話，刪除時會 cascade 刪除訊息與附件。 |
| `message` | `id, user_id, conversation_id, sender_type, content, created_at` | 文字內容、訊息來源（user/assistant），需指向一個 conversation。 |
| `message_file` | `id, message_id, file_name, file_path, mime_type, size_bytes, created_at` | 每個附件一筆紀錄；實體檔案存於 `chat_uploads/user_<id>_<slug>/`，slug 由 `display_name` 轉換。 |

`database.py` 會在 `init_db()` 時建立上述表單，並且如果既有 `message` 表缺少 `conversation_id` 欄位，會以 `ALTER TABLE` 自動補上。

---

## 🧪 測試

- 測試檔：`backend/tests/test_auth_users.py`, `backend/tests/test_messages.py`
- 工具：`pytest` + FastAPI `TestClient`
- 執行：
  ```powershell
  cd backend
  .\.venv\Scripts\activate
  pytest tests -q
  ```
- 內容涵蓋：
  - 帳號註冊、登入、角色檢查。
  - 對話 CRUD、權限限制。
  - 文字與附件訊息、跨對話隔離。
  - 管理員發送 assistant 訊息、模擬回覆等。

若測試需要清空 DB，只要刪除 `backend/simplechat.db` 後重新啟動即可。

---

## 🖥️ 前端整合重點

- **環境變數**（`frontend/.env` 或 `.env.development`）：
  ```
  VITE_API_BASE_URL=http://localhost:8000/api
  VITE_UPLOAD_BASE_URL=http://localhost:8000/chat_uploads
  ```
- **登入/註冊**：`src/stores/auth.js` 直接呼叫後端 API；登入成功會把 `user` 與 `token` 存到 localStorage。
- **對話/訊息流程**：`src/stores/chat.js`
  1. `initialize()` 先載入 `GET /api/conversations`，若沒有會自動建立一筆。
  2. `selectConversation()` 呼叫 `GET /api/messages?conversation_id=...`.
  3. `sendMessage()` 以 `FormData` 將 `conversation_id`, `content`, `files` 傳給 `/api/messages`。若後端回傳的助手訊息 `status = pending`，Pinia 會顯示停止按鈕並透過 `schedulePendingRefresh()` 自動輪詢；使用者按下停止時，`chatStore.stopGenerating()` 會呼叫 `POST /api/messages/{id}/stop` 更新狀態。
  4. 附件 URL 透過 `buildUploadUrl` 指向 `VITE_UPLOAD_BASE_URL`。

前端開發指令：
```bash
npm install
npm run dev
```

---

## 🚀 部署注意事項

- **反向代理 / HTTPS**：在 production 以 Nginx 或 Caddy 代理 `uvicorn`，統一 TLS 與靜態檔案服務。
- **CORS**：更新 `CORSMiddleware` 的 `allow_origins` 為實際網域。
- **SECRET_KEY & DB**：以環境變數或 secret manager 管理；production DB 請用 Postgres/MySQL 等更可靠方案。
- **檔案儲存**：建議改用 S3/GCS 等物件儲存並在 `CHAT_UPLOAD_ROOT` 指向掛載點，或改寫 `persist_upload_file()` 直接傳上雲端。
- **排程 / Log**：若未串接真正的模型，可將 `build_simulated_reply()` 換成呼叫 LLM API；並在日志中記錄錯誤（ex: Sentry）。

---

## ❓ 常見問題

- **bcrypt 錯誤 `AttributeError: module 'bcrypt' has no attribute '__about__'`**
  - 請安裝 `bcrypt==4.1.2`（`pip install bcrypt==4.1.2`），並確認沒有其他舊版殘留。
- **`SECRET_KEY` 暴露**
  - 別把密鑰寫進程式碼；使用 `.env` 或部署環境提供的 Secrets。
- **附件抓不到**
  - 確認 `VITE_UPLOAD_BASE_URL` 與後端 `app.mount('/chat_uploads', ...)` 對應，且檔案存在於 `chat_uploads/user_<id>/`。
- **測試失敗 (HTTP 405 on OPTIONS)**
  - 需要 CORS 設定；`backend/main.py` 已預設 `http://localhost:5173`，如改用其他域名請同步調整。

如需更多協助或要擴充新功能，歡迎在 issue 或討論區提出。***
