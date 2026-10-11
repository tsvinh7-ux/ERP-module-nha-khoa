#!/bin/bash
# Khởi động bản demo DMAG Dental ERP trên máy (cần Docker Desktop / Docker Engine).
cd "$(dirname "$0")"
docker compose up -d || exit 1
PORT="${DMAG_PORT:-8069}"
echo "Đang khởi động… Lần đầu mất khoảng 3–5 phút để sinh dữ liệu mẫu."
echo "Theo dõi: docker compose logs -f odoo"
until curl -s -o /dev/null "http://localhost:$PORT/web/login"; do sleep 5; printf "."; done
echo
echo "Sẵn sàng: http://localhost:$PORT   (đăng nhập: giamdoc.demo / demo — xem README.md để biết các tài khoản khác)"
