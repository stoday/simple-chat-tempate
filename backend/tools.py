# type: ignore
import akasha
import akasha.agent.agent_tools as at
import pandas as pd
import os
from pathlib import Path
from datetime import datetime
from typing import List
import rich
import traceback


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

# def get_table_content(table_name: str | List[str]) -> str:
#     # # 統一轉為大寫
#     # table_name = table_name.upper()
#     try:
#         # outcome = pd.read_excel('C:/Users/today/Desktop/禾聯電/20250805-提供的資料/db_schema_descriptions-20250804_new.xlsx', sheet_name=table_name)
#         if table_name.__class__ == list:
#             outcome_list = []
#             for tn in table_name:
#                 outcome = pd.read_excel(
#                   'C:/Users/today/Desktop/禾聯電/20250805-提供的資料/TableSchema_new.xlsx', # 
#                   sheet_name=tn)
#                 outcome_list.append(f"### 表單: {tn}\n" + outcome.to_markdown(index=False, tablefmt="pipe"))
#             return "\n\n".join(outcome_list) # type: ignore
        
#         else:
#             outcome = pd.read_excel(
#             'C:/Users/today/Desktop/禾聯電/20250805-提供的資料/TableSchema_new.xlsx', # 
#             sheet_name=table_name)
            
#             # 將結果轉為 markdown 格式
#             return outcome.to_markdown(index=False, tablefmt="pipe")
        
#     except Exception as e:
#         return f"查詢表單 {table_name} 時發生錯誤: {e}"



# 創建工具
table_db_content_tool = akasha.create_tool(
    tool_name="get_db_table_content",
    tool_description="這是一個查詢資料表內容的工具，可以得知資料庫全部的表單、欄位意義與內容。",
    func=get_db_table_content
)

        
# 定義一個工具來執行 MSSQL 查詢
def execute_sql_query(query):
    import pyodbc
    import pandas as pd
    # 執行 MSSQL 查詢並返回結果
    # 使用 pyodbc 連接資料庫檔案，用 pandas 讀取資料
    # 連線 SQL Server
    # 設定連線資訊
    # server = "localhost,1433"   # SQL Server Docker container port 映射到本機
    server = os.environ.get('MSSQL_SERVER', 'localhost,1433')
    database = os.environ.get('MSSQL_DATABASE', 'master')
    username = os.environ.get('MSSQL_USER', 'sa')
    password = os.environ.get('MSSQL_PASSWORD', 'Mlops123!')

    # 是否使用 Windows (Trusted) Authentication
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

# 定義一個工具來執行 Python 代碼
def exec_python_code(code):
    rich.print("Executing exec_python_code tool...")
    def _exec(target_code: str):
        local_vars = {}
        exec(target_code, {}, local_vars)
        return str(local_vars)  # 返回執行後的本地變量字典

    try:
        # 先直接嘗試執行原始字串
        return _exec(code)
    except SyntaxError:
        # 若因為跳脫字元造成語法錯誤，嘗試將行分隔的 \\n 替換成真正換行（不動字串內的 '\n' 常值）
        if isinstance(code, str):
            import re

            fixed = re.sub(r"\\n(?=[ \t]*[^\s])", "\n", code)
            fixed = fixed.replace("\\t", "\t")
            try:
                return _exec(fixed)
            except Exception as e:
                print(traceback.format_exc())
                return f"執行 Python 代碼時發生錯誤: {e}"
    except Exception as e:
        print(traceback.format_exc())
        return f"執行 Python 代碼時發生錯誤: {e}"

exec_python_tool = akasha.create_tool(
    tool_name="exec_python_code",
    tool_description="""
    這是一個執行 Python 代碼的工具，可用來處理資料或進行計算。輸入參數 code 為「可直接執行」的 Python 代碼字串，請務必：
    1) 產生完整可執行程式，包含必要的 import。
    2) 將重點計算結果存成變數 result，並使用 print(result) 輸出，避免僅有回傳值無輸出。
    範例：
    - code = "result = 1 + 1\\nprint(result)"
    - code = "import math\\nresult = math.sqrt(16)\\nprint(result)"
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

        API_KEY = os.environ['GOOGLE_API_KEY']
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
def documents_rag_tool(query: str) -> str:
    rich.print("Executing documents_rag_tool...")
    ak = akasha.RAG(embeddings="openai:text-embedding-3-small",
                    model="openai:gpt-4o",
                    max_input_tokens=3000,
                    keep_logs=True,
                    verbose=True)
    
    response = ak(data_source=["經濟部攜手產業送暖企業捐贈家電寢具助雲嘉南災後復原.pdf"],
                  prompt=query)

    return response


# 創建工具
documents_rag_tool = akasha.create_tool(
    tool_name="documents_rag_tool",
    tool_description="""
    這個工具可以找出禾聯與雲嘉南災後復原的新聞報導。輸入參數 query 為查詢關鍵字。
    範例:
    - query = "akasha 是什麼？"
    """,
    func=documents_rag_tool
)


# 定義一個工具來進行多步驟思考
def chain_of_thought(query: str) -> str:
    rich.print("Executing chain_of_thought tool...")
    ak = akasha.ask(
        model="openai:gpt-4o",
        temperature=1.0,
        max_input_tokens=1048576,
        max_output_tokens=8192,
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


# 創建工具
documents_rag_tool = akasha.create_tool(
    tool_name="documents_rag_tool",
    tool_description="""
    這個工具可以找出禾聯與雲嘉南災後復原的新聞報導。輸入參數 query 為查詢關鍵字。
    範例:
    - query = "akasha 是什麼？"
    """,
    func=documents_rag_tool
)


# 建立 agent
agent = akasha.agents(
    tools=[today_tool, 
           table_db_content_tool,
           sql_query_tool,
           check_rules_tool,
           exec_python_tool,
           google_search_tool,
           # documents_rag_tool,
           at.saveJSON_tool()
           ],
    model='gemini:gemini-2.5-flash',
    # model='openai:gpt-4o',
    temperature=1.0,
    language='zh',
    verbose=True,
    max_input_tokens=1048576,
    max_output_tokens=8192,
    max_round=3,
    stream=True,
)
