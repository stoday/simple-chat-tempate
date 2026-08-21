# Text-to-SQL 測試驗證個案集 (Test Cases)

- **版本**: 20260821-v1
- **說明**: 本文檔用於記錄 Text-to-SQL 模型的評測基準。每筆測試個案包含「測試問題（輸入）」與「標準 SQL 語法（正確回應 / 說明）」。

---

## 測試個案 01

### 測試問題 (Input)
> 找出 2025 年 5 月 19 日至 2025 年 8 月 19 日最熱門產品的品名？

### 正確回應 / 說明 (Ground Truth SQL)
```sql
SELECT TOP 10
    T2.smdob_itemno, 
    T2.smdob_001, 
    COUNT(DISTINCT T2.smdob_docno) AS total_sales_times
FROM smdoa AS T1
INNER JOIN smdob AS T2
    ON T1.smdoa_ent = T2.smdob_ent 
   AND T1.smdoa_site = T2.smdob_site 
   AND T1.smdoa_docno = T2.smdob_docno
WHERE T1.smdoa_stus = 'S' 
  AND T1.smdoa_pstdt >= '2025-05-19'
  AND T1.smdoa_pstdt < '2025-08-20'
  AND T2.smdob_014 = '1' 
  AND T2.smdob_loc <> 'AU'
GROUP BY T2.smdob_itemno, T2.smdob_001
ORDER BY total_sales_times DESC;
```
> **業務規則說明：**
> - `smdoa_stus = 'S'`：單據狀態為「過帳」
> - `smdoa_pstdt`：以「資料過帳日」為銷售統計依據
> - `smdob_014 = '1'`：產品類型為「1.一般」（排除贈品等）
> - `smdob_loc <> 'AU'`：排除辦公倉

---

## 測試個案 02

### 測試問題 (Input)
> 哪一款產品退貨次數最高？

### 正確回應 / 說明 (Ground Truth SQL)
```sql
SELECT TOP 10  
    smsrb_itemno AS product_number, 
    smsrb_001 AS product_name,
    COUNT(DISTINCT smsrb_docno) AS return_count
FROM smsrb
WHERE smsrb_stus = 'S' 
  AND smsrb_loc <> 'AU'
GROUP BY smsrb_itemno, smsrb_001
ORDER BY return_count DESC;
```
> **業務規則說明：**
> - `smsrb_stus = 'S'`：單據狀態為「過帳」
> - `smsrb_loc <> 'AU'`：銷退入庫倉庫編號排除辦公倉

---

## 測試個案 03

### 測試問題 (Input)
> 二年內售價差異最大的產品？

### 正確回應 / 說明 (Ground Truth SQL)
```sql
SELECT TOP 1
    smdob.smdob_itemno AS product_number,
    MIN(smdob.smdob_001) AS product_name,
    MAX(CAST(CAST(smdob.smdob_005 AS FLOAT) / smdob.smdob_qty AS FLOAT)) -
    MIN(CAST(CAST(smdob.smdob_005 AS FLOAT) / smdob.smdob_qty AS FLOAT)) AS price_diff
FROM smdob
JOIN smdoa 
    ON smdob.smdob_ent = smdoa.smdoa_ent 
   AND smdob.smdob_site = smdoa.smdoa_site 
   AND smdob.smdob_docno = smdoa.smdoa_docno
WHERE smdoa.smdoa_pstdt BETWEEN '2023-08-20' AND '2025-08-20'
  AND smdob.smdob_qty IS NOT NULL
  AND smdob.smdob_qty != 0
  AND smdoa.smdoa_stus = 'S' 
  AND smdob.smdob_014 = '1' 
  AND smdob.smdob_loc <> 'AU'
GROUP BY smdob.smdob_itemno
HAVING COUNT(DISTINCT CAST(CAST(smdob.smdob_005 AS FLOAT) / smdob.smdob_qty AS FLOAT)) > 1
ORDER BY price_diff DESC;
```
> **業務規則說明：**
> - 單價計算：`smdob_005` (未稅金額) / `smdob_qty` (數量)
> - 篩選已過帳單據 (`smdoa_stus = 'S'`)，產品類型為一般品 (`smdob_014 = '1'`)

---

## 測試個案 04

### 測試問題 (Input)
> 哪種產品問題最少？

### 正確回應 / 說明 (Ground Truth SQL)
```sql
SELECT TOP 1
    smsrb_itemno AS product_number,
    MIN(smsrb_001) AS product_name,
    SUM(smsrb_qty) AS total_returned_quantity
FROM smsrb
WHERE smsrb_stus = 'S' 
  AND smsrb_loc <> 'AU'
GROUP BY smsrb_itemno
ORDER BY total_returned_quantity ASC;
```
> **業務規則說明：**
> - 「問題最少」以銷退數量最少為判斷依據
> - 排除未過帳單據與辦公倉 (`smsrb_stus = 'S' AND smsrb_loc <> 'AU'`)
> - 備註資訊可參考 `smsra_rmk`

---

## 測試個案 05

### 測試問題 (Input)
> 以整體的銷售狀況判斷主收入來源是哪個產品類別？

### 正確回應 / 說明 (Ground Truth SQL)
```sql
SELECT
    wmmta.wmmta_ud012 AS product_category,
    SUM(CAST(smdob.smdob_005 AS FLOAT)) AS total_income
FROM smdob
LEFT JOIN wmmta 
    ON wmmta.wmmta_ent = smdob.smdob_ent 
   AND wmmta.wmmta_site = smdob.smdob_site 
   AND wmmta.wmmta_itemno = smdob.smdob_itemno
WHERE ISNULL(wmmta.wmmta_ud012, '') <> ''
GROUP BY wmmta.wmmta_ud012
ORDER BY total_income DESC;
```
> **業務規則說明：**
> - 產品類別需關聯「料件主檔 (wmmta)」之 `wmmta_ud012` (產品別)
> - 代碼定義：R (液晶類)、A (冷氣類)、F (冰箱類)、W (洗衣機類)、O (其他家電類)

---

## 測試個案 06

### 測試問題 (Input)
> 哪種產品退貨數量最低（問題最少）？

### 正確回應 / 說明 (Ground Truth SQL)
```sql
SELECT TOP 1
    smsrb_itemno AS product_number,
    MIN(smsrb_001) AS product_name,
    SUM(smsrb_qty) AS total_returned_quantity
FROM smsrb
WHERE smsrb_stus = 'S' 
  AND smsrb_loc <> 'AU'
GROUP BY smsrb_itemno
ORDER BY total_returned_quantity ASC;
```
> **業務規則說明：**
> - 檢驗退貨單身檔 `smsrb` 中的已過帳項目

---

## 測試個案 07

### 測試問題 (Input)
> 2025年四月的銷售額比2025年三月成長多少？

### 正確回應 / 說明 (Ground Truth SQL)
```sql
-- 2025年3月銷售額
SELECT 
    SUM(T2.smdob_005) AS total_sales_amount_march
FROM smdoa AS T1
INNER JOIN smdob AS T2 
    ON T1.smdoa_ent = T2.smdob_ent 
   AND T1.smdoa_site = T2.smdob_site 
   AND T1.smdoa_docno = T2.smdob_docno
WHERE T1.smdoa_pstdt BETWEEN '2025-03-01' AND '2025-03-31' 
  AND T1.smdoa_stus = 'S' 
  AND T2.smdob_014 = '1' 
  AND T2.smdob_loc <> 'AU';

-- 2025年4月銷售額
SELECT 
    SUM(T2.smdob_005) AS total_sales_amount_april
FROM smdoa AS T1
INNER JOIN smdob AS T2 
    ON T1.smdoa_ent = T2.smdob_ent 
   AND T1.smdoa_site = T2.smdob_site 
   AND T1.smdoa_docno = T2.smdob_docno
WHERE T1.smdoa_pstdt >= '2025-04-01' 
  AND T1.smdoa_pstdt < '2025-05-01'  
  AND T1.smdoa_stus = 'S' 
  AND T2.smdob_014 = '1' 
  AND T2.smdob_loc <> 'AU';
```
> **業務規則說明：**
> - 依資料過帳日 `smdoa_pstdt` 劃分月份
> - 需符合已過帳 (`smdoa_stus = 'S'`)、一般品 (`smdob_014 = '1'`)、非辦公倉 (`smdob_loc <> 'AU'`)

---

## 測試個案 08

### 測試問題 (Input)
> 哪些產品的銷售額在2024年4月到5月比較下降最多？

### 正確回應 / 說明 (Ground Truth SQL)
```sql
WITH AprilSales AS (
    SELECT
        smdob.smdob_itemno AS product_number,
        MIN(smdob.smdob_001) AS product_name,
        SUM(smdob.smdob_005) AS total_sales
    FROM smdob
    JOIN smdoa 
        ON smdoa.smdoa_ent = smdob.smdob_ent 
       AND smdoa.smdoa_site = smdob.smdob_site 
       AND smdoa.smdoa_docno = smdob.smdob_docno
    WHERE FORMAT(smdoa.smdoa_pstdt, 'yyyy-MM') = '2024-04' 
      AND smdoa.smdoa_stus = 'S' 
      AND smdob.smdob_014 = '1' 
      AND smdob.smdob_loc <> 'AU'
    GROUP BY smdob.smdob_itemno
),
MaySales AS (
    SELECT
        smdob.smdob_itemno AS product_number,
        SUM(smdob.smdob_005) AS total_sales
    FROM smdob
    JOIN smdoa 
        ON smdoa.smdoa_ent = smdob.smdob_ent 
       AND smdoa.smdoa_site = smdob.smdob_site 
       AND smdoa.smdoa_docno = smdob.smdob_docno
    WHERE FORMAT(smdoa.smdoa_pstdt, 'yyyy-MM') = '2024-05' 
      AND smdoa.smdoa_stus = 'S' 
      AND smdob.smdob_014 = '1' 
      AND smdob.smdob_loc <> 'AU'
    GROUP BY smdob.smdob_itemno
)
SELECT TOP 5
    a.product_number,
    a.product_name,
    a.total_sales AS april_sales,
    ISNULL(m.total_sales, 0) AS may_sales,
    (a.total_sales - ISNULL(m.total_sales, 0)) AS sales_decrease
FROM AprilSales a
LEFT JOIN MaySales m ON a.product_number = m.product_number
WHERE (a.total_sales - ISNULL(m.total_sales, 0)) > 0
ORDER BY sales_decrease DESC;
```
> **業務規則說明：**
> - 比對兩月份的過帳銷售額差值，使用 LEFT JOIN 處理次月為 0 的狀況

---

## 測試個案 09

### 測試問題 (Input)
> 2025年表現最好的五名業務。

### 正確回應 / 說明 (Ground Truth SQL)
```sql
SELECT TOP 5
    MIN(smrta.smrta_002) AS 業務姓名,
    SUM(smdob.smdob_005) AS 總銷售金額
FROM smdob
JOIN smdoa
    ON smdoa.smdoa_ent = smdob.smdob_ent 
   AND smdoa.smdoa_site = smdob.smdob_site 
   AND smdob.smdob_docno = smdoa.smdoa_docno
JOIN smrta
    ON smrta.smrta_ent = smdob.smdob_ent 
   AND smrta.smrta_site = smdob.smdob_site 
   AND smdoa.smdoa_ud008 = smrta.smrta_001
WHERE YEAR(smdoa.smdoa_pstdt) = 2025 
  AND smdoa.smdoa_stus = 'S' 
  AND smdob.smdob_014 = '1' 
  AND smdob.smdob_loc <> 'AU'
  AND smrta.smrta_stus = 'Y' 
  AND smrta.smrta_002 <> ''
GROUP BY smrta.smrta_001
ORDER BY 總銷售金額 DESC;
```
> **業務規則說明：**
> - 關聯鍵：`smdoa_ud008` (單頭業務區別) = `smrta_001` (業務區別代號)
> - 需篩選有效業務 `smrta_stus = 'Y'` 與有效過帳單據

---
## 測試個案 10

### 測試問題 (Input)
> 找出 2025 年 5 月 19 日至 2025 年 8 月 19 日最熱門產品的品名？

### 正確回應 / 說明 (Ground Truth SQL)
```sql
SELECT TOP 10
    T2.smdob_itemno,
    T2.smdob_001,
    COUNT(DISTINCT T2.smdob_docno) AS total_sales_times
FROM smdoa AS T1
INNER JOIN smdob AS T2
    ON T1.smdoa_ent = T2.smdob_ent
   AND T1.smdoa_site = T2.smdob_site
   AND T1.smdoa_docno = T2.smdob_docno
WHERE T1.smdoa_pstdt >= '2025-05-19'
  AND T1.smdoa_pstdt < '2025-08-20'
  AND T1.smdoa_stus = 'S'
  AND T2.smdob_014 = '1'
  AND T2.smdob_loc <> 'AU'
GROUP BY T2.smdob_itemno, T2.smdob_001
ORDER BY total_sales_times DESC;
```
> **業務規則說明：**
> - 計算出貨次數（`COUNT(DISTINCT smdob_docno)`）取 TOP 10
