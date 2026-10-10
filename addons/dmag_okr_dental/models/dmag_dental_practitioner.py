from odoo import fields, models


class DmagDentalPractitioner(models.Model):
    _inherit = 'dmag.dental.practitioner'

    dmag_is_associate = fields.Boolean(
        'Bác sĩ phụ / associate',
        help='Dùng cho KR "% ca do bác sĩ phụ thực hiện" (giảm tải bác sĩ chính / chủ phòng khám).')
