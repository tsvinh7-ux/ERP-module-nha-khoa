from odoo import api, fields, models

ROUTES = [
    ('oral', 'Uống'),
    ('mouthwash', 'Súc miệng'),
    ('buccal', 'Ngậm'),
    ('topical', 'Bôi'),
    ('injection', 'Tiêm'),
    ('other', 'Khác'),
]
# Động từ dùng để soạn câu hướng dẫn sử dụng
ROUTE_VERBS = {
    'oral': 'Uống', 'mouthwash': 'Súc miệng', 'buccal': 'Ngậm',
    'topical': 'Bôi', 'injection': 'Tiêm', 'other': 'Dùng',
}
TIMINGS = [
    ('after_meal', 'sau ăn'),
    ('before_meal', 'trước ăn'),
    ('with_meal', 'trong bữa ăn'),
    ('bedtime', 'trước khi đi ngủ'),
    ('when_pain', 'khi đau'),
    ('after_brushing', 'sau khi chải răng'),
    ('none', '(không ràng buộc bữa ăn)'),
]


class DmagDrug(models.Model):
    """Danh mục thuốc dùng để kê đơn (không phải hàng tồn kho)."""
    _name = 'dmag.drug'
    _description = 'Thuốc (danh mục kê đơn)'
    _order = 'name'

    name = fields.Char('Tên thuốc (theo TT 26)', compute='_compute_name', store=True, index=True,
                       help='1 hoạt chất: "Tên chung + hàm lượng (Tên thương mại)"; '
                            'nhiều hoạt chất: "Tên thương mại + hàm lượng".')
    inn_name = fields.Char('Hoạt chất / tên chung (INN)', required=True)
    strength = fields.Char('Hàm lượng / nồng độ')
    dosage_form = fields.Char('Dạng bào chế', help='Viên nén, viên nang, gel, dung dịch súc miệng…')
    unit = fields.Char('Đơn vị tính', required=True, default='Viên')
    dose_unit = fields.Char('Đơn vị liều', help='Đơn vị ghi trong cách dùng (mỗi lần 1 viên, 10 ml…). '
                                                'Để trống = đơn vị tính.')
    route = fields.Selection(ROUTES, string='Đường dùng', required=True, default='oral')
    brand_name = fields.Char('Tên thương mại')
    registration_number = fields.Char('Số đăng ký')
    national_code = fields.Char('Mã thuốc Dược quốc gia')
    multi_ingredient = fields.Boolean('Thuốc nhiều hoạt chất')
    is_narcotic = fields.Boolean('Thuốc gây nghiện (N)')
    is_psychotropic = fields.Boolean('Thuốc hướng thần / tiền chất (H)')
    is_supplement = fields.Boolean(
        'Thực phẩm chức năng', help='Luật KCB 2023 Đ63 k2: không được kê thực phẩm chức năng trong đơn thuốc.')
    default_dose_per_time = fields.Float('Liều mỗi lần mặc định', default=1.0)
    default_times_per_day = fields.Integer('Số lần/ngày mặc định', default=2)
    default_days = fields.Integer('Số ngày mặc định', default=5)
    default_timing = fields.Selection(TIMINGS, string='Thời điểm dùng mặc định', default='after_meal')
    note = fields.Text('Ghi chú (chống chỉ định, tương tác…)')
    company_id = fields.Many2one('res.company', string='Phòng khám',
                                 help='Để trống = dùng chung cho mọi phòng khám.')
    active = fields.Boolean(default=True)

    @api.depends('inn_name', 'strength', 'brand_name', 'multi_ingredient')
    def _compute_name(self):
        for drug in self:
            drug.name = drug._tt26_name()

    def _tt26_name(self):
        """Tên thuốc ghi trên đơn theo TT 26/2025/TT-BYT."""
        self.ensure_one()
        strength = (self.strength or '').strip()
        inn = (self.inn_name or '').strip()
        brand = (self.brand_name or '').strip()
        if self.multi_ingredient and brand:
            return ' '.join(p for p in (brand, strength) if p)
        name = ' '.join(p for p in (inn, strength) if p)
        if brand and not self.multi_ingredient:
            name = f'{name} ({brand})'
        return name

    def _get_dose_unit(self):
        self.ensure_one()
        return self.dose_unit or (self.unit or '').lower()

    def _catalog_dict(self):
        self.ensure_one()
        return {
            'id': self.id, 'name': self.name, 'inn_name': self.inn_name, 'strength': self.strength or '',
            'brand_name': self.brand_name or '', 'dosage_form': self.dosage_form or '',
            'unit': self.unit, 'dose_unit': self._get_dose_unit(), 'route': self.route,
            'is_narcotic': self.is_narcotic, 'is_psychotropic': self.is_psychotropic,
            'is_supplement': self.is_supplement,
            'default_dose_per_time': self.default_dose_per_time,
            'default_times_per_day': self.default_times_per_day,
            'default_days': self.default_days, 'default_timing': self.default_timing or 'none',
        }
