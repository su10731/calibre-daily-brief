@echo off
rem ============================================================
rem  4-科普拓展-2篇.bat
rem  内容：Quanta / MIT TR / Physics World / New Scientist
rem 同一天可以反复双击：文件名带到秒的时间戳，不会互相覆盖；
rem 且上一批选过的文章已记进 state\seen.json，下一次会自动换新的文章。
rem ============================================================
chcp 65001 >nul
cd /d "%~dp0"
set "PY=python"
where python >nul 2>nul || set "PY=py -3"
%PY% scripts\build_brief.py --book popular --open
if errorlevel 1 (
    echo.
    echo 没成功。对照上面最后几行日志：
    echo   - "没找到 ebook-convert"  →  装 Calibre：https://calibre-ebook.com/download_windows
    echo   - "一篇都没选到"  →  源都没连上（这一本要不要代理？）
    echo   - 个别源失败不影响出书，日志会列出失败的是哪几个
)
echo.
pause
