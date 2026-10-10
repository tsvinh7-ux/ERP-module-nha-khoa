from odoo import api, fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    is_dental_service = fields.Boolean('Dịch vụ nha khoa', index=True)
    dental_category = fields.Selection([
        ('exam', 'Khám & chẩn đoán'),
        ('imaging', 'Chẩn đoán hình ảnh'),
        ('hygiene', 'Dự phòng / vệ sinh'),
        ('restorative', 'Điều trị bảo tồn'),
        ('endo', 'Nội nha'),
        ('surgery', 'Phẫu thuật / nhổ răng'),
        ('implant', 'Implant'),
        ('prosthodontic', 'Phục hình'),
        ('orthodontic', 'Chỉnh nha'),
        ('cosmetic', 'Thẩm mỹ'),
        ('pediatric', 'Nha khoa trẻ em'),
        ('other', 'Khác'),
    ], string='Nhóm dịch vụ nha khoa')
    dental_duration = fields.Integer('Thời lượng chuẩn (phút)', default=30)
    dental_complexity = fields.Selection([
        ('light', 'Nhẹ – xen ca được'),
        ('normal', 'Thường'),
        ('heavy', 'Nặng – không xếp chồng'),
    ], string='Độ nặng ca', default='normal',
        help='Dùng cho luật xếp lịch: không đặt 2 ca "Nặng" của cùng bác sĩ trùng khung giờ, '
             'ưu tiên xen ca "Nhẹ" để lấp ghế.')
    dental_requires_tooth = fields.Boolean('Bắt buộc chọn răng', default=True)
    practice_scope_id = fields.Many2one('dmag.practice.scope', string='Phạm vi hành nghề yêu cầu')
    min_clinical_level_id = fields.Many2one('dmag.clinical.level', string='Bậc lâm sàng tối thiểu')
    requires_second_opinion = fields.Boolean(
        'Cần bác sĩ thứ hai duyệt',
        help='Cầu chì y đức: kế hoạch có dịch vụ này (bọc sứ, mài cùi thẩm mỹ…) phải có '
             'bác sĩ thứ hai duyệt chỉ định trước khi bệnh nhân ký đồng ý.')
    warranty_months = fields.Integer('Bảo hành (tháng)')
    recall_months = fields.Integer('Nhắc tái khám sau (tháng)',
                                   help='Ví dụ cạo vôi: 6 tháng. Để 0 nếu không nhắc.')
    aftercare_note = fields.Html('Lời dặn sau thủ thuật', translate=True,
                                 help='Gửi cho bệnh nhân sau khi hoàn tất thủ thuật.')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('is_dental_service'):
                vals.setdefault('detailed_type', 'service')
        return super().create(vals_list)
