#!/bin/bash
# Xóa sạch bản demo (CSDL + tệp) rồi tạo lại từ đầu với dữ liệu mẫu mới theo ngày hôm nay.
cd "$(dirname "$0")"
docker compose down -v && ./start.sh
