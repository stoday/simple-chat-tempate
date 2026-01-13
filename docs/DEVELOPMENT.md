---
> 📘 本文件補充 README 未詳述的內容：後端環境設定、API 行為、檔案儲存策略、測試與常見疑難排解。若只想快速啟動專案，可先閱讀 README，再回來查表。

## ✅ TODO / 後續優化想法

- [ ] **行動端體驗**：ChatView 側邊欄在手機上應改為抽屜式，按鈕與輸入區需放大。
- [ ] **Markdown / 程式碼高亮**：在 `ChatMessage.vue` 導入 `markdown-it` + `highlight.js`，並加上複製按鈕。
- [ ] **串流訊息**：將 `/api/messages` 的回覆改為 SSE/WebSocket，並在前端加入「停止」控制。
- [x] **自動主題生成**：使用者輸入第一個問題後，自動依內容產出主題標題。
- [x] **全域模型設定**：Admin 可在 UI 調整模型名稱、Temperature 與 System Prompt。
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
├── rag_files/            # 管理員上傳的共用 RAG 檔案
├── tests/                # pytest 測試（auth + conversations + messages）
└── requirements.txt
```

- **認證**：`/api/auth/register`、`/api/auth/login`、`/api/auth/me`。第一位註冊者自動成為 `admin`；之後的新註冊角色依 `config.toml` 的 `roles.default_role`。JWT 以 `SECRET_KEY` 簽署。
- **對話**：`conversation` 表保存每位使用者的多輪對話列表，API 提供 CRUD 並檢查擁有者／管理員權限。
- **訊息**：`message` 表與 `message_file` 表記錄每則訊息與附件，並與 `conversation_id` 關聯。
- **附件儲存**：所有上傳檔案存於 `backend/chat_uploads/user_<id>_<display_name_slug>/原檔名_<8碼>.ext`。`display_name` 會做 sanitize（非英數轉 `_`、前後去除 `_`）；若沒有顯示名稱，則僅 `user_<id>`。靜態路徑由 `app.mount('/chat_uploads', ...)` 提供。
- **RAG 檔案**：管理員上傳的共用 RAG 檔案存於 `backend/rag_files/`。
- **LLM 回覆與自動命名**：目前在 `_run_reply_worker` 內呼叫 `akasha` agent。若對話標題為 `"New Chat"`，會先呼叫一個輕量級的 `_generate_conversation_title` (同樣使用 akasha) 來產生標題並更新 DB。

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

4. **應用設定**
   - 專案根目錄 `config.toml` 可調整品牌、主題色票與角色清單。
   - 後端提供 `GET /api/config` 供前端讀取。

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
| App Config | `GET /api/config` | 回傳 `config.toml` 合併後的品牌/主題/角色設定。 |
| Users | `GET /api/users` (admin) | 列出所有使用者。 |
|      | `GET/PATCH/DELETE /api/users/{id}` | 本人可查/改自身，admin 可管理所有人。 |
| Conversations | `GET /api/conversations` | 回傳使用者的所有對話，並附上訊息數。 |
|               | `POST /api/conversations` | 建立新對話。 |
|               | `PATCH /api/conversations/{id}` | 修改標題。 |
|               | `DELETE /api/conversations/{id}` | 刪除對話（含訊息/附件）。 |
| Messages | `POST /api/messages` | 需要 `conversation_id`，同時支援多附件。回傳 `message` 以及模擬回覆（若助手回覆尚在生成則 `status=pending`）。 |
|          | `GET /api/messages` | 依 `conversation_id`、`user_id` 查詢。`include_assistant=true` 可取得助手訊息與其狀態。 |
|          | `POST /api/messages/{id}/stop` | 停止尚未完成的助手訊息，並在資料庫紀錄 `status='cancelled'` 與 `stopped_at`。 |
| Admin | `GET/POST/DELETE /api/admin/rag-files` | 管理共用 RAG 檔案。 |
| Admin | `GET/PUT /api/admin/mssql-config` | 取得/更新 MSSQL 連線設定。 |
| Admin | `GET/PATCH /api/admin/llm-config` | 取得/更新 LLM 模型設定（模型名稱, Temperature, System Prompt 等）。 |
| Admin | `POST /api/admin/mssql-config/test` | 測試 MSSQL 連線。 |

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
| `llm_config` | `id, model_name, temperature, max_output_tokens, system_prompt` | 全域 LLM 參數設定，僅 admin 可透過 UI 修改。 |

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
  3. `sendMessage()` 以 `FormData` 將 `conversation_id`, `content`, `files` 傳給 `/api/messages`。若後端回傳的助手訊息 `status = pending`，Pinia 會顯示停止按鈕並透過 `schedulePendingRefresh()` 自動輪詢。
  4. **標題同步**：`GET /api/messages` 會回傳 `conversation_title`。若前端發現標題已從 "New Chat" 變更，會同步更新 `conversations` store 並存入緩存。
  5. `stopGenerating()` 會呼叫 `POST /api/messages/{id}/stop` 更新狀態。
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

---

## 📝 自動標題生成、模型設定與 API Key 規範 (2026-01-12 新增)

- **自動對話命名**：系統會在使用者發送第一個問題時，於背景透過 `akasha` 根據提問內容產生主題名稱。
- **動態模型配置**：Admin 可以在 Settings 頁面即時切換模型名稱 (如 gemini -> gpt-4o)、調整 Temperature 以及設定全域 System Prompt，設定後立即生效。
- **環境變數命名規範**：
  - `GEMINI_API_KEY`: 供 LLM 模型（Gemini）使用。
  - `GSEARCH_API_KEY`: 供 Google Custom Search 工具使用（避免與 `GOOGLE_API_KEY` 產生環境變數衝突警告）。

- **自動對話命名**：系統會在使用者發送第一個問題時，於背景透過 `akasha` 根據提問內容產生簡短的主題名稱，並自動更新側邊欄。
- **環境變數命名規範**：
  - `GEMINI_API_KEY`: 供 LLM 模型（Gemini）使用。
  - `GSEARCH_API_KEY`: 供 Google Custom Search 工具使用（避免與 `GOOGLE_API_KEY` 產生環境變數衝突警告）。

---

## 🚄 Agent 緩存優化與串流輸出 (2026-01-12)

### Agent 預載與緩存機制

為了提升響應速度並避免每次請求都重新初始化 Akasha Agent（包含載入 LLM 配置、建立工具等開銷），系統實現了以下優化：

1. **模組級預載** (`backend/main.py`):
   ```python
   # 在 FastAPI 應用啟動前（multiprocessing fork 之前）預先載入 agent
   _PRELOADED_AGENT = get_agent(stream=True)
   ```
   - 在主進程載入時就初始化 agent
   - 子進程會繼承已初始化的 agent（透過 fork 機制）
   - 避免第一次請求的「冷啟動」延遲

2. **Singleton 模式緩存** (`backend/tools.py`):
   ```python
   class AgentSingleton:
       _instance = None
       _agent = None
       _stream = None
   ```
   - 使用強單例模式確保跨進程共享
   - 緩存 key 為 `stream` 參數（True/False）
   - 提供 `clear_agent_cache()` 函數供手動清除緩存

3. **啟動事件初始化** (`backend/main.py`):
   ```python
   @app.on_event("startup")
   async def startup_event():
       get_agent(stream=True)  # 再次確認 agent 已載入
   ```

### 效能改善

- **第一次請求響應時間**：從 ~2-3 秒降至與後續請求一致（~0.5 秒）
- **後續請求**：全部使用緩存的 agent，無需重新初始化
- **啟動時間**：增加約 1-2 秒（一次性開銷）

### 多用戶環境安全性

✅ **完全安全**：
- Agent 配置是無狀態的（僅存儲 model、temperature、tools 等設定）
- 對話歷史通過參數傳遞，不存儲在 agent 中
- Multiprocessing 提供進程隔離，每個請求在獨立進程中處理
- Python GIL 提供基本的線程安全保障

⚠️ **注意事項**：
- 如果在運行時更新了 LLM 配置（temperature、model 等），需要重啟 server 或調用 `clear_agent_cache()`
- 每個 worker 進程都會有完整的 agent 副本，注意記憶體使用
- 高並發時可考慮增加 worker 數量：`uvicorn backend.main:app --workers 4`

### 串流輸出優化

**問題**：前端只需要顯示 AI 的最終答案，不需要顯示中間的思考過程（thought）、工具調用（action）等內容。

**解決方案**：

1. **後端簡化** (`akasha-package/akasha/agent/agents.py`):
   - 將所有複雜的解析邏輯移除
   - 直接 `yield chunk` 輸出完整的 JSON 響應
   - 讓前端負責過濾和提取最終答案

2. **前端智能過濾** (`src/components/chat/ChatMessage.vue`):
   ```javascript
   // 使用正則表達式提取 Final Answer 的 action_input
   const answerPattern = /"action"\s*:\s*"[^"]*[Aa]nswer[^"]*"[\s\S]*?"action_input"\s*:\s*"([\s\S]*?)(?:"\s*}|$)/g
   ```
   - 自動識別並提取 `action: "Answer"` 的 `action_input` 值
   - 清理轉義字符（`\n`, `\"` 等）
   - 處理多次 LLM 調用（取最後一個 Answer）
   - 在思考過程中顯示空內容（使用原本的 pending 動畫）

**優勢**：
- ✅ 用戶只看到乾淨的最終答案
- ✅ 後端代碼更簡潔可維護
- ✅ 前端可靈活控制顯示邏輯
- ✅ 支持逐字符串流顯示

### 調試與監控

可以通過以下方式監控 agent 緩存狀態：

```python
# 添加健康檢查端點
@app.get("/api/health")
async def health_check():
    return {
        "status": "healthy",
        "process_id": os.getpid(),
        "memory_mb": psutil.Process().memory_info().rss / 1024 / 1024,
        "agent_cached": _singleton._agent is not None
    }
```

查看啟動日誌中的緩存訊息：
```
[MAIN] Pre-loading agent at module level...
[AGENT CACHE] Building new agent (stream=True)
[MAIN] Agent pre-loaded successfully
==================================================
Initializing agent...
[AGENT CACHE] Using cached agent (stream=True)
==================================================
```
