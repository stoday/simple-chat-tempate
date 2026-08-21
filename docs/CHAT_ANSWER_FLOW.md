# 前端輸入到答案生成流程

本文說明使用者在前端輸入問題後，系統如何建立訊息、執行 Agent／LLM、透過 SSE 傳送事件，最後在畫面上逐段顯示答案。

## 整體流程

```text
ChatInput
  ↓ emit('send')
ChatView
  ↓ chatStore.sendMessage()
POST /api/messages
  ↓
建立 user message
建立 pending assistant message
  ↓
背景 Thread 執行模型
  ↓
Akasha Agent + 工具／RAG
  ↓
Queue 傳回事件
  ↓
寫入 message_event／更新 assistant content
  ↓
SSE /api/messages/{id}/stream
  ↓
瀏覽器解析事件
  ↓
Pinia 更新畫面
  ↓
完成答案
```

## 1. 前端取得輸入

使用者在 `src/components/chat/ChatInput.vue` 按下 Enter 或送出按鈕後：

- 檢查是否有文字或附件。
- 暫時鎖住送出按鈕，避免重複送出。
- 將 `{ text, files }` emit 給 `ChatView`。

`src/views/ChatView.vue` 接到事件後，呼叫 `chatStore.sendMessage()`。

## 2. 前端組成 multipart request

`src/stores/chat.js` 的 `sendMessage()` 會：

- 取得目前對話的 `conversation_id`。
- 檢查登入 token 是否過期。
- 建立 `FormData`，包含：
  - `conversation_id`
  - `content`
  - `files`
- 呼叫：

```http
POST /api/messages
Content-Type: multipart/form-data
```

## 3. 後端保存使用者訊息

`backend/main.py` 的 `/api/messages` endpoint 會：

1. 驗證登入者與對話權限。
2. 將使用者訊息寫入 `message` 資料表。
3. 將附件保存到 upload directory，並寫入 `message_file`。
4. 建立一筆空白的 assistant message：

```text
status = pending
parent_message_id = user_message_id
content = ""
```

5. 啟動背景回答任務。
6. 立即回傳 user message 與 pending assistant message。

因此，`POST /api/messages` 不會等待模型完整生成答案。

## 4. 前端建立 SSE 連線

收到 pending assistant message 後，`chat.js` 會呼叫 `connectToStream()`，連線到：

```http
GET /api/messages/{assistant_message_id}/stream
Accept: text/event-stream
```

前端會持續讀取 `ReadableStream`，並依照事件序號處理：

- 重複事件
- 遺失事件
- 連線中斷
- 重新連線

## 5. 背景工作執行模型

`backend/main.py` 的 `run_assistant_reply()` 會把回答工作交給 thread pool：

```text
async task
  ↓
ThreadPool worker
  ↓
_run_reply_worker()
  ↓
build_reply()
```

worker 會先取得：

- 最近的對話歷史。
- 目前對話中的已上傳檔案。
- 使用者名稱與角色。
- 使用者上傳目錄。
- 對話標題資訊。

若對話標題仍是 `New Chat`，系統也會使用第一則問題產生新的對話標題。標題生成與左側欄更新流程如下。

## 6. 根據第一則訊息生成左側欄標題

新對話建立時，標題預設為 `New Chat`。背景 worker 會先檢查目前對話標題，只有在仍為 `New Chat` 時，才會使用第一則使用者訊息呼叫 `_generate_conversation_title()`。

完整流程如下：

```text
第一則使用者訊息
  ↓
_generate_conversation_title(content)
  ↓
更新 conversation.title
  ↓
送出 conversation_title event
  ↓
SSE 傳到前端
  ↓
chat.js 的 updateConversationTitle()
  ↓
更新 Pinia conversations
  ↓
ChatView.vue 重新渲染 SidebarItem
  ↓
左側欄顯示新標題
```

後端會對生成結果做基本清理，例如移除引號，並限制標題長度最多 50 個字元。成功產生標題後，後端會：

1. 更新 `conversation.title` 與 `updated_at`。
2. 將新的標題寫入 `conversation_title` event。
3. 透過後續的 SSE stream 傳給前端。

前端收到 `conversation_title` event 後，`src/stores/chat.js` 的 `updateConversationTitle()` 會：

- 找到對應的 conversation。
- 更新 Pinia 中的 `conversation.title`。
- 將更新後的對話清單保存到 local storage cache。

`src/views/ChatView.vue` 使用 `conversations` 渲染左側欄，並將每個對話的 `item.title` 傳給 `SidebarItem`，因此 Pinia 更新後，左側欄會立即顯示新的標題。

如果 SSE 連線在標題事件送出前中斷，前端重新載入訊息或對話資料時，後端也會從資料庫的 `conversation.title` 回傳目前標題，作為補償機制。

## 後端 Prompt 管理與除錯索引

後端不是只有一個 prompt。一次聊天回答可能同時經過「Agent system prompt」、「聊天主 prompt」，以及 Agent 選中的工具所使用的子 prompt。除錯時應先確認是哪一層產生問題。

### A. 聊天主流程：生成 assistant 答案

這是使用者輸入問題時一定會走到的主要 prompt 路徑：

| 層級 | 程式位置 | 實際內容 | 修改用途 |
| --- | --- | --- | --- |
| Agent system prompt | `backend/tools.py:715-727` | 從 `llm_config.system_prompt` 讀取，後面再附加 SQL 錯誤處理規則 | 修改整體角色、語氣、SQL 錯誤處理原則 |
| 聊天主 prompt | `backend/main.py:1106-1212` | 對話歷史、時間、使用者資訊、檔案資訊、system prompt、本次問題 | 修改模型實際看到的上下文與格式 |
| 使用者問題 | `backend/main.py:1202-1203` | `content`，也就是前端送來的文字 | 確認輸入是否被清理、截斷或改寫 |

聊天主 prompt 的結構大致如下：

```text
# 對話歷史
歷史 user／AI 訊息

# 當前資訊
時間、使用者 id、名稱、角色、上傳目錄

# 上傳檔案資訊
目前對話可使用的檔案與絕對路徑

# 系統提示
llm_config.system_prompt
上傳檔案問答工具使用規則

# 使用者問題
本次 content
```

其中 `llm_config.system_prompt` 可由管理員設定；後端會透過 `/api/admin/llm-config` 更新資料庫中的 system prompt。即使管理員沒有填寫，後端也會套用預設提示詞，並補上 `upload_file_qa_tool` 使用規則。

### B. 對話標題 prompt

| 程式位置 | 輸入 | 模型用途 |
| --- | --- | --- |
| `backend/main.py:689-705` | 第一則使用者訊息 `content` | 產生左側欄顯示的短標題 |

這是獨立的 `akasha.ask()`，不是聊天 Agent 的同一個回合。它要求模型只輸出簡短標題，後端再移除引號並限制最多 50 個字元。

### C. Agent 呼叫的工具 prompt

以下工具會在主 Agent 判斷需要時，額外呼叫模型或 RAG：

| 工具 | 程式位置 | 傳入的 prompt／query | 是否在主 Agent 啟用 |
| --- | --- | --- | --- |
| `upload_file_qa_tool` | `backend/tools.py:170-200` | 使用者針對檔案的問題 `question`，檔案路徑透過 `info=paths` 傳入 | 是 |
| `documents_rag_tool` | `backend/tools.py:624-648` | 使用者查詢 `query`，並搭配可搜尋的 RAG 文件 | 有 RAG data source 時是 |
| `chain_of_thought_tool` | `backend/tools.py:651-681` | 固定的分析指示詞加上 `query` | 否，目前沒有放入 `build_agent()` 的 tool list |
| `revising_prompt_tool` | `backend/tools.py:343-362` | 固定的修訂規則加上傳入的 `prompt` | 否，目前沒有放入 `build_agent()` 的 tool list |

主 Agent 目前實際註冊的工具清單在 `backend/tools.py:692-702`。因此，除錯時看到工具被呼叫，應先確認該工具是否真的在清單中，以及它是否又建立了第二次 LLM／RAG 呼叫。

### D. RAG 建立與文件摘要 prompt

這些不是每次聊天都會執行，而是在管理員建立或重建 RAG index 時使用：

| 程式位置 | 模型呼叫 | 用途 |
| --- | --- | --- |
| `backend/main.py:1817-1831` | `akasha.RAG(...); ak(..., prompt="測試")` | 驗證 RAG index 是否可用 |
| `backend/main.py:1843-1867` | `akasha.summary(...); summarizer(content=[file_path])` | 對每個文件產生摘要，保存到 `rag_file.summary` |

文件摘要結果會被用來建立 RAG tool description，位置在 `backend/tools.py:69-77`。這個 description 會告訴主 Agent 目前有哪些可搜尋文件，但它不是使用者問題本身的答案 prompt。

### E. 管理員的模型測試

`backend/main.py:2124-2146` 的 `/api/admin/llm-config/test` 會使用固定文字 `測試` 呼叫模型。這只能確認 provider／model 是否能回應，不能代表完整聊天 prompt 已經正確。

## Prompt 除錯建議

要修改或除錯時，可以依照以下順序確認：

1. 先確認 `backend/main.py:1202-1203` 的本次使用者問題是否正確進入主 prompt。
2. 檢查 `llm_config.system_prompt` 是否包含預期內容，以及是否被後端附加的上傳檔案規則或 SQL 規則影響。
3. 檢查歷史訊息是否被納入；`pending` 訊息不會放入歷史，且歷史筆數受 `HISTORY_MESSAGE_LIMIT` 限制。
4. 如果模型呼叫工具，另外檢查該工具的輸入。工具可能會再次呼叫 `akasha.ask()` 或 `akasha.RAG()`。
5. 如果是檔案問答，確認 `upload_file_qa_tool` 收到的 `file_paths` 與 `question` 是否正確。
6. 如果是文件 RAG，確認文件是否已建立 index、embedding model 是否一致，以及 `documents_rag_function()` 收到的 query。
7. 最後才檢查模型參數，例如 `model_name`、`temperature`、`max_input_tokens` 與 `max_output_tokens`。

## 8. 組合模型 Prompt

`backend/main.py` 的 `build_reply()` 會將下列內容組合成完整 prompt：

```text
最近對話紀錄
目前時間
使用者資訊
使用者檔案資訊
系統提示詞
本次使用者問題
```

歷史訊息會依照時間順序放入 prompt，且只會納入非 `pending` 的訊息。

## 9. 建立 Akasha Agent

後端會以 streaming 模式取得 Agent：

```python
agent = get_agent(stream=True)
result = agent(question=prompt, include_thinking=True)
```

Agent 設定位於 `backend/tools.py`，主要包含：

- LLM model
- temperature
- system prompt
- 最大輸入與輸出 token
- 最大推理回合數 `max_round=10`
- `stream=True`

可用工具包括：

- SQL／資料庫查詢
- 規則檢查
- Python 程式執行
- Google 搜尋
- 檔案問答
- JSON 儲存
- 文件 RAG 工具

文件 RAG 工具只有在存在可用的 RAG data source 時才會加入 Agent。

因此，模型可能直接回答，也可能先呼叫工具或 RAG，再根據工具結果繼續產生答案。

## 10. 模型事件進入 Queue

Akasha 回傳的 streaming event 會被轉換成系統事件：

| Akasha event | 系統事件 | 用途 |
| --- | --- | --- |
| `thinking` | `thinking` | 顯示目前思考或執行狀態 |
| `answer` | `answer_delta` | 傳送答案文字片段 |
| `tool` | `tool_call`／`tool_result` | 顯示工具呼叫與結果 |

每個事件會先放入 thread-safe Queue。後端的 async task 再從 Queue 取出事件，寫入 `message_event`。

`answer_delta` 同時會即時追加到 assistant message 的 `content` 欄位，因此資料庫中也會保留目前已生成的部分答案。

## 11. 後端透過 SSE 傳回前端

`backend/main.py` 的 `stream_message()` 會：

1. 驗證使用者是否有權限讀取該訊息。
2. 從 `message_event` 重播尚未收到的事件。
3. 等待新的事件進入 subscriber queue。
4. 以 `text/event-stream` 傳給瀏覽器。
5. 使用 `sequence` 確保事件順序。

事件格式概念如下：

```text
id: 3
data: {"version":1,"type":"answer_delta", ...}
```

HTTP response 會設定 `X-Accel-Buffering: no`，讓反向代理不要把串流內容累積到最後才傳送。

## 12. 前端逐段更新答案

`src/services/agentStream.js` 解析 SSE event 後，`chat.js` 會依事件類型更新 Pinia 狀態：

| 事件 | 前端行為 |
| --- | --- |
| `thinking` | 更新思考／執行狀態 |
| `tool_call` | 記錄工具呼叫 |
| `tool_result` | 記錄工具結果 |
| `answer_delta` | 將文字片段接到目前答案後面 |
| `done` | 將訊息狀態改為 `completed` |
| `error` | 將訊息狀態改為 `error` |
| `stopped` | 保留目前已生成的部分答案 |

因此，畫面上的答案是隨著 `answer_delta` 持續累加，而不是等模型完成後才一次顯示。

前端也會檢查事件序號。如果發現 sequence gap，會從最後一個已收到的序號重新連線，以避免遺漏答案片段。

## 13. 完成後永久保存

模型生成結束後，後端會：

1. 將 assistant message 設為 `completed`。
2. 保存完整答案。
3. 保存模型產生的檔案與下載連結。
4. 寫入最後的 `done` event。
5. 更新對話的 `updated_at`。
6. 通知所有 SSE subscribers。

如果生成過程中發生錯誤：

- 保留已生成的部分文字。
- 將訊息狀態設為 `error`。
- 寫入錯誤事件。

## 相關程式位置

| 元件 | 位置 |
| --- | --- |
| 輸入元件 | `src/components/chat/ChatInput.vue` |
| 聊天頁面 | `src/views/ChatView.vue` |
| 聊天狀態與送出流程 | `src/stores/chat.js` |
| SSE 解析與事件套用 | `src/services/agentStream.js` |
| 建立訊息與背景生成 | `backend/main.py` |
| Agent 與工具設定 | `backend/tools.py` |
| Streaming event 轉換與保存 | `backend/streaming_events.py` |
