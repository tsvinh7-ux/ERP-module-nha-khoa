@echo off
REM Xoa sach ban demo roi tao lai tu dau.
cd /d "%~dp0"
docker compose down -v
call start.bat
