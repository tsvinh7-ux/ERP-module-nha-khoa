from odoo import fields, models

STT_PROVIDERS = [
    ('simulate', 'Giả lập (bản ghi mẫu – demo, không cần micro)'),
    ('browser', 'Trình duyệt (Web Speech API – miễn phí, cho demo / thí điểm)'),
    ('fpt', 'FPT.AI Speech to Text (API trong nước)'),
    ('viettel', 'Viettel AI Speech to Text (API trong nước)'),
]

# Địa chỉ mặc định – [CẦN XÁC MINH] theo tài liệu / hợp đồng của nhà cung cấp trước khi chạy thật
FPT_DEFAULT_ENDPOINT = 'https://api.fpt.ai/hmi/asr/general'
VIETTEL_DEFAULT_ENDPOINT = 'https://viettelai.vn/asr/recognize'


class ResCompany(models.Model):
    _inherit = 'res.company'

    dmag_stt_provider = fields.Selection(STT_PROVIDERS, string='Nhận dạng giọng nói (AI-01)', default='simulate',
                                         required=True)
    dmag_stt_fpt_endpoint = fields.Char('FPT.AI – địa chỉ API', default=FPT_DEFAULT_ENDPOINT)
    dmag_stt_fpt_api_key = fields.Char('FPT.AI – khóa API (api-key)', copy=False,
                                       groups='dmag_dental_base.group_dmag_director,base.group_system')
    dmag_stt_viettel_endpoint = fields.Char('Viettel AI – địa chỉ API', default=VIETTEL_DEFAULT_ENDPOINT)
    dmag_stt_viettel_token = fields.Char('Viettel AI – token', copy=False,
                                         groups='dmag_dental_base.group_dmag_director,base.group_system')
    dmag_stt_fpt_key_set = fields.Boolean('Đã có khóa FPT.AI', compute='_compute_dmag_stt_keys')
    dmag_stt_viettel_key_set = fields.Boolean('Đã có token Viettel AI', compute='_compute_dmag_stt_keys')

    def _compute_dmag_stt_keys(self):
        for company in self:
            company.dmag_stt_fpt_key_set = bool(company.sudo().dmag_stt_fpt_api_key)
            company.dmag_stt_viettel_key_set = bool(company.sudo().dmag_stt_viettel_token)
