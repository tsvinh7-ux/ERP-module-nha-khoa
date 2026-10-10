from odoo import fields, models


class DmagDentalPractitioner(models.Model):
    _inherit = 'dmag.dental.practitioner'

    rx_link_code = fields.Char('Mã liên thông bác sĩ', tracking=True,
                               help='Mã liên thông đơn thuốc quốc gia do Sở Y tế cấp cho người kê đơn.')
    rx_link_password = fields.Char('Mật khẩu liên thông bác sĩ', copy=False,
                                   groups='dmag_dental_base.group_dmag_director')
    rx_token = fields.Char('Token liên thông', copy=False, groups='base.group_system')
    rx_token_expiry = fields.Datetime('Token hết hạn', copy=False, groups='base.group_system')
    rx_controlled_allowed = fields.Boolean(
        'Được kê đơn thuốc gây nghiện / hướng thần', tracking=True,
        help='Chỉ có hiệu lực khi phòng khám bật "Cho phép kê đơn N, H".')
