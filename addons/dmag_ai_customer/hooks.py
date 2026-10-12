def post_init_hook(env):
    """Nạp bộ kịch bản trả lời mẫu (NHÁP – Giám đốc duyệt trước khi trợ lý được tự gửi) cho mọi phòng khám."""
    Script = env['dmag.ai.reply.script']
    for company in env['res.company'].search([]):
        Script._load_samples(company)
    # Kho tri thức: nạp dữ liệu gốc Odoo (bảng giá, lịch làm việc, lịch trực, thông tin phòng khám) – chế độ mặc định
    # "chỉ trả lời từ dữ liệu đã nạp" dùng ngay được; cron hằng ngày / nút "Nạp lại dữ liệu" cập nhật tiếp.
    KB = env['dmag.ai.knowledge']
    for company in env['res.company'].search([]):
        KB.with_company(company).load_master_data(company)
