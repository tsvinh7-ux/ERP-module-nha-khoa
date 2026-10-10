from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    dmag_max_discount = fields.Float(
        'Giảm giá tối đa nhân viên được áp (%)', default=10.0,
        help='Bác sĩ / tư vấn / lễ tân chỉ được giảm đến mức này. Vượt mức cần Giám đốc / Quản lý cấp cao.')
    dmag_facility_code = fields.Char(
        'Mã cơ sở KCB',
        help='Mã cơ sở khám bệnh, chữa bệnh (mã BHYT 5 ký tự) – dùng sinh mã đơn thuốc liên thông.')
    dmag_license_number = fields.Char('Số giấy phép hoạt động KCB')
    dmag_license_date = fields.Date('Ngày cấp giấy phép hoạt động')
    dmag_professional_director = fields.Char('Người chịu trách nhiệm chuyên môn kỹ thuật')
