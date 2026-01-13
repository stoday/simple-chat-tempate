# Agent Cache 與 Multiprocessing 說明

## 🔍 當前問題分析

根據日誌分析，系統使用 `multiprocessing.Process` 來處理每個訊息請求，導致：

### 日誌觀察  
```
第1次對話: Worker PID: 11840 → [MAIN] Pre-loading agent...
第2次對話: Worker PID: 15908 → [MAIN] Pre-loading agent...  
第3次對話: Worker PID: 16188 → [MAIN] Pre-loading agent...
```

**每次都是不同的 Process ID**，這意味著：
1. 每個請求創建一個新的子進程
2. 新進程中所有 Python 模組都會被重新 import
3. 因此看到重複的模組初始化日誌

### Agent Cache 實際狀態

✅ **好消息**：在同一個 worker 進程內，agent cache **確實有效**！
- 日誌中顯示 `[AGENT CACHE] Using cached agent (stream=True)`
- 表示如果請求被分配到同一個進程，會使用緩存

❌ **問題**：每次都創建新進程，所以緩存無法跨請求重用

## 💡 解決方案選項

### 選項 1：使用進程池（Process Pool）⭐ 推薦

**優點**：
- 重用固定數量的 worker 進程
- Agent 只在每個 worker 中載入一次
- 進程隔離保證安全性

**實現方式**：
```python
# 在 startup 時創建進程池
_worker_pool = multiprocessing.Pool(processes=4)

# 使用 apply_async 而非 Process()
result = _worker_pool.apply_async(_run_reply_worker, args=(...))
```

**狀態**：已在代碼中實現基礎結構，但需要重構 `_run_reply_worker` 的串流處理邏輯

### 選項 2：使用 AsyncIO + ThreadPoolExecutor

**優點**：
- 線程共享同一進程內存，agent cache 完全共享
- 更輕量級，資源消耗更少
- 與 FastAPI 的異步模型更契合

**缺點**：
- Python GIL 可能影響 CPU 密集型任務性能
- 無進程隔離（但對 LLM API 調用影響不大）

**實現方式**：
```python
import asyncio
from concurrent.futures import ThreadPoolExecutor

executor = ThreadPoolExecutor(max_workers=4)

# 在處理訊息時
future = executor.submit(_run_reply_worker_sync, *args)
```

**狀態**：✅ **已實作並啟用 (2026-01-13)**。這是目前生產環境的運行模式。

### 🛡️ 關於多用戶併發安全性

使用者可能會擔心：「使用全域 Agent 在多人同時操作時會不會有問題？」

**潛在風險**：
- 雖然 LLM API 請求是 I/O bound（適合多執行緒），但如果 `akasha` 的 Agent 物件內部持有暫態（例如當前的對話上下文串流緩衝區），那麼多個線程共用同一個 Agent 物件就會導致 **Race Condition**（例如 A 的回應跑到 B 的畫面上）。

**解決方案：Thread Local Storage**：
- 我們在 `backend/tools.py` 中使用了 `threading.local` 來管理緩存。
- **機制**：系統會為每一個 Worker Thread 創建並緩存一個 **獨立的** Agent 副本。
- **安全性**：這保證了線程 A 絕對不會訪問到線程 B 的 Agent，實現了 100% 的執行緒安全。
- **資源消耗**：如果 Thread Pool Size = 10，則系統最多只會同時持有 10 個 Agent 物件，這對記憶體來說是非常高效且可控的。

### 選項 3：直接在主進程中處理（最簡單）

**優點**：
- Agent cache 完全有效
- 代碼最簡單
- 串流處理更直接

**缺點**：
- 無進程/線程隔離
- 阻塞型操作會影響其他請求（但 FastAPI 的異步機制可緩解）

**實現方式**：
直接在 API endpoint 中調用 `build_reply()` 而不使用 multiprocessing

### 選項 4：接受現狀（不推薦但可考慮）

**現狀分析**：
- 每個新進程會重新載入 agent（約 1.5-2 秒開銷）
- 但模組級預載入已經優化了首次載入時間
- 對於低頻使用場景可能足夠

## 📊 性能影響估算

| 方案 | Agent 載入頻率 | 記憶體使用 | 並發性能 | 實現複雜度 |
|------|-------------|-----------|---------|-----------|
| **進程池** | 每個 worker 一次 | 中等（N×Agent） | 高 | 中 |
| **線程池** | 全局一次 | 低（1×Agent） | 中（GIL限制） | 低 |
| **主進程** | 全局一次 | 最低 | 高（FastAPI異步） | 最低 |
| **現狀** | 每次請求 | 高（頻繁創建） | 中 | 無需更動 |

## 🎯 建議

### 短期方案（立即可用）

**改用線程池**，因為：
1. LLM API 調用是 I/O 密集型，不受 GIL 影響
2. 實現簡單，風險低
3. Agent cache 完全共享，性能最優

### 長期方案（生產環境）

**實現進程池 + 異步處理**：
1. 保持進程隔離的安全性
2. 重用 worker 進程以保持 agent cache
3. 配合 Redis/RabbitMQ 實現真正的任務隊列

## 🔧 下一步行動

1. **評估需求**：
   - 是否需要進程隔離？（多用戶環境通常不需要）
   - 並發量預期多高？（決定 pool size）
   - 是否有 CPU 密集型操作？（影響線程 vs 進程選擇）

2. **實施測試**：
   - 小規模測試線程池方案
   - 監控記憶體和響應時間
   - 驗證 agent cache 共享效果

3. **監控指標**：
   - Process/Thread ID 變化
   - Agent 載入日誌頻率
   - 平均響應時間
   - 記憶體使用量

---

**相關檔案**：
- `backend/main.py` - 第 1220-1240 行（Process creation）
- `backend/tools.py` - Agent cache 實現
- `docs/DEVELOPMENT.md` - Agent 緩存機制說明
