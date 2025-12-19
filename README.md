# SimpleChat – 後端友善的對話機器人範本

這個專案提供一套可直接使用的聊天 UI，但重點是讓只會後端與 Python 的人，也能快速做出可用的對話服務。你只需要改一個 Python 函式，就能把回覆串到你自己的 LLM 或任何內部服務。

## ⚡ 快速開始（後端為主）
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
   - `http://localhost:8000/docs` 可直接用 Swagger 測 API。
   - 首次啟動會建立 SQLite DB 與 `chat_uploads/` 目錄。

## 🔌 你要改的 Python 位置（最重要）
後端已經把「收到使用者訊息 → 產生助手回覆」的流程串好，你只要把 **LLM 回覆**接上就行。

請修改 `backend/main.py` 的 `build_simulated_reply()`：

```python
def build_simulated_reply(content: str, files: list[MessageFileResponse]) -> str:
    # 這裡改成你自己的模型/服務呼叫，最後回傳字串即可
    # files 會包含附件資訊，file.file_path 是相對於 UPLOAD_ROOT 的路徑
    reply_text = your_llm_call(content, files)
    return reply_text
```

目前系統在 `run_assistant_reply()` 內呼叫 `build_simulated_reply()`，並把結果寫回資料庫。  
如果你想做更進階的處理（例如串流、分段寫入），直接改 `run_assistant_reply()` 即可。

**流程小抄**
- `POST /api/messages`：收到使用者訊息，建立一筆 `assistant` 的 pending 訊息。
- `run_assistant_reply()`：產生回覆，更新 `message` 表內容與狀態。
- `POST /api/messages/{id}/stop`：可中止尚未完成的回覆。

更詳細的 API/DB 結構請看 `DEVELOPMENT.md` 與 `DB_SCHEMA.md`。

## 🖥️ 前端（可選）
若你想直接用現成 UI：
```bash
npm install
npm run dev
```
設定前端連線的 `.env`：
```
VITE_API_BASE_URL=http://localhost:8000/api
VITE_UPLOAD_BASE_URL=http://localhost:8000/chat_uploads
```
打開 `http://localhost:5173/` 即可使用。

## 📂 後端目錄速覽
```
backend/
├── main.py               # FastAPI 主檔，LLM 串接點在 build_simulated_reply()
├── database.py           # SQLite 初始化與連線
├── chat_uploads/         # 使用者附件
└── tests/                # pytest 測試
```

## 🔧 延伸建議（略）
- 串流回覆：改用 SSE / WebSocket。
- 上雲儲存：把附件改存 S3/GCS。
- CI/CD：加入 pytest 與 build 驗證。

如需完整後端細節、API 行為、測試指令，請參考 `DEVELOPMENT.md`。
