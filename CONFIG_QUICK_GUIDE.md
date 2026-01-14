# 統一配置管理快速指南

## 快速開始

所有 URL 和 port 設定都在 **`config.toml`** 的 `[server]` 區塊中：

```toml
[server.local]
frontend_port = 5173
backend_port = 8000
frontend_url = "http://localhost:5173"
backend_url = "http://localhost:8000"

[server.production]
frontend_domain = "heranchat.demo-today.org"
backend_domain = "api.demo-today.org"
```

## 修改配置步驟

### 1. 編輯 `config.toml`

修改 `[server]` 區塊中的設定

### 2. 執行同步腳本

```powershell
python scripts/sync_config.py
```

這會自動更新：
- `.env` - 前端環境變數
- `~/.cloudflared/config.yml` - Cloudflare Tunnel 配置

### 3. 重啟服務

根據腳本提示重啟相關服務

## 常見場景

### 更改本地開發 port

1. 編輯 `config.toml`:
```toml
[server.local]
frontend_port = 3000  # 改為 3000
backend_port = 9000   # 改為 9000
```

2. 執行: `python scripts/sync_config.py`

3. 重啟前後端和 cloudflared

### 更改生產域名

1. 編輯 `config.toml`:
```toml
[server.production]
frontend_domain = "你的域名.com"
backend_domain = "api.你的域名.com"
```

2. 同時更新 CORS 設定:
```toml
[deployment]
frontend_domains = [
    "https://你的域名.com",
    "http://localhost:5173"
]
```

3. 執行: `python scripts/sync_config.py`

## 注意事項

✅ **建議做法**:
- 永遠只修改 `config.toml`
- 修改後執行 `sync_config.py`
- API keys 等機密資訊可直接在 `.env` 修改（不會被覆蓋）

❌ **不建議做法**:
- 直接修改 `.env` 的 URL 設定
- 直接修改 `cloudflared/config.yml`

## 詳細文檔

完整說明請參考: [docs/CONFIG_MANAGEMENT.md](docs/CONFIG_MANAGEMENT.md)
