# SimpleChat – ChatGPT 風格前端樣板

SimpleChat 是一個以 Vue 3 + Vite 打造的聊天介面範本，模仿 ChatGPT 的互動體驗。只要接上你自己的後端／AI 推理服務，就能快速做出客服助理、知識庫問答或任何對話式應用。

## ✨ 特色功能
- 🧱 **現代化 UI**：雙欄佈局、可以摺疊的對話列表、訊息氣泡、打字中指示。
- ⌨️ **友善輸入體驗**：多行自動伸縮輸入框、Shift+Enter 換行、Ctrl/⌘+Enter 快捷鍵易於擴充。
- 📎 **檔案附件流程**：支援多檔案挑選、拖放、上傳進度條，並可整合自訂後端。
- 📦 **Pinia 狀態管理**：聊天歷史、使用者資訊、打字狀態等集中管理，方便擴寫。
- 🧩 **模組化結構**：ChatInput、ChatMessage、SidebarItem…可重複組合、替換樣式。

## 🛠 使用技術
- [Vue 3](https://vuejs.org/)（`<script setup>`）
- [Vite](https://vitejs.dev/)
- [Pinia](https://pinia.vuejs.org/)（狀態管理）
- [Vue Router](https://router.vuejs.org/)（路由）
- [Axios](https://axios-http.com/)（API 呼叫）
- [Phosphor Icons](https://phosphoricons.com/)

## ⚡ 快速開始
1. **安裝依賴**
   ```bash
   npm install
   ```
2. **設定環境變數**（可選，預設會連到 `http://localhost:3000/api`）
   ```bash
   cp .env.example .env   # 若不存在可自行建立
   echo "VITE_API_BASE_URL=http://localhost:8000/api" >> .env
   ```
3. **啟動開發伺服器**
   ```bash
   npm run dev
   ```
4. 開啟瀏覽器造訪 `http://localhost:5173/`。

### 常用指令
| 指令 | 說明 |
|------|------|
| `npm run dev` | 啟動 Vite 開發伺服器 |
| `npm run build` | 建立 production 版靜態檔案到 `dist/` |
| `npm run preview` | 在本機預覽編譯後的結果 |

## 🔧 環境變數
| 變數 | 預設值 | 說明 |
|------|--------|------|
| `VITE_API_BASE_URL` | `http://localhost:3000/api` | 前端呼叫的後端 API Root。請改為你的 FastAPI/其他服務網址。 |

> 建議為不同環境建立 `.env.development`、`.env.production`，或在 CI/CD 注入變數。

## 📂 目錄結構
```
src/
├── assets/css/          # reset / variables / base 樣式
├── components/
│   ├── chat/            # ChatInput, ChatMessage 等聊天元件
│   └── layout/          # SidebarItem 等佈局元件
├── services/api.js      # Axios 設定與附件上傳流程
├── stores/              # auth.js、chat.js（Pinia store）
├── views/               # ChatView、LoginView
├── router/              # 前端路由設定
└── main.js              # Vue 進入點、全域樣式載入
```

## 🔌 接上你的後端
- `src/services/api.js` 會讀取 `VITE_API_BASE_URL`，預期後端提供 `/chat/...`、`/upload` 等 API。
- `uploadFiles()` 以多檔案並行上傳並提供進度 callback，可改寫成串流/分段上傳。
- `src/stores/chat.js` 包含 `sendMessage`, `createNewChat`, `deleteConversation`…您可以直接改呼叫 FastAPI、Django、Node.js 等後端。
- 詳細 FastAPI 範例與 API 設計，請參考 [`DEVELOPMENT.md`](DEVELOPMENT.md)。

## 🚀 常見延伸方向
1. **支援 Markdown / 程式碼框**：在 `ChatMessage.vue` 使用 `markdown-it` + `highlight.js`。
2. **多模型設定**：在 `chat` store 增加 per-conversation 的 model、溫度等欄位。
3. **離線儲存**：使用 IndexedDB/localStorage 快取對話歷史。
4. **串流回覆**：整合 SSE / WebSocket 顯示 token-by-token 輸出。
5. **RWD 最佳化**：調整 ChatView 於手機上切換列表與對話畫面。

歡迎 Fork 或直接修改此範本，打造屬於自己的 AI 助理！若你希望我協助擴充其他功能，也可以開需求討論。 🎯
