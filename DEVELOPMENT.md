---
> 📘 這份文件補充了 README.md 沒寫到的細節，包含 FastAPI 範例、API 設計、以及進階開發建議。若只想快速啟動專案，可先閱讀 README。

## ✅ TODO / 後續優化建議

以下是將 SimpleChat 打造成「多應用範本」時常見的延伸項目，可依需求勾選實作：

- [ ] **行動版與小螢幕優化**：ChatView 的側邊欄與訊息區分離顯示、調整按鈕大小與間距。
- [ ] **Markdown 與程式碼高亮**：在 `ChatMessage.vue` 整合 `markdown-it`、`highlight.js` 或自訂 renderer，並加上「複製程式碼」按鈕。
- [ ] **串流回覆 / Stop 控制**：在 `chat` store 改為 SSE 或 WebSocket，並在 `ChatInput.vue` 加入「停止產生」按鈕與 token-by-token 更新。
- [ ] **對話層級設定**：讓每個 conversation 都能記住模型、溫度、system prompt 等參數，並在 UI 顯示摘要。
- [ ] **本地儲存與同步**：將 conversations/messages 快取到 IndexedDB 或 localStorage，供未登入/離線使用，並提供與伺服器同步機制。
- [ ] **測試與 CI**：使用 Vitest 測 store、Cypress 做 E2E 冒煙測試，並在 CI pipeline 執行 `npm run build`。
- [ ] **i18n 與品牌化**：導入 `vue-i18n`，並把主要文案、色票抽成設定檔，好快速套用到不同專案。

> 其餘尚未排程的想法（例如使用者 analytics、角色管理…）可以在此章節持續追加，維持範本的可視化待辦列表。

## ⚙️ FastAPI 後端建置步驟（詳細）

下面提供一份從零開始在本機建立 FastAPI 後端的實務步驟，包含必要套件、範例路由（含檔案上傳）、啟動指令與前端如何配置環境變數。
### 1. 建立資料夾結構

建議在專案根目錄旁建立獨立的 `backend/` 資料夾：
```
backend/
├── main.py
├── routers/
│   └── upload.py
├── uploads/          # 上傳檔案存放（可加入 .gitignore）
├── requirements.txt
└── .env              # 可選：環境變數

### 2. 建立虛擬環境並安裝套件（Windows PowerShell）
```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install fastapi uvicorn python-multipart aiofiles python-dotenv
pip freeze > requirements.txt

必要套件說明：
- `fastapi`：主框架
- `uvicorn`：ASGI server（開發用）
- `python-multipart`：支援 multipart/form-data（上傳）
- `aiofiles`：非同步寫檔
- `python-dotenv`：載入 `.env`（可選）

### 3. 範例：`backend/routers/upload.py`
```python
from fastapi import APIRouter, UploadFile, File
from typing import List
import aiofiles
import os

router = APIRouter()
@router.post('/upload')
async def upload_files(files: List[UploadFile] = File(...)):
  os.makedirs('uploads', exist_ok=True)
  urls = []
  for f in files:
    save_path = os.path.join('uploads', f.filename)
    async with aiofiles.open(save_path, 'wb') as out_file:
      content = await f.read()
      await out_file.write(content)
    # 回傳前端可用的檔案 metadata（可以改成完整 URL）
    urls.append({'name': f.filename, 'size': os.path.getsize(save_path), 'url': f'/uploads/{f.filename}'})
  return {'files': urls}
### 4. 範例：`backend/main.py`（最簡化）

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from routers import upload
app = FastAPI(title='SimpleChat API')

app.add_middleware(
  CORSMiddleware,
  allow_origins=["http://localhost:5173"],
  allow_credentials=True,
  allow_methods=["*"],
  allow_headers=["*"],
)
app.include_router(upload.router, prefix='/api')
app.mount('/uploads', StaticFiles(directory='uploads'), name='uploads')

@app.get('/')
async def root():
  return {'message': 'SimpleChat API running'}

if __name__ == '__main__':
  import uvicorn
  uvicorn.run('main:app', host='0.0.0.0', port=8000, reload=True)
```
### 5. 啟動後端（開發模式）

在 `backend` 內的虛擬環境中執行：

```powershell
.\.venv\Scripts\Activate.ps1
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```
開啟 `http://localhost:8000/docs` 可看到自動產生的 swagger UI。
專案根目錄啟動（推薦：避免 `from .database` 匯入錯誤），命令要改用完整模組路徑：
```powershell
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

### 5.1 訊息 API 串接與後續 LLM TODO

- `POST /api/messages` 現在同時接受文字（`content`）與多個附件（`files`）。檔案會儲存在 `backend/chat_uploads/` 下並透過 `app.mount('/chat_uploads', ...)` 對外提供靜態存取。
- 後端在成功建立使用者訊息後，會呼叫 `backend/main.py` 內的 `build_simulated_reply()` 產生暫時回覆並存入資料庫。未來要串接大語言模型時，請在此函式中改為呼叫真正的 LLM（程式碼已在註解中標示 TODO）。
- 前端則在 `src/stores/chat.js` 的 `sendMessage()` 以 `FormData` 將文字與檔案直接送到 `/api/messages`，並在拿到 `message`/`simulated_reply` 後更新 Pinia state。若日後要串接 LLM，可在這裡調整對回應欄位的處理（或增加流式更新）。
- 歷史訊息會在 `chatStore.loadMessages()` 透過 `GET /api/messages` 取得，附件 URL 則由 `VITE_UPLOAD_BASE_URL` 組合（預設對應 `http://localhost:8000/chat_uploads`）。

### 6. 前端設定（Vite）

在前端專案根目錄建立或修改 `.env`（或 `.env.development`）：
```
VITE_API_BASE_URL=http://localhost:8000/api
VITE_UPLOAD_BASE_URL=http://localhost:8000/chat_uploads
```
前端的 `src/services/api.js` 會使用 `import.meta.env.VITE_API_BASE_URL` 作為基底 URL（已在專案中預設），因此設定該環境變數後，前端請求會導向 FastAPI。`VITE_UPLOAD_BASE_URL` 則提供訊息附件的下載/預覽來源，預設與後端 `app.mount('/chat_uploads', ...)` 對應。

提示（在 Windows PowerShell 啟動 dev server 時）:
```powershell
# 在專案根目錄
npm run dev
```
若你想在本機同時啟動前後端，先啟後端（port 8000），再啟前端（Vite，port 5173）。

### 7. Production / 部署建議（簡要）

- 使用 uvicorn + gunicorn（或 uvicorn 的 production 設定）搭配 systemd 或 Docker 容器化。
- 在生產環境下請設定正確的 `allow_origins`（不要使用 `*`），並將上傳儲存改為使用雲端物件儲存（S3）、或把 `uploads/` 放到 NFS / 雲儲存中。
- 加入驗證與權限控制：上傳路由應檢查 user 與檔案大小、擴展名白名單等。

---

如果你希望，我可以：
- 幫你在 `backend/` 中建立上述範例檔案（`main.py`, `routers/upload.py`, `requirements.txt`），或
- 加入一個 Dockerfile 與 docker-compose 範例以便快速啟動（前端 + 後端）。

要我直接建立後端範例檔案或 Docker 設定嗎？
# SimpleChat 開發指南

本文檔專為熟悉 Python 但不熟悉 Vue.js 的開發者設計，將帶您從零開始設置前端環境，並整合 FastAPI 後端。

---

## 📋 目錄

1. [前端環境設置](#前端環境設置)
2. [運行前端專案](#運行前端專案)
3. [前端專案結構](#前端專案結構)
4. [FastAPI 後端整合](#fastapi-後端整合)
5. [API 端點設計](#api-端點設計)
6. [前端修改步驟](#前端修改步驟)
7. [常見問題](#常見問題)

---

## 🔧 前端環境設置

### 1. 安裝 Node.js

**什麼是 Node.js？**
- 類似於 Python 的執行環境，但是給 JavaScript 用的
- npm 就像 Python 的 pip，用來管理套件

**安裝步驟：**

1. 前往 [https://nodejs.org/](https://nodejs.org/)
2. 下載 **LTS 版本**（推薦）
3. 執行安裝程式，一路下一步

**驗證安裝：**
```bash
node --version
# 應該顯示：v20.x.x 或類似版本

npm --version
# 應該顯示：10.x.x 或類似版本
```

### 2. 安裝專案依賴

在專案根目錄（`P2025_SIMPLECHAT`）下執行：
cd C:\Users\today\Dropbox\MainStorage\P2025_SIMPLECHAT
npm install
- 讀取 `package.json` 文件（類似 Python 的 `requirements.txt`）
- 套件會被安裝到 `node_modules/` 資料夾（類似 Python 的 `venv/`）

**常見錯誤：**
- 如果卡住不動，等待 5-10 分鐘（第一次會比較慢）
- 如果報錯，嘗試 `npm cache clean --force` 後重試

---

## 🚀 運行前端專案

### 開發模式（Development）
```bash
npm run dev

## TODO: 啟用 HTTPS / TLS
- 本地測試：安裝 `mkcert` 並信任本機 CA，為 `localhost`（或開發域）產生 `cert`/`key`，在 Vite `server.https` 或本地反代中使用以測試 `https://localhost:5173`。
- 前端 env：在開發與生產環境設置 `VITE_API_BASE_URL` 為 HTTPS（例如 `VITE_API_BASE_URL=https://your-domain/api`），確保打包後的請求走 `https://`。
- 後端 CORS：在 FastAPI 中將 `allow_origins` 加入實際的 HTTPS origin（例如 `https://your-domain`），生產環境不要使用 `*`。
- 反向代理：在生產使用 `nginx` 或 `caddy` 終止 TLS（Let’s Encrypt），並反向代理到內部 HTTP（例如 `127.0.0.1:8000`）；避免直接在公網上由 `uvicorn` 處理 TLS。
- 憑證管理：為生產伺服器設定自動續期（`certbot renew` 或 使用 Caddy 的自動 ACME），並監控憑證到期日。
- Docker/CI：在容器化部署中以環境變數注入 `VITE_API_BASE_URL`，並以 volume 或集中式憑證管理提供 TLS 憑證給反向代理容器。
- WebSocket：若使用 WebSocket，確保在 HTTPS 環境下使用 `wss://`，並讓 proxy 支援 WS 轉發。
- Cookies 與安全：設定 cookies 為 `Secure; HttpOnly; SameSite`（根據需求），並僅在 HTTPS 下傳送敏感憑證。
- 測試流程：部署完成後從瀏覽器訪問 `https://your-domain`，確認前端與 API 都走 `https://`、CORS 無誤、WebSocket (`wss`) 正常連線。
- 建議：生產環境讓反向代理（nginx/Caddy）負責 TLS，後端由 `gunicorn + uvicorn workers` 或 systemd 管理；僅在內網測試或特殊需求下使用 `uvicorn --ssl-certfile/--ssl-keyfile`。
```

**執行後會看到：**
```
VITE v5.x.x  ready in 500 ms

➜  Local:   http://localhost:5173/
➜  Network: use --host to expose
➜  press h + enter to show help
```

**打開瀏覽器訪問：** `http://localhost:5173/`

**如何停止？**
按 `Ctrl + C`（兩次）

### 生產構建（Production Build）

```bash
npm run build
```

這會將專案打包成靜態檔案，輸出到 `dist/` 資料夾。

---

## 📁 前端專案結構

```
P2025_SIMPLECHAT/
├── node_modules/          # 依賴套件（不用管）
├── public/                # 靜態資源
├── src/                   # 源代碼（主要工作區）
│   ├── assets/            # CSS、圖片等
│   │   └── css/
│   │       ├── variables.css   # 顏色、間距變數
│   │       ├── base.css        # 基礎樣式
│   │       └── reset.css       # CSS 重置
│   ├── components/        # Vue 元件（類似 React Components）
│   │   ├── chat/
│   │   │   ├── ChatMessage.vue    # 對話訊息元件
│   │   │   └── ChatInput.vue      # 輸入框元件
│   │   └── layout/
│   │       └── SidebarItem.vue    # 側邊欄項目元件
│   ├── stores/            # Pinia 狀態管理（類似 Redux）
│   │   ├── auth.js        # 用戶認證狀態
│   │   └── chat.js        # 聊天邏輯狀態
│   ├── services/          # API 服務層
│   │   └── api.js         # 🔥 這裡配置後端連線
│   ├── views/             # 頁面級元件
│   │   ├── ChatView.vue   # 主聊天頁面
│   │   └── LoginView.vue  # 登入頁面
│   ├── router/            # 路由配置
│   │   └── index.js       # 定義 URL 路徑
│   ├── App.vue            # 根元件
│   └── main.js            # 程式入口
├── index.html             # HTML 入口
├── package.json           # 依賴清單（類似 requirements.txt）
├── vite.config.js         # Vite 配置（類似 webpack）
└── DEVELOPMENT.md         # 本文檔
```

**重要概念對照：**
| Vue.js | Python 類比 |
|--------|------------|
| `npm install` | `pip install -r requirements.txt` |
| `package.json` | `requirements.txt` |
| `node_modules/` | `venv/` 或 `site-packages/` |
| `.vue` 文件 | `.py` 模組（但包含 HTML + JS + CSS） |
| Pinia Store | 全局變數管理器 |

---

## 🐍 FastAPI 後端整合

### 後端 API 架構建議

創建一個 FastAPI 專案（與前端分離）：

```
backend/
├── main.py              # FastAPI 入口
├── models/              # 資料模型
│   ├── user.py
│   └── message.py
├── routers/             # API 路由
│   ├── auth.py          # 登入/註冊
│   ├── chat.py          # 聊天功能
│   └── upload.py        # 檔案上傳
├── services/            # 業務邏輯
│   └── ai_service.py    # AI 處理邏輯
├── database.py          # 資料庫連線
└── requirements.txt     # Python 依賴
```

---

## 🔌 API 端點設計

### 1. 認證相關

#### **POST /api/auth/login**
```python
# backend/routers/auth.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

class LoginRequest(BaseModel):
    email: str
    password: str

@router.post("/auth/login")
async def login(request: LoginRequest):
    # 驗證邏輯
    if request.email == "test@example.com" and request.password == "password":
        return {
            "user": {
                "id": 1,
                "name": "Test User",
                "email": request.email
            },
            "token": "fake-jwt-token-12345"
        }
    raise HTTPException(status_code=401, detail="Invalid credentials")
```

#### **POST /api/auth/logout**
```python
@router.post("/auth/logout")
async def logout():
    return {"message": "Logged out successfully"}
```

### 2. 聊天相關

#### **POST /api/chat/send**
```python
# backend/routers/chat.py
from fastapi import APIRouter, File, UploadFile, Form
from typing import List, Optional
import json

router = APIRouter()

@router.post("/chat/send")
async def send_message(
    conversation_id: int = Form(...),
    message: str = Form(...),
    files: Optional[List[UploadFile]] = File(None)
):
    # 1. 儲存用戶訊息到資料庫
    
    # 2. 處理檔案上傳（如果有）
    file_urls = []
    if files:
        for file in files:
            # 儲存檔案到硬碟或雲端
            file_path = f"uploads/{file.filename}"
            with open(file_path, "wb") as f:
                content = await file.read()
                f.write(content)
            file_urls.append(f"/uploads/{file.filename}")
    
    # 3. 呼叫 AI 處理
    ai_response = await process_with_ai(message, file_urls)
    
    # 4. 返回 AI 回覆
    return {
        "user_message": {
            "id": 123,
            "role": "user",
            "content": message,
            "files": file_urls,
            "timestamp": "2024-01-01T12:00:00Z"
        },
        "ai_message": {
            "id": 124,
            "role": "assistant",
            "content": ai_response,
            "timestamp": "2024-01-01T12:00:05Z"
        }
    }

async def process_with_ai(message: str, files: List[str]) -> str:
    # 這裡整合您的 AI 模型
    # 例如：OpenAI API、本地模型等
    return f"AI 回覆：我收到了您的訊息「{message}」"
```

#### **GET /api/chat/conversations**
```python
@router.get("/chat/conversations")
async def get_conversations(user_id: int):
    # 從資料庫獲取用戶的所有對話
    return {
        "conversations": [
            {"id": 1, "title": "First Chat", "date": "Today"},
            {"id": 2, "title": "Project Discussion", "date": "Yesterday"}
        ]
    }
```

#### **GET /api/chat/messages/{conversation_id}**
```python
@router.get("/chat/messages/{conversation_id}")
async def get_messages(conversation_id: int):
    # 從資料庫獲取該對話的所有訊息
    return {
        "messages": [
            {
                "id": 1,
                "role": "assistant",
                "content": "Hello! How can I help?",
                "timestamp": "2024-01-01T10:00:00Z"
            }
        ]
    }
```

#### **DELETE /api/chat/conversations/{conversation_id}**
```python
@router.delete("/chat/conversations/{conversation_id}")
async def delete_conversation(conversation_id: int):
    # 從資料庫刪除對話
    return {"message": "Conversation deleted"}
```

#### **POST /api/chat/conversations**
```python
@router.post("/chat/conversations")
async def create_conversation(user_id: int = Form(...)):
    # 創建新對話
    return {
        "id": 999,
        "title": "New Chat",
        "date": "Today"
    }
```

### 3. FastAPI 主程式

```python
# backend/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from routers import auth, chat

app = FastAPI(title="SimpleChat API")

# 🔥 CORS 設定（重要！讓前端能呼叫 API）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # 前端開發伺服器
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 註冊路由
app.include_router(auth.router, prefix="/api", tags=["auth"])
app.include_router(chat.router, prefix="/api", tags=["chat"])

# 提供靜態檔案訪問（上傳的檔案）
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

@app.get("/")
async def root():
    return {"message": "SimpleChat API is running"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

**運行後端：**
```bash
cd backend
python main.py
```

**測試 API：**
訪問 `http://localhost:8000/docs`（FastAPI 自動生成的文檔界面）

---

## 🔄 前端修改步驟

### 步驟 1：配置 API 基礎 URL

編輯 `src/services/api.js`：

```javascript
import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api',  // 🔥 改成 FastAPI 地址
  headers: {
    'Content-Type': 'application/json'
  },
  timeout: 30000  // 30 秒超時
})

// 請求攔截器（自動加入 Token）
api.interceptors.request.use(
  config => {
    const token = localStorage.getItem('auth_token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  error => Promise.reject(error)
)

// 回應攔截器（處理錯誤）
api.interceptors.response.use(
  response => response,
  error => {
    if (error.response?.status === 401) {
      // Token 過期，跳轉到登入頁
      localStorage.removeItem('auth_token')
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

export default api
```

**環境變數設定（可選）：**

創建 `.env` 文件（在專案根目錄）：
```env
VITE_API_BASE_URL=http://localhost:8000/api
```

### 步驟 2：修改 Auth Store（認證邏輯）

編輯 `src/stores/auth.js`：

```javascript
import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '@/services/api'
import router from '@/router'

export const useAuthStore = defineStore('auth', () => {
  const user = ref(null)
  const token = ref(localStorage.getItem('auth_token') || null)
  const isLoading = ref(false)
  const error = ref(null)

  const isAuthenticated = () => !!token.value

  // 🔥 真實的登入邏輯
  const login = async (email, password) => {
    isLoading.value = true
    error.value = null
    
    try {
      const response = await api.post('/auth/login', { email, password })
      const data = response.data
      
      // 儲存用戶資訊和 Token
      user.value = data.user
      token.value = data.token
      localStorage.setItem('auth_token', data.token)
      localStorage.setItem('user', JSON.stringify(data.user))
      
      // 跳轉到聊天頁面
      router.push('/')
    } catch (err) {
      error.value = err.response?.data?.detail || 'Login failed'
      throw err
    } finally {
      isLoading.value = false
    }
  }

  // 🔥 登出
  const logout = async () => {
    try {
      await api.post('/auth/logout')
    } catch (err) {
      console.error('Logout error:', err)
    } finally {
      user.value = null
      token.value = null
      localStorage.removeItem('auth_token')
      localStorage.removeItem('user')
      router.push('/login')
    }
  }

  // 🔥 從 localStorage 恢復用戶狀態
  const restoreUser = () => {
    const savedUser = localStorage.getItem('user')
    if (savedUser) {
      user.value = JSON.parse(savedUser)
    }
  }

  return {
    user,
    token,
    isLoading,
    error,
    isAuthenticated,
    login,
    logout,
    restoreUser
  }
})
```

### 步驟 3：修改 Chat Store（聊天邏輯）

編輯 `src/stores/chat.js`：

```javascript
import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '@/services/api'

export const useChatStore = defineStore('chat', () => {
  const conversations = ref([])
  const currentMessages = ref([])
  const activeChatId = ref(null)
  const isTyping = ref(false)

  // 🔥 從後端載入對話列表
  const loadConversations = async () => {
    try {
      const response = await api.get('/chat/conversations')
      conversations.value = response.data.conversations
      
      // 如果有對話，自動選擇第一個
      if (conversations.value.length > 0 && !activeChatId.value) {
        await selectConversation(conversations.value[0].id)
      }
    } catch (error) {
      console.error('Failed to load conversations:', error)
    }
  }

  // 🔥 選擇對話並載入訊息
  const selectConversation = async (id) => {
    activeChatId.value = id
    conversations.value.forEach(c => c.active = (c.id === id))
    
    try {
      const response = await api.get(`/chat/messages/${id}`)
      currentMessages.value = response.data.messages
    } catch (error) {
      console.error('Failed to load messages:', error)
      currentMessages.value = []
    }
  }

  // 🔥 發送訊息（支援檔案）
  const sendMessage = async (text, files = []) => {
    if (!activeChatId.value) return

    isTyping.value = true

    try {
      // 建立 FormData（用於上傳檔案）
      const formData = new FormData()
      formData.append('conversation_id', activeChatId.value)
      formData.append('message', text)
      
      // 加入檔案
      files.forEach(file => {
        formData.append('files', file)
      })

      // 發送到後端
      const response = await api.post('/chat/send', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      })

      // 將用戶訊息和 AI 回覆加入列表
      currentMessages.value.push(response.data.user_message)
      currentMessages.value.push(response.data.ai_message)

    } catch (error) {
      console.error('Failed to send message:', error)
      alert('發送失敗，請重試')
    } finally {
      isTyping.value = false
    }
  }

  // 🔥 創建新對話
  const createNewChat = async () => {
    try {
      const response = await api.post('/chat/conversations')
      const newChat = response.data
      
      conversations.value.unshift(newChat)
      await selectConversation(newChat.id)
    } catch (error) {
      console.error('Failed to create chat:', error)
    }
  }

  // 🔥 刪除對話
  const deleteConversation = async (id) => {
    try {
      await api.delete(`/chat/conversations/${id}`)
      
      conversations.value = conversations.value.filter(c => c.id !== id)
      
      if (activeChatId.value === id) {
        if (conversations.value.length > 0) {
          await selectConversation(conversations.value[0].id)
        } else {
          await createNewChat()
        }
      }
    } catch (error) {
      console.error('Failed to delete conversation:', error)
    }
  }

  // 🔥 重新命名對話
  const renameConversation = async (id, newTitle) => {
    try {
      await api.patch(`/chat/conversations/${id}`, { title: newTitle })
      
      const chat = conversations.value.find(c => c.id === id)
      if (chat) {
        chat.title = newTitle
      }
    } catch (error) {
      console.error('Failed to rename conversation:', error)
    }
  }

  return {
    conversations,
    currentMessages,
    activeChatId,
    isTyping,
    loadConversations,
    selectConversation,
    sendMessage,
    createNewChat,
    deleteConversation,
    renameConversation
  }
})
```

### 步驟 4：在 App 啟動時初始化

編輯 `src/views/ChatView.vue`，在 `<script setup>` 中加入：

```javascript
import { onMounted } from 'vue'

// ... 其他代碼

onMounted(async () => {
  // 載入對話列表
  await chatStore.loadConversations()
  scrollToBottom()
})
```

---

## ❓ 常見問題

### 1. **CORS 錯誤：Access to XMLHttpRequest has been blocked**

**原因：** 瀏覽器安全機制，阻止前端跨域請求。

**解決：** 確保 FastAPI 有設定 CORS（見上方 `main.py` 範例）

### 2. **連不到後端 API**

**檢查清單：**
- [ ] FastAPI 是否在運行？（`http://localhost:8000/docs` 能打開）
- [ ] 前端 `api.js` 的 `baseURL` 是否正確？
- [ ] 網路防火牆是否阻擋？

### 3. **檔案上傳失敗**

**常見原因：**
- FastAPI 沒有創建 `uploads/` 資料夾
- 檔案大小超過限制

**解決：**
```python
# 在 main.py 加入
import os
os.makedirs("uploads", exist_ok=True)
```

### 4. **Token 驗證失效**

**FastAPI 端需要實作 JWT 驗證：**
```python
from fastapi import Depends, HTTPException, Header

async def verify_token(authorization: str = Header(...)):
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid token format")
    
    token = authorization.replace("Bearer ", "")
    # 驗證 JWT token（使用 python-jose 或 PyJWT）
    
    return token

# 在需要驗證的路由使用：
@router.get("/protected")
async def protected_route(token: str = Depends(verify_token)):
    return {"message": "Authenticated!"}
```

---

## 🎯 完整開發流程

### 第一次設置：

```bash
# 1. 安裝前端依賴
cd C:\Users\today\Dropbox\MainStorage\P2025_SIMPLECHAT
npm install

# 2. 創建 Python 虛擬環境（後端）
cd ../backend
python -m venv venv
.\venv\Scripts\activate  # Windows
pip install fastapi uvicorn python-multipart

# 3. 創建 uploads 資料夾
mkdir uploads
```

### 日常開發：

**終端機 1（前端）：**
```bash
cd C:\Users\today\Dropbox\MainStorage\P2025_SIMPLECHAT
npm run dev
```

**終端機 2（後端）：**
```bash
cd ../backend
.\venv\Scripts\activate
python main.py
```

**測試：**
1. 打開瀏覽器：`http://localhost:5173/`
2. 登入測試帳號：`test@example.com` / `password`
3. 發送訊息，檢查是否能與後端通訊

---

## 📚 進階學習資源

### Vue.js 相關：
- [Vue 3 官方文檔](https://vuejs.org/)（中文版：[https://cn.vuejs.org/](https://cn.vuejs.org/)）
- [Pinia 文檔](https://pinia.vuejs.org/)
- [Vue Router 文檔](https://router.vuejs.org/)

### FastAPI 相關：
- [FastAPI 官方文檔](https://fastapi.tiangolo.com/)
- [CORS 設定說明](https://fastapi.tiangolo.com/tutorial/cors/)
- [檔案上傳教學](https://fastapi.tiangolo.com/tutorial/request-files/)

---

## 💡 建議的開發順序

1. ✅ **先跑起來**：前端 + 後端都能啟動
2. ✅ **測試登入**：確保 Auth API 能通
3. ✅ **測試發送訊息**：不帶檔案，純文字
4. ✅ **加入 AI 邏輯**：整合 OpenAI 或本地模型
5. ✅ **測試檔案上傳**：一個檔案
6. ✅ **完善功能**：多檔案、歷史紀錄
7. ✅ **資料庫整合**：用 SQLite 或 PostgreSQL

---

**祝開發順利！有任何問題隨時問我。** 🚀
