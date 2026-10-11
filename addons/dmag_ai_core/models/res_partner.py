from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    dmag_ai_consent = fields.Boolean('Đồng ý hỗ trợ bằng AI',
                                     help='Bệnh nhân đồng ý dữ liệu (đã ẩn danh) được xử lý bằng công cụ AI để hỗ trợ '
                                          'bác sĩ / chăm sóc. Có thể rút lại bất cứ lúc nào (NĐ 13/2023).')
    dmag_ai_consent_date = fields.Datetime('Thời điểm đồng ý AI', readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('dmag_ai_consent'):
                vals.setdefault('dmag_ai_consent_date', fields.Datetime.now())
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('dmag_ai_consent'):
            vals.setdefault('dmag_ai_consent_date', fields.Datetime.now())
        return super().write(vals)
