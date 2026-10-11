@echo off
REM Khởi động bản demo DMAG Dental ERP trên Windows (cần Docker Desktop đang chạy).
cd /d "%~dp0"
docker compose up -d --build
echo Dang khoi dong... Lan dau mat khoang 3-5 phut de sinh du lieu mau.
echo Theo doi: docker compose logs -f odoo
:wait
timeout /t 5 /nobreak >nul
curl -s -o nul http://localhost:8069/web/login || goto wait
echo San sang: http://localhost:8069  (dang nhap: giamdoc.demo / demo)
start http://localhost:8069
