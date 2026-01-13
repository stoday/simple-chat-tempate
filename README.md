# SimpleChat – AI 對話機器人範本

一套後端友善的多用戶 AI 聊天系統，讓只懂 Python 的開發者也能快速建立可用的對話服務。內建完整的用戶認證、對話管理、檔案上傳、RAG 知識庫等功能，並且可以輕鬆替換成自己的 LLM 模型。

---

## ✨ 主要功能

- **🔐 用戶系統**：註冊、登入、角色權限管理（User / Admin）
- **💬 多對話管理**：每位用戶可建立多個對話，支援重命名、刪除
- **📎 檔案上傳**：支援多檔案上傳，自動分類儲存
- **🧠 RAG 知識庫**：管理員可上傳共用文件作為背景知識
- **⚙️ 動態配置**：管理員可即時調整 LLM 模型、Temperature、System Prompt
- **🎨 主題自訂**：透過 `config.toml` 客製品牌、色票、角色設定
- **🔄 串流回應**：支援 AI 逐字串流輸出，提升使用者體驗
- **🤖 Agent 緩存**：代理緩存機制，提升回應速度

---

## 📋 系統需求

- **Python**: 3.8 以上
- **Node.js**: 16 以上（前端需要）
- **作業系統**: Windows / macOS / Linux

---

## 🚀 安裝步驟

### 1️⃣ 後端安裝

#### (1) 建立虛擬環境
```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\activate
```

#### (2) 安裝依賴套件
```powershell
pip install -r requirements.txt
```

#### (3) 設定環境變數
在專案根目錄建立 `.env` 檔案：
```env
# JWT 密鑰（必須）
SECRET_KEY=<請使用 openssl rand -hex 32 產生>

# LLM Modle Provider API Key
Ex: GEMINI_API_KEY=<your_gemini_api_key_here>

# Google Custom Search（選用，啟用搜尋工具時需要）
GSEARCH_API_KEY=your_google_search_api_key
SEARCH_ENGINE_ID=your_search_engine_id

# 資料庫與檔案路徑（選用）
SIMPLECHAT_DB_PATH=backend/simplechat.db
CHAT_UPLOAD_ROOT=backend/chat_uploads
```

> 💡 **提示**：產生 SECRET_KEY 的方法：
> - Windows (PowerShell): `openssl rand -hex 32`
> - Linux / macOS: `openssl rand -hex 32`

### 2️⃣ 前端安裝（可選）

如果需要使用內建的 Web UI：

```bash
# 安裝依賴
npm install
```

在專案根目錄建立 `.env` 檔案（或 `.env.development`）：
```env
VITE_API_BASE_URL=http://localhost:8000/api
VITE_UPLOAD_BASE_URL=http://localhost:8000/chat_uploads
```

---

## ▶️ 啟動方式

### 啟動後端

```powershell
# 確保虛擬環境已啟動
cd backend
.\.venv\Scripts\activate

# 啟動 FastAPI 服務
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

**啟動成功後：**
- API 文檔（Swagger UI）：`http://localhost:8000/docs`
- 首次啟動會自動建立 SQLite 資料庫與檔案儲存目錄
- 第一位註冊的使用者會自動成為 `admin`

### 啟動前端（可選）

```bash
npm run dev
```

**啟動成功後：**
- 前端介面：`http://localhost:5173/`

---

## 📚 文檔結構

詳細文檔已整理至 `docs/` 資料夾：

| 文件 | 說明 |
|------|------|
| [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) | 完整的開發指南：後端環境設定、API 詳解、測試指令、部署建議 |
| [`docs/DB_SCHEMA.md`](docs/DB_SCHEMA.md) | 資料庫 Schema 定義與欄位說明 |
| [`docs/DOMAIN_CONFIG.md`](docs/DOMAIN_CONFIG.md) | 跨網域部署時的配置說明 |
| [`docs/MIGRATION_GUIDE.md`](docs/MIGRATION_GUIDE.md) | 從舊版本遷移的指南 |
| [`docs/implementation_plan.md`](docs/implementation_plan.md) | 系統實作規劃與架構設計 |

---

## 🔌 LLM 串接入口（核心功能）

本專案已經將「接收使用者訊息 → 呼叫 LLM → 回傳結果」的流程完整整合。如果要替換成自己的 LLM 或其他服務，請從以下兩個檔案著手：

### 修改位置

1. **`backend/main.py`**  
   - `_run_reply_worker()` 函式：處理訊息生成的主要邏輯
   - 目前使用 `akasha` agent 產生回覆

2. **`backend/tools.py`**  
   - `get_agent()` 函式：配置 Agent 與工具
   - 可在此調整模型、工具、提示詞等設定

### 流程概述

```
使用者發送訊息
    ↓
POST /api/messages（建立 user 訊息 + assistant pending 訊息）
    ↓
_run_reply_worker（背景執行）
    ↓
呼叫 LLM（akasha agent）產生回覆
    ↓
更新 assistant 訊息內容與狀態
    ↓
前端輪詢或串流顯示結果
```

### 支援功能

- ✅ **串流輸出**：支援逐字輸出，提升使用者體驗
- ✅ **停止生成**：使用者可隨時中止 AI 回覆（`POST /api/messages/{id}/stop`）
- ✅ **自動命名**：根據對話內容自動產生對話標題
- ✅ **工具調用**：內建搜尋、檔案讀取、MSSQL 查詢等工具

---

## 🎨 主題與品牌自訂

透過專案根目錄的 `config.toml` 可以客製化：

```toml
[branding]
app_name = "SimpleChat"
brand_icon = "🤖"
empty_state_icon = "💬"
subtitle = "與 AI 對話從這裡開始"

[theme]
preset = "tech"              # 預設主題：tech / warm / minimal

[theme.colors]
primary = "#3B82F6"          # 主要色
accent = "#8B5CF6"           # 強調色
background = "#0F172A"       # 背景色

[roles]
default_role = "user"        # 新註冊使用者的預設角色
available_roles = ["user", "admin", "analyst"]
```

修改後記得重啟後端與前端。

---

## 📂 專案結構速覽

```
P2025_SIMPLECHAT/
├── backend/                    # 後端（FastAPI）
│   ├── main.py                 # API 主程式、LLM 串接入口
│   ├── database.py             # SQLite 初始化與連線
│   ├── tools.py                # Agent 工具與設定
│   ├── rag_state.py            # RAG 狀態管理
│   ├── requirements.txt        # Python 依賴
│   ├── chat_uploads/           # 使用者上傳檔案
│   ├── rag_files/              # 管理員上傳的 RAG 檔案
│   ├── Knowledge/              # RAG 知識庫索引
│   └── tests/                  # pytest 測試檔
│
├── src/                        # 前端（Vue.js）
│   ├── components/             # Vue 元件
│   ├── stores/                 # Pinia 狀態管理
│   ├── views/                  # 頁面
│   └── router/                 # 路由設定
│
├── docs/                       # 詳細文檔
│   ├── DEVELOPMENT.md          # 開發指南
│   ├── DB_SCHEMA.md            # 資料庫 Schema
│   ├── DOMAIN_CONFIG.md        # 網域配置
│   └── MIGRATION_GUIDE.md      # 遷移指南
│
├── config.toml                 # 系統配置檔
├── .env                        # 環境變數（需自行建立）
└── README.md                   # 本檔案
```

---

## 🧪 測試

執行後端測試：

```powershell
cd backend
.\.venv\Scripts\activate
pytest tests -v
```

測試涵蓋：
- ✅ 使用者註冊、登入、權限
- ✅ 對話 CRUD 與權限隔離
- ✅ 訊息發送與附件上傳
- ✅ Admin 專屬功能

> 如需清空測試資料，刪除 `backend/simplechat.db` 即可。

---

## 🔧 延伸建議

- **串流回覆**：可改用 Server-Sent Events (SSE) 或 WebSocket 提升即時性
- **雲端儲存**：將 `chat_uploads/` 改存至 S3 / GCS
- **資料庫升級**：Production 環境建議改用 PostgreSQL / MySQL
- **CI/CD**：使用 GitHub Actions 自動執行 `pytest` 與前端 build
- **監控與日誌**：整合 Sentry 或 ELK Stack

---

## 📞 常見問題

詳見 [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) 的「常見問題」章節。

---

## 📄 授權

此專案可自由修改與使用。
