# 域名配置說明

## 快速修改部署域名

所有域名配置都集中在 `config.toml` 的 `[deployment]` 區塊中：

```toml
[deployment]
# 部署域名設定 (用於 CORS 與前端自動偵測)
# 修改這些設定後需要重啟後端服務
frontend_domains = [
    "https://your-new-domain.com",  # 修改這裡！
    "http://localhost:5173"
]
# API 域名 (前端會根據 frontend_domain 自動對應)
api_domain_mapping = { "your-prefix" = "api" }
# 預設 API 域名
default_api_domain = "api.your-domain.com"  # 修改這裡！
```

## 修改步驟

### 1. 更新 config.toml

編輯 `config.toml` 中的 `[deployment]` 區塊：

```toml
frontend_domains = [
    "https://heranchat.demo-today.org",  # 您的新前端域名
    "http://localhost:5173"               # 保留本地開發
]
default_api_domain = "api.demo-today.org"  # 您的 API 域名
```

### 2. 更新前端自動偵測 (index.html)

編輯 `index.html` 中的域名偵測邏輯（第 18-20 行）：

```javascript
if (hostname.startsWith('hearnchat.')) {  // 改成您的前綴
    window.__API_BASE__ = protocol + '//api.demo-today.org';
}
```

### 3. 重啟服務

```bash
# 重啟後端 (會讀取新的 config.toml)
# 如果使用 uvicorn:
uvicorn backend.main:app --reload

# 前端會自動熱更新，或硬刷新瀏覽器 (Ctrl+Shift+R)
```

## 範例配置

### 範例 1: 從 app.demo-today.org 改為 hearnchat.demo-today.org

**config.toml:**
```toml
frontend_domains = [
    "https://heranchat.demo-today.org",
    "http://localhost:5173"
]
```

**index.html (第 18-20 行):**
```javascript
if (hostname.startsWith('app.') || hostname.startsWith('hearnchat.')) {
    window.__API_BASE__ = protocol + '//api.demo-today.org';
}
```

### 範例 2: 完全更換為新域名 (example.com)

**config.toml:**
```toml
frontend_domains = [
    "https://chat.example.com",
    "http://localhost:5173"
]
default_api_domain = "api.example.com"
```

**index.html:**
```javascript
if (hostname.includes('example.com')) {
    if (hostname.startsWith('chat.')) {
        window.__API_BASE__ = protocol + '//api.example.com';
    }
}
```

## 注意事項

1. **後端**：修改 `config.toml` 後**必須重啟**後端服務
2. **前端**：修改 `index.html` 後需要重新 build 或硬刷新瀏覽器
3. **HTTPS**：生產環境建議使用 HTTPS，確保 Cloudflare 或反向代理已正確配置 SSL
4. **內網部署**：如果是內網 IP 訪問，系統會自動偵測並使用 `http://IP:8000` 作為 API 地址

## 檔案位置總覽

| 檔案 | 用途 | 需要重啟 |
|------|------|---------|
| `config.toml` | 後端 CORS 域名清單 | ✅ 是 (後端) |
| `index.html` | 前端域名自動偵測邏輯 | ⚠️ 需刷新瀏覽器 |
| `docs/MIGRATION_GUIDE.md` | 文件參考 | ❌ 否 |

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
