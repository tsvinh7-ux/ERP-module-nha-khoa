#!/bin/bash
# Tắt bản demo (giữ nguyên dữ liệu).
cd "$(dirname "$0")" && docker compose stop
