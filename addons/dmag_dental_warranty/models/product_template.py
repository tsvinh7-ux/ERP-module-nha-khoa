from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    warranty_conditions = fields.Text(
        'Điều kiện bảo hành', translate=True,
        help='In trên thẻ bảo hành. Ví dụ: tái khám định kỳ 6 tháng; không áp dụng khi chấn thương, '
             'tự ý sửa chữa ở cơ sở khác, không vệ sinh đúng hướng dẫn.')
