from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

IDENTITY_TYPES = [
    ('cccd', 'Căn cước / Căn cước công dân (số định danh cá nhân)'),
    ('passport', 'Hộ chiếu'),
    ('birth_cert', 'Giấy khai sinh (trẻ em)'),
]
PATIENT_CATEGORIES = [
    ('bhyt', 'Bảo hiểm y tế'),
    ('fee', 'Thu phí'),
    ('exempt', 'Miễn'),
    ('other', 'Khác'),
]


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # Hành chính theo mẫu bệnh án ngoại trú (16/BV1)
    identity_type = fields.Selection(IDENTITY_TYPES, string='Loại giấy tờ định danh', default='cccd',
                                     help='TT 13/2025/TT-BYT: bệnh án điện tử gắn với số định danh cá nhân.')
    identity_exemption_reason = fields.Char(
        'Lý do chưa có số định danh',
        help='Chỉ điền khi người bệnh không cung cấp được số định danh (ví dụ: người nước ngoài chưa có hộ chiếu '
             'kèm theo, trẻ sơ sinh chưa đăng ký khai sinh, cấp cứu). Bắt buộc nếu ký bệnh án khi thiếu số định danh.')
    ethnicity = fields.Char('Dân tộc')
    nationality_id = fields.Many2one('res.country', string='Quốc tịch',
                                     default=lambda self: self.env.ref('base.vn', raise_if_not_found=False))
    workplace = fields.Char('Nơi làm việc')
    patient_category = fields.Selection(PATIENT_CATEGORIES, string='Đối tượng', default='fee')
    bhyt_number = fields.Char('Số thẻ bảo hiểm y tế')
    bhyt_valid_to = fields.Date('Thẻ bảo hiểm y tế có giá trị đến')
    emergency_contact_name = fields.Char('Người nhà báo tin – họ tên')
    emergency_contact_address = fields.Char('Người nhà báo tin – địa chỉ')
    emergency_contact_phone = fields.Char('Người nhà báo tin – điện thoại')
    family_history = fields.Text('Tiền sử bệnh gia đình')

    @api.constrains('patient_category', 'bhyt_number')
    def _check_bhyt(self):
        for partner in self:
            if partner.is_patient and partner.patient_category == 'bhyt' and not partner.bhyt_number:
                raise ValidationError(_('Đối tượng bảo hiểm y tế cần có số thẻ bảo hiểm y tế.'))

    def _emr_address(self):
        """Địa chỉ thường trú đầy đủ, không viết tắt."""
        self.ensure_one()
        parts = [self.street, self.street2, self.city, self.state_id.name,
                 self.country_id.name if self.country_id and self.country_id.code != 'VN' else False]
        return ', '.join(p for p in parts if p)

    def _emr_identity_label(self):
        self.ensure_one()
        return dict(IDENTITY_TYPES).get(self.identity_type or 'cccd')
