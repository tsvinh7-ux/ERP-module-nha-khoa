from odoo import fields, models


class DmagAbbreviation(models.Model):
    """Danh sách ký hiệu, chữ viết tắt do cơ sở ban hành (TT 32/2023 Điều 52 khoản 2 điểm c).

    Chỉ dùng trong hồ sơ nội bộ; tài liệu giao người bệnh không được viết tắt.
    """
    _name = 'dmag.abbreviation'
    _description = 'Ký hiệu / chữ viết tắt được phép dùng trong hồ sơ bệnh án'
    _order = 'code'

    code = fields.Char('Ký hiệu / viết tắt', required=True)
    name = fields.Char('Nghĩa đầy đủ', required=True)
    note = fields.Char('Ghi chú')
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', string='Cơ sở ban hành',
                                 help='Để trống: áp dụng cho mọi cơ sở trong hệ thống.')
    issued_date = fields.Date('Ngày ban hành')
    decision_ref = fields.Char('Quyết định ban hành số')

    _sql_constraints = [
        ('code_company_uniq', 'unique(code, company_id)', 'Ký hiệu viết tắt đã tồn tại trong danh sách.'),
    ]
