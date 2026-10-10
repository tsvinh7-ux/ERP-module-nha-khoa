from odoo import fields, models


class DmagDentalChair(models.Model):
    _name = 'dmag.dental.chair'
    _description = 'Ghế nha'
    _order = 'company_id, sequence, name'

    name = fields.Char('Tên ghế', required=True)
    code = fields.Char('Mã ghế')
    sequence = fields.Integer(default=10)
    room = fields.Char('Phòng / khu vực')
    company_id = fields.Many2one('res.company', string='Phòng khám', required=True,
                                 default=lambda self: self.env.company)
    color = fields.Integer('Màu')
    note = fields.Text('Ghi chú (thiết bị gắn kèm…)')
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('name_company_uniq', 'unique(name, company_id)', 'Tên ghế đã tồn tại trong phòng khám này.'),
    ]
