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

### 自動生成的檔案

以下檔案會由 `scripts/sync_config.py` 自動生成，**請勿手動編輯 URL 相關設定**：

1. **`.env`** - 前端環境變數
   - `VITE_API_BASE_URL`
   - `VITE_UPLOAD_BASE_URL`
   - （其他 API keys 等會保留）

2. **`~/.cloudflared/config.yml`** - Cloudflare Tunnel 配置
   - 服務映射設定

## 使用方式

### 修改 URL 或 Port

1. 編輯 `config.toml` 中的 `[server]` 區塊
2. 執行同步腳本：

```powershell
python scripts/sync_config.py
```

3. 根據提示重新啟動相關服務

### 範例：修改本地開發 port

假設你想把前端改到 port 3000，後端改到 port 8080：

1. 編輯 `config.toml`:
```toml
[server.local]
frontend_port = 3000
backend_port = 8080
frontend_url = "http://localhost:3000"
backend_url = "http://localhost:8080"
```

2. 執行同步：
```powershell
python scripts/sync_config.py
```

3. 重新啟動服務：
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

2. 同時更新 `[deployment]` 區塊的 CORS 設定：
```toml
[deployment]
frontend_domains = [
    "https://chat.example.com",
    "http://localhost:5173"
]
default_api_domain = "api.example.com"
```

3. 執行同步腳本並重啟服務

## 檔案關聯圖

```
config.toml (唯一來源)
    ├─> .env (自動生成)
    │   └─> 前端 Vite 使用
    ├─> ~/.cloudflared/config.yml (自動生成)
    │   └─> Cloudflare Tunnel 使用
    └─> backend/main.py 直接讀取
        └─> CORS 設定使用
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
