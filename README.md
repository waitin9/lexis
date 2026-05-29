# Lexis - 間隔重複單字學習系統

Lexis 是一個極簡且具備 Glassmorphism 設計的單字學習工具，內建間隔重複（Spaced Repetition）邏輯。

## 一鍵開啟 / 部署 (One-Click Open)

### 雲端開發環境
點擊下方按鈕即可在 GitHub Codespaces 中一鍵開啟並運行本專案：

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/waitin9/lexis)

### 本地端一鍵啟動
如果你已經將專案下載到 Windows 本地端，只需雙擊專案目錄下的 **`run.bat`** 即可一鍵啟動 Django 伺服器並自動開啟瀏覽器。

---

## 手動安裝與執行

1. 安裝所需套件：
   ```bash
   pip install -r requirements.txt
   ```
2. 進行資料庫遷移：
   ```bash
   python manage.py migrate
   ```
3. 啟動伺服器：
   ```bash
   python manage.py runserver
   ```
4. 開啟瀏覽器並前往 `http://127.0.0.1:8000/`
