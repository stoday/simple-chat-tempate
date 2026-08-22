# 遠端 Text-to-SQL E2E 測試

## 目的與資料流

本工具測試遠端已部署的完整流程：

~~~text
測試 runner container
    → frontend / Nginx
    → backend container
    → Agent
    → Gemma4:26b / Ollama
    → execute_sql_query
    → MSSQL
~~~

測試不比對最後的自然語言答案，只擷取 SSE 中符合以下條件的事件：

~~~text
event.type == "tool_call"
event.payload.name == "execute_sql_query"
~~~

實際比對的 SQL 位於：

~~~text
event.payload.arguments.query
~~~

測試案例來源是：

~~~text
docs/text_to_sql_qa_test_cases.md
~~~

## 測試檔案

~~~text
tests/
├── Dockerfile
├── requirements.txt
├── run_text_to_sql.py
└── README.md
~~~

## 一、確認遠端 containers 與 network

在遠端主機執行：

~~~bash
docker ps
docker network ls
docker inspect simplechat-frontend
docker inspect simplechat-backend
~~~

找出 frontend 與 backend 共同使用的 network。Compose 預設 network 通常類似：

~~~text
<compose-project>_default
~~~

例如：

~~~text
simplechat_default
~~~

測試 runner 必須加入該 network，並使用：

~~~text
http://simplechat-frontend
~~~

測試 runner 不需要直接連線到 Ollama；它只呼叫 frontend，backend 會依正式設定連線到 LLM。

## 二、建立測試 image

請在包含完整專案 checkout 的遠端主機執行：

~~~bash
docker build -f tests/Dockerfile -t heranchat-text-to-sql-e2e .
~~~

如果 docs/text_to_sql_qa_test_cases.md 有修改，請重新 build：

~~~bash
docker build --no-cache -f tests/Dockerfile -t heranchat-text-to-sql-e2e .
~~~

這個 image 不會修改正式的 frontend、backend 或 LLM image。

## 三、執行單一案例

Linux：

~~~bash
mkdir -p artifacts/text_to_sql
docker run --rm --network <existing_network> -e BASE_URL=http://simplechat-frontend -e TEST_EMAIL=heranchat-e2e@example.com -e TEST_PASSWORD=test-only-password -e RESULTS_DIR=/results -v "$(pwd)/artifacts/text_to_sql:/results" heranchat-text-to-sql-e2e --case 01
~~~

```bash
mkdir -p artifacts/text_to_sql
docker run --rm --network simple-chat-tempate_default -e BASE_URL=http://heranchat.demo-today.org -e TEST_EMAIL=admin@demo.heran -e TEST_PASSWORD=password123 -e RESULTS_DIR=/results -v "$(pwd)/artifacts/text_to_sql:/results" heranchat-text-to-sql-e2e --case 01
```

請將 existing_network 替換成實際 network，例如：

~~~bash
--network simplechat_default
~~~

PowerShell：

~~~powershell
New-Item -ItemType Directory -Force artifacts/text_to_sql
docker run --rm --network <existing_network> -e BASE_URL=http://simplechat-frontend -e TEST_EMAIL=heranchat-e2e@example.com -e TEST_PASSWORD=test-only-password -e RESULTS_DIR=/results -v "C:/path/to/artifacts/text_to_sql:/results" heranchat-text-to-sql-e2e --case 01
~~~

PowerShell 的 volume 路徑請替換成遠端主機實際的絕對路徑。

## 四、執行多個或全部案例

執行指定案例：

~~~bash
docker run --rm --network <existing_network> -e BASE_URL=http://simplechat-frontend -e TEST_EMAIL=heranchat-e2e@example.com -e TEST_PASSWORD=test-only-password -e RESULTS_DIR=/results -v "$(pwd)/artifacts/text_to_sql:/results" heranchat-text-to-sql-e2e --case 01 --case 07 --case 10
~~~

執行全部案例時移除所有 case 參數：

~~~bash
docker run --rm --network <existing_network> -e BASE_URL=http://simplechat-frontend -e TEST_EMAIL=heranchat-e2e@example.com -e TEST_PASSWORD=test-only-password -e RESULTS_DIR=/results -v "$(pwd)/artifacts/text_to_sql:/results" heranchat-text-to-sql-e2e
~~~

個案 07 預期有兩筆 SQL，runner 會依 SQL 分號拆成兩筆。

## 五、環境變數

| 變數 | 必填 | 說明 |
|---|---:|---|
| BASE_URL | 否 | frontend URL，預設為 http://simplechat-frontend |
| TEST_EMAIL | 是 | 專用測試帳號 email |
| TEST_PASSWORD | 是 | 專用測試帳號密碼 |
| TEST_DISPLAY_NAME | 否 | 測試帳號顯示名稱 |
| RESULTS_DIR | 否 | container 內結果目錄，預設為 /results |

runner 會先嘗試註冊帳號。若帳號已存在，會直接嘗試登入。請使用測試專用帳號，不要使用正式使用者帳號。

## 六、測試結果

每次執行會產生：

~~~text
artifacts/text_to_sql/text_to_sql_YYYYMMDDTHHMMSSZ.json
~~~

每個案例會保存：

- 執行時間與耗時
- 測試案例 ID 與問題
- conversation ID
- assistant message ID
- 原始 SSE
- 所有解析後的 events
- event type 與 sequence
- expected SQL
- actual SQL
- normalized SQL
- SQL 數量是否一致
- exact SQL match
- terminal event
- 錯誤訊息

結果範例：

~~~json
{
  "case_id": "01",
  "conversation_id": 123,
  "message_id": 456,
  "sql_count_match": true,
  "exact_sql_match": false,
  "event_types": ["thinking", "tool_call", "tool_result", "done"],
  "terminal_event": "done"
}
~~~

exact_sql_match 為 false 不一定代表 SQL 錯誤，只代表基本 normalization 後文字仍不同。

## 七、交給 LLM 做 SQL 語意比較

可以把 JSON 結果交給另一個 LLM，要求比較 expected_sql 與 actual_sql。

請檢查：

1. 使用的資料表。
2. JOIN 與 JOIN 條件。
3. WHERE 條件。
4. 日期範圍。
5. TOP 數量。
6. GROUP BY。
7. SUM、COUNT、COUNT DISTINCT 等 aggregate function。
8. ORDER BY 與排序方向。
9. alias 或空白是否只是表面差異。
10. 是否可能導致實際查詢結果不同。

建議分類：

~~~text
semantically_equivalent
semantically_different
unable_to_determine
~~~

建議提示詞：

~~~text
請比較 expected_sql 與 actual_sql 是否具有相同查詢語意。
逐項檢查 table、JOIN、WHERE、日期範圍、TOP、
GROUP BY、aggregate function、ORDER BY 與過濾條件。
不要因為空白、大小寫、alias 或等價日期寫法不同，
就直接判定 SQL 錯誤。
最後分類為 semantically_equivalent、
semantically_different 或 unable_to_determine。
~~~

## 八、失敗調查

### runner 無法啟動

~~~bash
docker image ls heranchat-text-to-sql-e2e
docker build --no-cache -f tests/Dockerfile -t heranchat-text-to-sql-e2e .
~~~

### 無法連線到 frontend

啟動測試 image shell：

~~~bash
docker run --rm -it --network <existing_network> --entrypoint sh heranchat-text-to-sql-e2e
~~~

在 container 內檢查 DNS：

~~~sh
python -c "import socket; print(socket.gethostbyname('simplechat-frontend'))"
~~~

檢查 HTTP：

~~~sh
python -c "import urllib.request; print(urllib.request.urlopen('http://simplechat-frontend/docs').status)"
~~~

### 沒有擷取到 SQL

查看結果 JSON 的 raw_sse、events 與 event_types，確認是否存在：

~~~text
type = tool_call
payload.name = execute_sql_query
payload.arguments.query
~~~

### SQL 數量不一致

比較 expected_sql 與 actual_sql。個案 07 預期兩筆 SQL；如果 Agent 用一筆查詢完成兩個月份，交給 LLM 判斷是否語意等價。

### terminal event 不是 done

- done：完成。
- error：Agent 或 LLM 生成失敗。
- stopped：生成被停止。

## 九、LLM/Ollama 位址

如果 Ollama 在遠端主機上，backend 可能使用：

~~~text
http://host.docker.internal:11434
~~~

如果 Ollama 是另一個 container，backend 應使用 network 中可解析的 service name：

~~~text
http://ollama:11434
~~~

不要在 backend container 裡使用 127.0.0.1:11434，因為這會指向 backend container 自己。

## 十、測試資料清理

runner 會建立測試 user、conversation、user message、assistant message 與 SSE events。

目前不會自動刪除，方便使用 conversation ID 和 message ID 追查。正式大量執行前，請：

- 使用專用測試帳號。
- 確認測試資料不影響正式報表。
- 定期清理舊測試 conversation。
- 保存 JSON 結果與執行時間。


## 十二、自動化整個流程

本專案提供 scripts/remote_text_to_sql.ps1，可自動執行：

1. 檢查 git、ssh、scp。
2. 只 stage 指定的 knowledge、測試工具、案例文件與 automation script。
3. commit 並在指定 -Push 時執行 git push。
4. SSH 到遠端執行 git pull --ff-only。
5. 執行 docker compose build 與 docker compose up -d。
6. 建立 Text-to-SQL 測試 image。
7. 將 runner 加入指定 Docker network。
8. 執行指定案例或全部案例。
9. 用 SCP 將最新 JSON artifact 拉回本機。

### 遠端建立測試 env file

請在遠端主機建立只供測試使用的 env file：

~~~bash
cd /path/to/HERANCHAT
umask 077
cat > .env.text-to-sql-e2e <<'EOF'
TEST_EMAIL=heranchat-e2e@example.com
TEST_PASSWORD=test-only-password
TEST_DISPLAY_NAME=Text-to-SQL E2E
EOF
~~~

這個檔案不要 commit，也不要放入 GitHub。它只留在遠端主機，並由 docker run 的 env-file 讀取。

### 自動執行全部流程

在本機專案根目錄執行：

~~~powershell
.\scripts\remote_text_to_sql.ps1 -RemoteHost user@remote-host -RemoteProjectPath /opt/HERANCHAT -RemoteNetwork simple-chat-tempate_default -BaseUrl http://heranchat.demo-today.org -RemoteEnvFile /opt/HERANCHAT/.env.text-to-sql-e2e -Push
~~~

如果 runner 應該經由 frontend container 內部 DNS 呼叫：

~~~powershell
.\scripts\remote_text_to_sql.ps1 -RemoteHost user@remote-host -RemoteProjectPath /opt/HERANCHAT -RemoteNetwork simple-chat-tempate_default -BaseUrl http://simplechat-frontend -RemoteEnvFile /opt/HERANCHAT/.env.text-to-sql-e2e -Push
~~~

### 參數說明

| 參數 | 說明 |
|---|---|
| RemoteHost | SSH 目標，例如 user@remote-host |
| RemoteProjectPath | 遠端 checkout 絕對路徑 |
| RemoteNetwork | frontend/backend 共用的 Docker network |
| BaseUrl | runner 要呼叫的 frontend URL |
| RemoteEnvFile | 遠端測試 env file 路徑 |
| Push | 明確允許本機 commit 並 git push |
| CaseId | 可重複指定，例如 -CaseId 01 -CaseId 07 |
| NoCache | 測試 image 使用 docker build --no-cache |
| SkipDeploy | 不執行遠端 Compose rebuild/up |
| SkipTest | 只更新部署，不執行 E2E runner |

### 只測指定案例

~~~powershell
.\scripts\remote_text_to_sql.ps1 -RemoteHost user@remote-host -RemoteProjectPath /opt/HERANCHAT -RemoteNetwork simple-chat-tempate_default -BaseUrl http://heranchat.demo-today.org -RemoteEnvFile /opt/HERANCHAT/.env.text-to-sql-e2e -CaseId 01 -CaseId 07 -Push
~~~

### 強制重建測試 image

加入：

~~~powershell
-NoCache
~~~

### 只執行遠端測試，不重新部署

適合 frontend/backend 已是正確版本，只想重跑測試：

~~~powershell
.\scripts\remote_text_to_sql.ps1 -RemoteHost user@remote-host -RemoteProjectPath /opt/HERANCHAT -RemoteNetwork simple-chat-tempate_default -BaseUrl http://heranchat.demo-today.org -RemoteEnvFile /opt/HERANCHAT/.env.text-to-sql-e2e -SkipDeploy -CaseId 01
~~~

### 安全注意事項

- 不加 -Push 時，script 不會執行 git push。
- script 只會 stage 預先列出的路徑，不會把整個 worktree 全部加入 commit。
- 測試密碼不寫入 script，也不會傳到 GitHub。
- 遠端 env file 必須由使用者自行建立。
- 執行前請確認 git status，避免把其他修改混入 commit。
- 遠端測試失敗時，script 仍會嘗試拉回已產生的 JSON artifact。
- 本機必須已設定 SSH key，且能使用 ssh 與 scp 連線遠端主機。
