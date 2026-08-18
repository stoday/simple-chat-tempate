# 域名配置說明

## 快速修改部署域名

前端不再偵測或組合 API 網域。瀏覽器永遠請求同一來源的 `/api/*` 與
`/chat_uploads/*`，因此公開前端的 Web server 或 Tunnel 必須把這兩個路徑
轉送至 FastAPI。

Docker 已由 `nginx.conf` 提供代理，不需要額外前端設定。其他部署方式可採用：

```nginx
location /api/ {
    proxy_pass http://backend:8000/api/;
}

location /chat_uploads/ {
    proxy_pass http://backend:8000/chat_uploads/;
}
```

`config.toml` 的 `[server.production]` 保留公開域名與 Cloudflare Tunnel 設定；
修改後執行：

```powershell
python scripts/sync_config.py
```

這支腳本只更新 `~/.cloudflared/config.yml`，不會修改 `.env`。更新設定後請
重新啟動後端、反向代理與 Cloudflare Tunnel。

## 注意事項

1. **同源代理**：公開前端的服務必須代理 `/api` 與 `/chat_uploads`。
2. **後端**：修改 `config.toml` 後必須重新啟動，才能重新載入 CORS 等設定。
3. **HTTPS**：生產環境建議使用 HTTPS，並由 Cloudflare 或反向代理處理 TLS。
4. **靜態託管**：若平台無法提供 reverse proxy，必須另外設置 gateway；前端不再支援以環境變數指定跨網域 API。

## 檔案位置總覽

| 檔案 | 用途 | 需要重啟 |
|------|------|---------|
| `config.toml` | 後端、公開域名與 Tunnel 設定 | ✅ 後端／Tunnel |
| `vite.config.js` | 本機 `/api`、`/chat_uploads` 代理 | ✅ 前端 |
| `nginx.conf` | Docker 同源反向代理 | ✅ Nginx 容器 |

---

## 版本號管理

### 統一版本號來源

所有版本號都從 `config.toml` 的 `[app]` 區塊統一管理：

```toml
[app]
version = "1.0.1"  # 修改這裡就好！
```

### 自動同步版本號

修改 `config.toml` 的版本號後，執行同步腳本：

```bash
python scripts/sync_version.py
```

這會自動更新：
- `package.json` - 前端專案版本
- `src/stores/appConfig.js` - 前端預設配置

### 手動查看版本號

**前端：**
```javascript
// 在瀏覽器 Console
console.log(config.app.version)
```

**後端：**
```bash
# 查看 config.toml
grep version config.toml
```

### 發布新版本檢查清單

1. ✅ 更新 `config.toml` 的 version
2. ✅ 執行 `python scripts/sync_version.py`
3. ✅ 檢查版本號是否同步成功
4. ✅ 提交代碼並打 tag
5. ✅ 重啟服務

**Git 標籤範例：**
```bash
# 從 config.toml 讀取版本號
VERSION=$(grep -oP 'version = "\K[^"]+' config.toml | head -1)

# 創建 tag
git tag -a "v${VERSION}" -m "Release version ${VERSION}"
git push origin "v${VERSION}"
```
