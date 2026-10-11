# DMAG Dental ERP – ảnh Odoo 17 cho bản demo, thêm thư viện "anthropic" để chạy AI thật (Claude API).
# Không có thư viện này, các tính năng AI vẫn chạy ở chế độ Giả lập.
FROM odoo:17.0
USER root
# Ảnh odoo:17.0 dùng Ubuntu 22.04 (Python 3.10, pip 22 – chưa có PEP 668 nên không cần cờ
# --break-system-packages). Nếu sau này ảnh gốc chuyển sang Debian 12 / pip ≥ 23 thì tự thêm cờ đó.
# Mạng công ty chặn / thay chứng chỉ HTTPS: build kèm --secret id=ca,src=<tệp CA.pem> (tùy chọn).
RUN --mount=type=secret,id=ca,required=false \
    if [ -s /run/secrets/ca ]; then export PIP_CERT=/run/secrets/ca; fi; \
    FLAGS=""; \
    if pip3 install --help | grep -q -- "--break-system-packages"; then FLAGS="--break-system-packages"; fi; \
    pip3 install --no-cache-dir $FLAGS "anthropic>=0.40" \
    && python3 -c "import anthropic; print('anthropic', anthropic.__version__)"
USER odoo
