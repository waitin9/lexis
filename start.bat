@echo off
chcp 65001 >nul
title Lexis 詞彙學習系統 - 一鍵啟動器 v2

set PYTHON_CMD=python
set PIP_CMD=pip

echo ====================================================
echo  正在檢查系統 Python 環境...
echo ====================================================
echo.

:: 1. 偵測系統全域 python
%PYTHON_CMD% --version >nul 2>&1
if %errorlevel% equ 0 goto check_requirements

:: 2. 偵測當前使用者 AppData 下的預設 python3.10 安裝路徑 (繞過環境變數未即時更新問題)
if exist "%USERPROFILE%\AppData\Local\Programs\Python\Python310\python.exe" (
    set PYTHON_CMD="%USERPROFILE%\AppData\Local\Programs\Python\Python310\python.exe"
    set PIP_CMD="%USERPROFILE%\AppData\Local\Programs\Python\Python310\Scripts\pip.exe"
    goto check_requirements
)

:: 3. 若皆找不到，開始自動下載並進行免管理員權限靜默安裝
echo ====================================================
echo  [提示] 未偵測到 Python 環境！
echo  正在為您自動下載並安裝 Python 3.10...
echo  (此過程需要網際網路連線，且無需系統管理員權限)
echo ====================================================
echo.

:: 使用 PowerShell 下載 Python 3.10 64位元 Installer
powershell -Command "echo '正在從 Python 官網下載安裝檔...'; [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.10.11/python-3.10.11-amd64.exe' -OutFile 'python_installer.exe'"

if not exist python_installer.exe (
    echo.
    echo [錯誤] 下載 Python 安裝包失敗，請確認您的網路連線是否正常。
    pause
    exit /b
)

echo 下載完成！正在進行免管理員權限的靜默安裝，請稍候...
:: InstallAllUsers=0 代表僅安裝給目前使用者，不需要管理員密碼；PrependPath=1 會自動寫入環境變數
start /wait python_installer.exe /quiet InstallAllUsers=0 PrependPath=1 Include_test=0
del python_installer.exe
echo Python 安裝成功！
echo.

:: 再次設定安裝後的實體路徑
if exist "%USERPROFILE%\AppData\Local\Programs\Python\Python310\python.exe" (
    set PYTHON_CMD="%USERPROFILE%\AppData\Local\Programs\Python\Python310\python.exe"
    set PIP_CMD="%USERPROFILE%\AppData\Local\Programs\Python\Python310\Scripts\pip.exe"
    goto check_requirements
)

echo [警告] 找不到安裝後的 python.exe。請嘗試重新執行此 start.bat。
pause
exit /b

:check_requirements
echo ====================================================
echo  正在檢查並安裝專案依賴套件 (Requirements)...
echo ====================================================
%PIP_CMD% install -r requirements.txt
if %errorlevel% neq 0 (
    echo.
    echo [警告] 安裝依賴套件時可能出現些許問題，但我們將嘗試繼續啟動服務...
)

echo.
echo ====================================================
echo  正在啟動 Lexis 詞彙學習系統服務...
echo  啟動後將會自動在瀏覽器中開啟系統網頁。
echo ====================================================
echo.

:: 延遲 2 秒後在瀏覽器開啟首頁，確保 Django 服務有足夠時間啟動
start "" http://127.0.0.1:8000

:: 啟動 Django 伺服器
%PYTHON_CMD% manage.py runserver

pause
