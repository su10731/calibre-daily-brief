@echo off
rem ==============================================================
rem  每日科学简报 —— 本地手动出书
rem  双击这里生成一本 out\每日科学简报-<日期>.epub
rem  想每天自动跑：见 README「让它每天自动跑」一节（schtasks 一行命令）
rem ==============================================================
chcp 65001 >nul
setlocal
cd /d "%~dp0"

rem ---- 可选：想抓海外源（Quanta/Nature/Guardian 等）就放开下面两行，端口改成你自己的代理端口 ----
rem set HTTP_PROXY=http://127.0.0.1:7890
rem set HTTPS_PROXY=http://127.0.0.1:7890

set "PY=python"
where python >nul 2>nul || set "PY=py -3"

echo 正在抓源、选材、排版……
%PY% scripts\build_brief.py --open
if errorlevel 1 (
    echo.
    echo 没成功。按上面最后几行日志对号入座：
    echo   - "没找到 ebook-convert"  → 装 Calibre：https://calibre-ebook.com/download_windows
    echo   - "一篇都没选到"          → 网络问题，当前网络一个源都没连上（或全部超出新鲜度窗口）
    echo   - 个别源失败不影响出书，日志里会列出失败的是哪几个
)
echo.
pause
