from odoo import api, fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    dental_result_condition_id = fields.Many2one(
        'dmag.dental.condition', string='Tình trạng sau điều trị',
        help='Ghi lên sơ đồ răng khi thủ thuật hoàn tất (ví dụ Trám → "Đã trám", Implant → "Implant").')

    @api.onchange('is_dental_service')
    def _onchange_is_dental_service(self):
        if self.is_dental_service:
            self.detailed_type = 'service'
            # Thu theo tiến độ: chỉ xuất hóa đơn phần đã làm
            self.invoice_policy = 'delivery'
            # Dịch vụ khám chữa bệnh không chịu thuế GTGT
            self.taxes_id = False

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if self.env.context.get('default_is_dental_service') and 'taxes_id' in fields_list:
            res['taxes_id'] = [(6, 0, [])]
        return res

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('is_dental_service'):
                vals.setdefault('invoice_policy', 'delivery')
        return super().create(vals_list)
