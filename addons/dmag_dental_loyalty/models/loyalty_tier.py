from odoo import api, fields, models


class DmagLoyaltyTier(models.Model):
    """Hạng thành viên – xét theo thực thu 12 tháng và / hoặc điểm gắn bó 12 tháng."""
    _name = 'dmag.loyalty.tier'
    _description = 'Hạng thành viên'
    _order = 'level, id'

    name = fields.Char('Hạng', required=True, translate=True)
    code = fields.Char('Mã')
    level = fields.Integer('Bậc', required=True, default=0, help='Bậc càng cao hạng càng cao.')
    company_id = fields.Many2one('res.company', string='Phòng khám',
                                 help='Để trống: áp dụng cho mọi phòng khám.')
    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id)
    min_paid_12m = fields.Monetary('Thực thu 12 tháng tối thiểu')
    min_engagement_points = fields.Integer(
        'Điểm gắn bó 12 tháng tối thiểu',
        help='Điểm từ tái khám đúng hẹn, giới thiệu thành công, khảo sát (không tính điểm thanh toán).')
    condition = fields.Selection([
        ('or', 'Đạt MỘT trong hai'),
        ('and', 'Đạt CẢ hai'),
    ], string='Điều kiện', default='or', required=True)
    benefits = fields.Text('Quyền lợi', translate=True)
    priority_booking = fields.Boolean('Ưu tiên giờ đẹp')
    free_xray = fields.Boolean('Miễn phí phim kiểm tra')
    extended_warranty_months = fields.Integer('Bảo hành mở rộng (tháng)')
    birthday_gift = fields.Char('Quà sinh nhật', translate=True)
    color = fields.Char('Màu', default='#178BEC')
    active = fields.Boolean(default=True)
    member_count = fields.Integer('Số thành viên', compute='_compute_member_count')

    def _compute_member_count(self):
        data = self.env['res.partner']._read_group(
            [('dmag_tier_id', 'in', self.ids)], ['dmag_tier_id'], ['__count'])
        counts = {tier.id: count for tier, count in data}
        for tier in self:
            tier.member_count = counts.get(tier.id, 0)

    def _is_reached(self, paid, engagement):
        self.ensure_one()
        paid_ok = paid >= (self.min_paid_12m or 0.0)
        eng_ok = engagement >= (self.min_engagement_points or 0)
        if not self.min_paid_12m and not self.min_engagement_points:
            return True
        if self.condition == 'and':
            return paid_ok and eng_ok
        # 'or': chỉ tính các tiêu chí có đặt ngưỡng
        checks = []
        if self.min_paid_12m:
            checks.append(paid_ok)
        if self.min_engagement_points:
            checks.append(eng_ok)
        return any(checks)

    @api.model
    def _get_tiers(self, company):
        return self.search([('company_id', 'in', (False, company.id))], order='level asc, id asc')

    @api.model
    def _find_tier(self, company, paid, engagement):
        """Hạng cao nhất đạt được."""
        reached = self.browse()
        for tier in self._get_tiers(company):
            if tier._is_reached(paid, engagement):
                reached = tier
        return reached

    def _tier_dict(self):
        self.ensure_one()
        return {
            'id': self.id, 'name': self.name, 'code': self.code or '', 'level': self.level,
            'color': self.color or '#178BEC', 'benefits': self.benefits or '',
            'priority_booking': self.priority_booking, 'free_xray': self.free_xray,
            'extended_warranty_months': self.extended_warranty_months,
            'birthday_gift': self.birthday_gift or '',
            'min_paid_12m': self.min_paid_12m, 'min_engagement_points': self.min_engagement_points,
            'condition': self.condition,
        }
