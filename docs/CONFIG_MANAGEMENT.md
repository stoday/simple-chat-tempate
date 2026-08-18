# 統一配置管理

## 概述

為了避免在多個檔案中重複設定 URL、port 等資訊，本專案使用 `config.toml` 作為**唯一的配置來源**。

所有 URL 和 port 設定都集中在 `config.toml` 的 `[server]` 區塊中。

## 配置檔案說明

### `config.toml` - 主要配置檔（唯一來源）

```toml
[server.local]
frontend_port = 5173        # Vite 前端開發伺服器 port
backend_port = 8000         # FastAPI 後端伺服器 port
frontend_url = "http://localhost:5173"
backend_url = "http://localhost:8000"

[server.production]
frontend_domain = "heranchat.demo-today.org"
backend_domain = "api.demo-today.org"
frontend_url = "https://heranchat.demo-today.org"
backend_url = "https://api.demo-today.org"

cloudflare_tunnel_name = "heran-tunnel"
```

### 同源 API 路由

前端不從 `.env` 讀取 API URL，也不直接讀取 `config.toml`。瀏覽器固定使用
`/api/*` 與 `/chat_uploads/*`：

- 本機開發由 `vite.config.js` 代理到 `localhost:8000`。
- Docker 部署由 `nginx.conf` 代理到 `backend:8000`。
- `.env` 只保存後端機密資料與執行環境設定。

`scripts/sync_config.py` 只會依 `config.toml` 更新
`~/.cloudflared/config.yml`，不會再產生或修改 `.env`。

## 使用方式

### 修改 URL 或 Port

1. 編輯 `config.toml` 中的 `[server]` 區塊
2. 執行同步腳本：

```powershell
python scripts/sync_config.py
```

3. 根據提示重新啟動相關服務。實際監聽埠仍由 Uvicorn 啟動命令與
   `vite.config.js` 決定，修改時必須保持一致。

### 範例：修改本地開發 port

假設你想把前端改到 port 3000，後端改到 port 8080：

1. 編輯 `config.toml`:
```toml
[server.local]
frontend_url = "http://localhost:3000"
backend_url = "http://localhost:8080"
```

2. 同步修改 Uvicorn 啟動命令與 `vite.config.js` 的 proxy target。

3. 如使用 Cloudflare Tunnel，執行同步：
```powershell
python scripts/sync_config.py
```

4. 重新啟動服務：
```powershell
# 重啟後端
python -m backend.main

# 重啟前端（在另一個終端）
npm run dev

# 重啟 cloudflared（如果使用）
cloudflared tunnel run heran-tunnel
```

### 範例：修改生產域名

1. 編輯 `config.toml`:
```toml
[server.production]
frontend_domain = "chat.example.com"
backend_domain = "api.example.com"
frontend_url = "https://chat.example.com"
backend_url = "https://api.example.com"
```

2. 執行同步腳本並重啟後端與 Cloudflare Tunnel。後端會直接從
   `[server.local]` 和 `[server.production]` 的 `frontend_url` 建立 CORS 白名單。

## 檔案關聯圖

```
config.toml (唯一來源)
    ├─> ~/.cloudflared/config.yml (sync_config.py 生成)
    │   └─> Cloudflare Tunnel 使用
    └─> backend/main.py 直接讀取
        └─> CORS 設定使用

前端
    ├─> /api/* (同源相對路徑)
    └─> /chat_uploads/* (同源相對路徑)
         ├─> Vite proxy (本機)
         └─> Nginx proxy (Docker)
```

## 注意事項

1. **永遠只修改 `config.toml`**，不要直接編輯 `.env` 或 `cloudflared/config.yml` 的 URL 設定
2. API keys 等機密資訊仍可直接在 `.env` 中編輯，這些不會被覆蓋
3. 修改配置後記得重啟相關服務才會生效
4. 建議將 `config.toml` 納入版本控制，但 `.env` 應加入 `.gitignore`

## 疑難排解

### Q: 執行 `sync_config.py` 後前端還是連不到後端？
A: 確認是否重新啟動了前端開發伺服器 (`npm run dev`)

### Q: Cloudflare Tunnel 連不到本地服務？
A: 確認是否重新啟動了 cloudflared (`cloudflared tunnel run`)

### Q: 我的 API keys 不見了？
A: `sync_config.py` 會保留所有非 URL 的環境變數，不會刪除 API keys
