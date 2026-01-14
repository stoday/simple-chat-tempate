# type: ignore
import akasha
import akasha.agent.agent_tools as at
from .rag_state import get_rag_data_sources, get_rag_instance
import pandas as pd
import os
import re
import subprocess
import sys
from pathlib import Path
from datetime import datetime
from typing import List
import rich
import traceback
from .database import get_connection, load_llm_config


def _fetch_rag_summaries():
    conn = None
    try:
        conn = get_connection()
        rows = conn.execute(
            "SELECT id, file_name, summary FROM rag_file ORDER BY created_at DESC"
        ).fetchall()
        return rows
    except Exception:
        return []
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


def _get_rag_summary_version() -> str:
    conn = None
    try:
        conn = get_connection()
        row = conn.execute(
            "SELECT MAX(summary_updated_at) AS last_updated FROM rag_file"
        ).fetchone()
        value = row["last_updated"] if row else None
        return value or ""
    except Exception:
        return ""
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


def _build_rag_tool_description() -> str:
    rows = _fetch_rag_summaries()
    if not rows:
        return "以下為可以此工具用 rag 查找的資料: (目前尚未建立摘要)"
    lines = ["以下為可以此工具用 rag 查找的資料:"]
    for row in rows:
        summary = row["summary"] or "(尚未建立摘要)"
        lines.append(f"- {row['file_name']}: {summary}")
    return "\n".join(lines)


def _build_rag_data_sources():
    conn = None
    try:
        conn = get_connection()
        rows = conn.execute(
            "SELECT file_path FROM rag_file ORDER BY created_at DESC"
        ).fetchall()
        data_sources = []
        for row in rows:
            relative_path = (Path("backend") / "rag_files" / row["file_path"]).as_posix()
            data_sources.append(relative_path)
        return data_sources
    except Exception:
        return []
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


def build_documents_rag_tool():
    return akasha.create_tool(
        tool_name="documents_rag_tool",
        tool_description=_build_rag_tool_description(),
        func=documents_rag_function
    )


# # 定義一個工具來回傳資料庫表單的總覽資訊
# def get_table_overview():
#     table_info = pd.read_excel(
#       'C:/Users/today/Desktop/禾聯電/20250805-提供的資料/db_schema_descriptions-20250804_new.xlsx', 
#       sheet_name='資料表綜覽')
#     # 轉為 markdown 格式
#     table_info = table_info.to_markdown(index=False, tablefmt="pipe")
#     return table_info


# # 創建工具
# table_overview_info = akasha.create_tool(
#     tool_name="table_overview",
#     tool_description="這是一個取得資料表單總覽的工具，可以了解各個資料表單的概要內容是什麼，不需要輸入參數。",
#     func=get_table_overview,
# )


# 定義一個工具來獲取今天的日期
def today_f():
    rich.print("Executing today_f tool...")
    now = datetime.now()
    return "today's date: " + str(now.strftime("%Y-%m-%d %H:%M:%S"))


# 創建工具
today_tool = akasha.create_tool(
    tool_name="today_date_tool",
    tool_description="This is the tool to get today's date, the tool doesn't have any input parameter.",
    func=today_f,
)


# 定義一個工具來查詢資料庫的表單有哪些欄位與內容意義
def get_db_table_content() -> str:
    # 使用 pathlib 建構跨平台路徑
    TOOLS_DIR = Path(__file__).resolve().parent
    kb_path = TOOLS_DIR / 'Knowledge' / 'optimized_prompt_full.txt'

    try:
        with kb_path.open('r', encoding='utf-8') as file:
            content = file.read()
    except FileNotFoundError:
        return f"Knowledge file not found: {kb_path}"
    except Exception as e:
        return f"Read Knowledge file error: {e}"

    return content


# 創建工具
table_db_content_tool = akasha.create_tool(
    tool_name="get_db_table_content",
    tool_description="這是一個查詢資料表內容的工具，可以得知資料庫全部的表單、欄位意義與內容。",
    func=get_db_table_content
)


# 定義一個針對上傳檔案問答的工具
def upload_file_qa(file_paths: str, question: str) -> str:
    rich.print(f"Executing upload_file_qa tool for files: {file_paths}...")
    # Split paths if multiple provided
    paths = [p.strip() for p in file_paths.split(",") if p.strip()]
    if not paths:
        return "錯誤：未提供有效的檔案路徑。"

    # Get llm config for the ask object
    db = get_connection()
    try:
        cfg = load_llm_config(db)
    finally:
        db.close()

    ask_obj = akasha.ask(
        model=cfg["model_name"],
        temperature=cfg["temperature"],
        max_input_tokens=cfg["max_input_tokens"],
        max_output_tokens=cfg["max_output_tokens"],
        verbose=True
    )

    response = ask_obj(prompt=question, info=paths)
    return response


# 創建工具
upload_file_qa_tool = akasha.create_tool(
    tool_name="upload_file_qa_tool",
    tool_description="這是一個針對已上傳檔案進行問答的工具。當使用者詢問有關上傳檔案的內容、總結或細節時使用。需輸入參數 file_paths (字串，檔案完整的絕對路徑，多個路徑以逗號隔開) 與 question (字串，想要詢問檔案的問題內容)。",
    func=upload_file_qa
)

        
# 定義一個工具來執行 MSSQL 查詢
def load_mssql_config_from_db():
    try:
        conn = get_connection()
    except Exception:
        return None
    try:
        row = conn.execute("SELECT * FROM mssql_config WHERE id = 1").fetchone()
        if not row:
            return None
        return {
            "server": row["server"],
            "database": row["database"],
            "username": row["username"],
            "password": row["password"],
            "use_trusted": bool(row["use_trusted"]),
        }
    except Exception:
        return None
    finally:
        try:
            conn.close()
        except Exception:
            pass


def execute_sql_query(query):
    import pyodbc
    import pandas as pd
    # 執行 MSSQL 查詢並返回結果
    # 使用 pyodbc 連接資料庫檔案，用 pandas 讀取資料
    # 連線 SQL Server
    # 設定連線資訊
    # server = "localhost,1433"   # SQL Server Docker container port 映射到本機
    db_config = load_mssql_config_from_db() or {}
    server = db_config.get("server") or os.environ.get('MSSQL_SERVER', 'localhost,1433')
    database = db_config.get("database") or os.environ.get('MSSQL_DATABASE', 'master')
    username = db_config.get("username") or os.environ.get('MSSQL_USER', 'sa')
    password = db_config.get("password") or os.environ.get('MSSQL_PASSWORD', 'Mlops123!')

    # 是否使用 Windows (Trusted) Authentication
    use_trusted = db_config.get("use_trusted")
    if use_trusted is None:
        use_trusted = os.environ.get('MSSQL_USE_TRUSTED', 'false').lower() in ('1', 'true', 'yes')

    # Normalize escaped characters often introduced by JSON/LLM outputs
    if isinstance(query, str):
        # 把常見的 escape 還原為真實字元
        query = query.replace('\\r\\n', '\n').replace('\\n', '\n').replace('\\t', '\t')
        # 處理被多重跳脫的反斜線，例如 "\\\\n" -> "\\n" -> "\n"
        query = query.replace('\\\\', '\\')

    # 執行查詢
    try:
        # 建立連線字串
        if use_trusted:
            # 使用 Windows Authentication（Trusted Connection）
            # 注意：在 Windows 上，Python 程式需以欲使用的 Windows 帳號執行，
            # 才會帶入該帳號的憑證進行驗證。
            conn_str = (
                f"DRIVER={{ODBC Driver 18 for SQL Server}};"
                f"SERVER={server};"
                f"DATABASE={database};"
                f"Trusted_Connection=yes;"
                f"Encrypt=no;"
            )
        else:
            # 使用 SQL 帳號/密碼（SQL Authentication）
            conn_str = (
                f"DRIVER={{ODBC Driver 18 for SQL Server}};"
                f"SERVER={server};"
                f"DATABASE={database};"
                f"UID={username};"
                f"PWD={password};"
                f"Encrypt=no;"
            )

        sqlserver_conn = pyodbc.connect(conn_str)
        
        # 建立與 SQL Server 的連線
        sqlserver_conn.autocommit = True  # 確保自動提交

        outcome = pd.read_sql_query(query, sqlserver_conn)
        # 將結果轉為 markdown 格式
        result_markdown = outcome.to_markdown(index=False, tablefmt="pipe")
        return result_markdown

    except Exception as e:
        print(traceback.format_exc())
        return f"執行 SQL 查詢時發生錯誤: {e}"

    finally:
        try:
            sqlserver_conn.close()
        except Exception:
            pass


# 創建工具
sql_query_tool = akasha.create_tool(
    tool_name="execute_sql_query",
    tool_description="""
    這是一個執行 MSSQL 語法來作查詢的工具，可以用來查詢銷售庫存或業務的資料庫中的資料。輸入參數 query 為 MSSQL 查詢語句。
    範例: 
    - SELECT * FROM pmpsa WHERE pmpsa.pmpsa_ent=168;
    """,
    func=execute_sql_query
)


def revising_prompt_tool(prompt):
  # 在這裡實現對 prompt 的修訂邏輯，將自然描述的需求轉成更詳細的需求
  system_prompt = '''
  # 任務
  將使用者描述的需求，轉換成更詳細的需求描述，並且包含必要的規則。
  例如
  - 使用者需求: 找出過去三個月最熱門前十名產品的品名。
  - 轉換後的需求: 請查詢資料庫中過去三個月的銷售資料，找出銷售次數最多的前十名產品，並回傳其品名。

  '''
  revisor = akasha.ask(
    temperature=1.0,
    verbose=True,
    max_input_tokens=1048576,
    max_output_tokens=8192,
  )
  
  revised_prompt = revisor(system_prompt + '\n\n#使用者需求: ' + prompt,)

  return revised_prompt


# 定義一個最後詳細檢查使用者需求與產生的相對應 sql 指令，是否符合規則的工具
def check_rules():
    # 定義一個最後詳細檢查使用者需求與產生的相對應 sql 指令，是否符合規則的工具
    sale_rules = '''
    # 銷售與出貨：
    - 計算銷售量時，就要統計 smdob_docno (單據號碼) 出現的次數，而非使用 smdob_qty (數量) 欄位，也不是 smdob_itemno (產品編號) 欄位。
    - 銷售的出貨日期請以 smdoa 表單的 smdoa_pstdt (資料過帳日) 為準。而非使用 smdoa_docdt (單據日期)，也不是 smdob_007 (預計出貨日期)。
    - 當查詢銷售產品數量時，請使用 smdob_014 (產品類型) 欄位來過濾，僅包含 '1' (一般) 的產品類型，排除 '2' (贈品)，同時 smdob_loc (庫別) 欄位不等於 'AU' 也就是不會放置在「辦公倉」的部分。然後 smdoa_stus (單據狀態) 欄位必須等於 'S' (過帳)。
    - 有關業務人員的部分，要從 smrta 表單來做查詢。使用 smrta.smrta_002 欄位作為業務的姓名查找，smdob.smdob_005 作為總銷售金額的欄位，不要找 smdoa_epoe 這個欄位。例如說，如果要找 2025 年銷售最好的業務人員，可以如以下的 SQL 指令:
    ```sql
    SELECT TOP 5
  min(smrta.smrta_002) AS 業務姓名, --smrta_002	業務簡稱
  SUM(smdob.smdob_005) AS 總銷售金額
FROM smdob
JOIN smdoa
  ON smdoa_ent = smdob_ent and smdoa_site = smdob_site and smdob.smdob_docno = smdoa.smdoa_docno
JOIN smrta
  ON smrta.smrta_ent = smdob.smdob_ent AND smrta.smrta_site = smdob.smdob_site and smdoa_ud008=smrta_001
  --smdoa_ud008	業務區別 / smrta_001 業務區別代號
WHERE
  YEAR(smdoa.smdoa_pstdt) = 2025 and smdoa_stus='S' and smdob_014='1' and smdob_loc<>'AU'
-- smdoa_stus='S' 單據狀態為'過帳' / smdoa_pstdt 資料過帳日 / smdob_014 產品類型　"1.一般　2.贈品" / smdob_loc庫別<>AU辦公倉
  and smrta_stus='Y' AND smrta.smrta_002 <> ''
  --smrta_stus	狀態碼
GROUP BY
  smrta.smrta_001 --smrta_001 業務區別代號
ORDER BY
  總銷售金額 DESC;

    '''
    
    return sale_rules


# 創建工具
check_rules_tool = akasha.create_tool(
    tool_name="check_rules_tool",
    tool_description="""
    這個工具會回傳需要查詢的規則。沒有需要輸入的參數。
    """,
    func=check_rules
)

import ast

# 定義一個工具來執行 Python 代碼 (Subprocess 穩定版)
def exec_python_code(code, output_path: str = "./backend/chat_uploads/"):
    rich.print("Executing exec_python_code tool (subprocess mode)...")
    
    # 1. 確保目錄存在
    output_dir = Path(output_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    codegen_dir = Path("./backend/codegen")
    codegen_dir.mkdir(parents=True, exist_ok=True)
    
    # 2. 準備腳本檔案
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    script_file = codegen_dir / f"script_{timestamp}.py"
    
    # 3. 寫入程式碼（具備強大的自動解轉義邏輯）
    try:
        fixed_code = code
        if isinstance(fixed_code, str):
            # 針對 LLM 可能產生的雙重或多重轉義進行循環修復
            # 我們會不斷尝试還原，直到程式碼可以被正確解析為止
            max_attempts = 3
            current_attempt = 0
            while current_attempt < max_attempts:
                try:
                    # 嘗試解析語法，如果成功代表程式碼格式已正確
                    ast.parse(fixed_code)
                    break
                except SyntaxError:
                    # 如果語法出錯且包含反斜線，嘗試進行一次符號還原
                    if "\\" in fixed_code:
                        new_code = fixed_code.replace("\\n", "\n").replace("\\t", "\t").replace('\\"', '"')
                        if new_code == fixed_code:
                            break
                        fixed_code = new_code
                    else:
                        break
                current_attempt += 1

        with open(script_file, "w", encoding="utf-8") as f:
            f.write(fixed_code)
    except Exception as e:
        return f"建立腳本時發生錯誤: {e}"

    # 4. 執行腳本並擷取輸出
    try:
        # 設定環境變數確保輸出為 UTF-8
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        
        proc_result = subprocess.run(
            [sys.executable, str(script_file)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60,
            cwd=os.getcwd(),
            env=env
        )
        
        stdout = proc_result.stdout
        stderr = proc_result.stderr
        
        # 5. 後處理：從輸出中擷取結果與檔案路徑
        final_output_lines = [f"--- 執行輸出 ---", stdout]
        if stderr:
            final_output_lines.extend(["--- 錯誤訊息 ---", stderr])
            
        # 尋找輸出中提到的路徑或 file_path
        potential_paths = re.findall(r"(?:file_path|path)[\s:=]+['\"]?([a-zA-Z0-9\._\-\/\\:]+)['\"]?", stdout, re.I)
        updated_files = []
        
        for p in set(potential_paths):
            path_obj = Path(p)
            if not path_obj.is_absolute() and not path_obj.exists():
                path_obj = output_dir / path_obj
            
            if path_obj.exists() and path_obj.is_file():
                # 確保在 output_path 內且尚未加上時間標記
                if not re.search(r"_\d{8}_\d{6}", path_obj.stem):
                    new_name = f"{path_obj.stem}_{timestamp}{path_obj.suffix}"
                    new_path = path_obj.with_name(new_name)
                    try:
                        path_obj.rename(new_path)
                        updated_files.append(new_path.as_posix())
                    except Exception:
                        updated_files.append(path_obj.as_posix())
                else:
                    updated_files.append(path_obj.as_posix())

        if updated_files:
            final_output_lines.append("\n--- 生成檔案路徑 (已套用時間戳) ---")
            for f_path in updated_files:
                final_output_lines.append(f_path)
                
        return "\n".join(final_output_lines)

    except subprocess.TimeoutExpired:
        return "錯誤：程式執行超過 60 秒，已強制終止。"
    except Exception as e:
        print(traceback.format_exc())
        return f"執行過程中發生系統錯誤: {e}"


exec_python_tool = akasha.create_tool(
    tool_name="exec_python_code",
    tool_description="""
    # 工具說明
    這是一個在獨立環境中執行 Python 程式碼的工具。適合用於複雜計算、資料分析、繪製圖表。
    
    # 執行環境規範
    1) **寫作指南**：請像撰寫標準 .py 檔案一樣編寫程式碼。可以自由使用多行字串 `\"\"\"...\"\"\"`。
    2) **存檔路徑**：產出的檔案請固定存放在 `./backend/chat_uploads/`。
    3) **結果回傳**：
       - 請務必將最終計算結果透過 `print()` 輸出到螢幕。
       - 若產生了檔案，請 `print(f'file_path: {path}')` 以便追蹤並提供下載。
    4) **繪圖規范**：
       - 使用 matplotlib 繪圖，並務必透過 `fm.FontProperties(fname='TaipeiSansTCBeta-Regular.ttf')` 設定中文字體。
    5) **常用函式庫**：提供 pandas, matplotlib, numpy, statsmodels, openpyxl 等。
    
    # 限制
    - 任務執行限時 60 秒。
    - 生成的腳本會儲存在 `./backend/codegen/` 目錄中。
    """,
    func=exec_python_code
)


# 定義一個工具來做 Google 搜尋
def google_search_function(query):
    rich.print("Executing google_search_function...")
    try:
        import os
        import requests
        import dotenv
        dotenv.load_dotenv()

        API_KEY = os.environ.get('GSEARCH_API_KEY') or os.environ.get('GOOGLE_API_KEY')
        CX = os.environ['GOOGLE_CSE_ID']
        url = "https://www.googleapis.com/customsearch/v1"
        params = {"key": API_KEY, "cx": CX, "q": query}
        resp = requests.get(url, params=params)
        data = resp.json()

        search_results = []
        if 'items' in data:
            for item in data['items']:
                search_results.append({
                    "title": item.get('title', ''),
                    "snippet": item.get('snippet', ''),
                    "source": item.get('link', '')
                })
        else:
            return f"Google 搜尋未返回任何結果。"

        print('search_results:', search_results)
    except Exception as e:
        print(traceback.format_exc())
        return f"執行 Google 搜尋時發生錯誤: {e}"
    
    return str(search_results)


# # 需要啟用並使用 Google 的「Custom Search JSON API」（也稱 Programmable Search Engine / Custom Search），並在 Programmable Search Engine 建一個 CSE（取得 cx），同時在 Google Cloud Console 產生 API Key（GOOGLE_API_KEY）。
# 1. 建立 Google Cloud 專案（或選現有專案）
# 前往 https://console.cloud.google.com ，用你的 Google 帳號登入，建立一個新的 Project（或選一個現有 Project）。
# 2. 啟用 API：Custom Search JSON API
# 在 Cloud Console 的「API 與服務」→「啟用 API 與服務」，搜尋 "Custom Search API" 或 "Custom Search JSON API"，點進去按「啟用」。
# 3. 產生 API key
# 在 Cloud Console → API 與服務 → 憑證（Credentials）→ 建立憑證 → 選「API 金鑰」。
# 取得金鑰後建議設定 Key 限制（HTTP referer 或 IP），避免濫用。
# 4. 建立 Programmable Search Engine（CSE），取得 cx
# 前往 https://programmablesearchengine.google.com/ （或舊稱 cse.google.com）。
# 新增搜尋引擎：在「Sites to search」可以指定網站清單；如果要搜尋整個網路，建立後進入控制台把「Search the entire web」或把 Sites 設為 www.google.com 類似選項開啟（介面可能有變動，找「Search the entire web」或類似選項）。
# 建立後從設定或控制台取得 Search engine ID（就是 cx）。
# 5.（選擇）若要搜尋圖片：在 CSE 設定中開啟 Image Search。
# 把金鑰與 cx 設到你的應用環境
# 在 .env 或環境變數中加入：
# 你的前端/後端程式呼叫時用這兩個值。

# ```
# GOOGLE_API_KEY=你的_API_KEY
# GOOGLE_CSE_ID=你的_CX_ID
# ```

# 創建工具
google_search_tool = akasha.create_tool(
    tool_name="google_search_tool",
    tool_description="""
    這是一個使用 Google 搜尋的工具，可以用來查找相關資訊。輸入參數 `query` 為搜尋關鍵字。
    範例:
    - query = "最新的 SQL 查詢最佳實踐"
    """,
    func=google_search_function
)


# 定義一個使用文件檢索增強生成（RAG）技術的工具
def documents_rag_function(query: str) -> str:
    rich.print("Executing documents_rag_tool...")
    ak = get_rag_instance()
    if ak is None:
        ak = akasha.RAG(embeddings="openai:text-embedding-3-small",
                        model="openai:gpt-4o",
                        max_input_tokens=3000,
                        keep_logs=True,
                        verbose=True)
    data_sources = get_rag_data_sources() or _build_rag_data_sources()
    response = ak(data_sources=data_sources, prompt=query)

    return response


# 定義一個工具來進行多步驟思考
def chain_of_thought(query: str) -> str:
    rich.print("Executing chain_of_thought tool...")
    db = get_connection()
    try:
        cfg = load_llm_config(db)
    finally:
        db.close()
        
    ak = akasha.ask(
        model=cfg["model_name"],
        temperature=cfg["temperature"],
        max_input_tokens=cfg["max_input_tokens"],
        max_output_tokens=cfg["max_output_tokens"],
        verbose=True,
    )
    
    response = ak('將下列使用者提問的需求，拆解成多步驟的思考過程，並且一步步地給出解決方案，最後再給出完整的回答。\n\n使用者提問: ' + query)

    return response


# 創建工具
chain_of_thought_tool = akasha.create_tool(
    tool_name="chain_of_thought_tool",
    tool_description="""
    這是一個進行多步驟思考的工具，可以幫助拆解複雜問題並逐步解決。輸入參數 query 為使用者的提問。
    範例:
    - query = "請說明如何提升銷售業績？"
    """,
    func=chain_of_thought
)


def build_agent(stream: bool = False):
    db = get_connection()
    try:
        cfg = load_llm_config(db)
    finally:
        db.close()
        
    documents_rag_tool = build_documents_rag_tool()
    return akasha.agents(
        tools=[today_tool,
               table_db_content_tool,
               sql_query_tool,
               check_rules_tool,
               exec_python_tool,
               documents_rag_tool,
               google_search_tool,
               upload_file_qa_tool,
               at.saveJSON_tool()
               ],
        model=cfg["model_name"],
        temperature=cfg["temperature"],
        system_prompt=cfg.get("system_prompt"),
        language='zh',
        verbose=True,
        keep_logs=True,
        max_input_tokens=cfg["max_input_tokens"],
        max_output_tokens=cfg["max_output_tokens"],
        max_round=10,
        stream=stream,
    )


# Global agent instance with stronger singleton pattern
# Global agent instance with Thread-Local storage for safety in ThreadPool
import threading

class AgentThreadLocal(threading.local):
    """
    Thread-local storage for Agent.
    Each thread in the ThreadPool will have its own independent instance of the Agent.
    This prevents race conditions if the Agent object itself holds state during execution.
    """
    def __init__(self):
        super().__init__()
        self._agent = None
        self._stream = None

    def get_agent(self, stream: bool = False):
        import sys
        
        # Check if this thread already has a cached agent
        if self._agent is not None and self._stream == stream:
            tid = threading.get_ident()
            msg = f"[AGENT CACHE] Using cached agent in Thread {tid} (stream={stream})"
            print(msg, flush=True)
            sys.stdout.flush()
            return self._agent
        
        # Build new agent for this thread
        tid = threading.get_ident()
        msg = f"[AGENT CACHE] Building new agent for Thread {tid} (stream={stream})"
        print(msg, flush=True)
        sys.stdout.flush()
        
        agent = build_agent(stream=stream)
        self._agent = agent
        self._stream = stream
        return agent

    def clear_cache(self):
        self._agent = None
        self._stream = None


_thread_local_storage = AgentThreadLocal()


def get_agent(stream: bool = False):
    """Get or create agent instance for the current thread."""
    return _thread_local_storage.get_agent(stream)


def clear_agent_cache():
    """Clear agent cache for the current thread."""
    _thread_local_storage.clear_cache()
