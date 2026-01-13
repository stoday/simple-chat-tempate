# HeranChat 系統搬遷與環境部署指南

本指南旨在協助您將 HeranChat 系統從目前的展示環境（Cloudflare Tunnel）搬遷至新的伺服器或內部網路（Intranet）環境。

---

## 1. 核心檔案遷移清單

在遷移至新主機時，請確保以下目錄與檔案完整複製：

*   **`backend/simplechat.db`**: 所有的對話紀錄、使用者帳號、系統設定與 LLM 配置都儲存在此 SQLite 資料庫。
*   **`backend/chat_uploads/`**: 使用者上傳的所有實體檔案與圖片存儲位置。
*   **`.env`**: 包含 Gemini API Key 與其他敏感環境變數。
*   **`config.toml`**: 系統標題、上傳格式權限及 UI 主題設定。

---

## 2. 網路與網域配置

系統已內建「動態環境偵測」，大部分情況下換環境後前端會自動適應，但仍需注意以下手動調整項：

### A. 後端 CORS 權限 (`backend/main.py`)
當您的人員透過新的 IP 或網域訪問網頁時，必須在後端放行該來源，否則會出現 **Network Error**。
*   **修改位置**：`app.add_middleware(CORSMiddleware, ...)`
*   **動作**：將新的網址（含 Port）加入 `allow_origins` 清單。
    ```python
    allow_origins=[
        "https://app.demo-today.org",
        "https://heranchat.demo-today.org",
        "http://localhost:5173",
        "http://192.168.1.100:5173", # 範例：新增您的內網 IP
    ]
    ```

### B. 前端 API 鎖定 (`index.html`)
目前系統會自動判斷：
1.  若是 `app.demo-today.org` 或 `hearnchat.demo-today.org` -> 連向雲端 API。
2.  若是 `localhost` -> 連向本地 8000。
3.  **其他情況（內網）** -> 自動連向瀏覽器網址的 8000 埠。
*   **注意**：若您未來在內網使用了非 `8000` 的後端埠，請修改 `index.html` 中的偵測腳本。

---

## 3. 開發伺服器與防火牆設定

### 外部存取設定 (`vite.config.js`)
如果您在新環境使用 `npm run dev` 啟動前端：
*   目前已設定 `host: true`，允許透過 IP 存取。
*   目前已設定 `allowedHosts: true`，跳過網域檢查。

### 防火牆開放連接埠
請確保伺服器防火牆已開啟以下 Port 的輸入（Inbound）許可：
*   **5173**: 前端 Web 介面。
*   **8000**: 後端 RESTful API。

---

## 4. 內部網路環境的注意事項

### A. HTTPS 的必要性
*   **功能限制**：若在內網僅使用 `http://` (沒有 SSL)，瀏覽器安全性原則會停用 `navigator.clipboard` 功能。這將導致訊息框右上角的「複製程式碼」按鈕失效。
*   **建議**：若為正式環境，建議配置自簽憑證走 HTTPS，或部署在已套用 SSL 的反向代理伺服器（如 Nginx）後方。

### B. 反向代理部署 (強烈建議)
若環境許可，建議使用 Nginx 統一管理流量：
*   將 `http://your-ip` 導向前端 (5173)。
*   將 `http://your-ip/api` 導向後端 (8000)。
*   **優點**：可解決所有 CORS 問題，且不需在前端腳本中偵測 Port。

---

## 5. 故障排除

*   **Network Error**: 90% 是因為後端 `allow_origins` 沒填入正確的訪問來源網址。
*   **401 Unauthorized**: 請檢查伺服器時間是否與標準時間落差過大（影響 JWT 驗證）。
*   **空白頁面**: 請檢查瀏覽器控制台 (F12) 是否有 JS 載入錯誤，通常是 API 地址抓取失敗。

---
*文件更新日期：2026-01-13*
