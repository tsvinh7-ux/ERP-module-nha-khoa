def post_init_hook(env):
    """Nạp bộ kịch bản trả lời mẫu (NHÁP – Giám đốc duyệt trước khi trợ lý được tự gửi) cho mọi phòng khám."""
    Script = env['dmag.ai.reply.script']
    for company in env['res.company'].search([]):
        Script._load_samples(company)
