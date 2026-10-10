from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

ROLES = [
    ('doctor', 'Bác sĩ (thủ thuật phí)'),
    ('assistant', 'Phụ tá / Điều dưỡng'),
    ('consultant', 'Tư vấn viên'),
    ('receptionist', 'Lễ tân'),
    ('telesale', 'Telesale'),
    ('referrer', 'Người giới thiệu'),
]
DENTAL_CATEGORIES = [
    ('exam', 'Khám & chẩn đoán'), ('imaging', 'Chẩn đoán hình ảnh'), ('hygiene', 'Dự phòng / vệ sinh'),
    ('restorative', 'Điều trị bảo tồn'), ('endo', 'Nội nha'), ('surgery', 'Phẫu thuật / nhổ răng'),
    ('implant', 'Implant'), ('prosthodontic', 'Phục hình'), ('orthodontic', 'Chỉnh nha'),
    ('cosmetic', 'Thẩm mỹ'), ('pediatric', 'Nha khoa trẻ em'), ('other', 'Khác'),
]
# Độ ưu tiên khi nhiều quy tắc cùng khớp: cụ thể hơn thắng
SCOPE_PRIORITY = {'product': 0, 'product_category': 1, 'dental_category': 2, 'all': 3}


class DmagCommissionRule(models.Model):
    _name = 'dmag.commission.rule'
    _description = 'Quy tắc thủ thuật phí / hoa hồng'
    _inherit = ['mail.thread']
    _order = 'role, sequence, id'

    name = fields.Char('Tên quy tắc', required=True, tracking=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', string='Phòng khám', required=True,
                                 default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    role = fields.Selection(ROLES, string='Vai trò hưởng', required=True, tracking=True)
    scope = fields.Selection([
        ('all', 'Mọi dịch vụ'),
        ('dental_category', 'Theo nhóm dịch vụ nha khoa'),
        ('product_category', 'Theo nhóm sản phẩm'),
        ('product', 'Theo dịch vụ / sản phẩm cụ thể'),
    ], string='Phạm vi', default='all', required=True, tracking=True)
    dental_category = fields.Selection(DENTAL_CATEGORIES, string='Nhóm dịch vụ nha khoa')
    product_categ_id = fields.Many2one('product.category', string='Nhóm sản phẩm')
    product_ids = fields.Many2many('product.product', string='Dịch vụ / sản phẩm')
    basis = fields.Selection([
        ('collected', '% trên tiền thực thu (gồm thuế)'),
        ('revenue', '% trên doanh thu (chưa thuế) đã thu'),
        ('fixed', 'Cố định mỗi thủ thuật'),
        ('tiered', 'Lũy tiến theo thực thu tháng'),
    ], string='Cách tính', default='collected', required=True, tracking=True,
        help='Mọi cách tính đều chỉ phát sinh trên phần tiền đã thu thực tế: thu một phần → hưởng '
             'tương ứng; hóa đơn bị đảo → tự sinh dòng âm.')
    rate = fields.Float('Tỷ lệ (%)', digits=(16, 2), tracking=True)
    fixed_amount = fields.Monetary('Số tiền / thủ thuật', tracking=True)
    tier_ids = fields.One2many('dmag.commission.tier', 'rule_id', string='Bậc lũy tiến')
    date_from = fields.Date('Hiệu lực từ')
    date_to = fields.Date('Hiệu lực đến')
    note = fields.Text('Ghi chú')

    @api.constrains('rate', 'fixed_amount', 'scope', 'dental_category', 'product_categ_id', 'product_ids')
    def _check_rule(self):
        for rule in self:
            if rule.rate < 0 or rule.rate > 100 or rule.fixed_amount < 0:
                raise ValidationError(_('Tỷ lệ phải trong khoảng 0–100%% và số tiền không âm (%s).', rule.name))
            if rule.scope == 'dental_category' and not rule.dental_category:
                raise ValidationError(_('Chọn nhóm dịch vụ nha khoa cho quy tắc %s.', rule.name))
            if rule.scope == 'product_category' and not rule.product_categ_id:
                raise ValidationError(_('Chọn nhóm sản phẩm cho quy tắc %s.', rule.name))
            if rule.scope == 'product' and not rule.product_ids:
                raise ValidationError(_('Chọn dịch vụ cho quy tắc %s.', rule.name))

    def _matches(self, product, date):
        self.ensure_one()
        if self.date_from and date < self.date_from or self.date_to and date > self.date_to:
            return False
        if self.scope == 'all':
            return True
        if self.scope == 'dental_category':
            return product.dental_category == self.dental_category
        if self.scope == 'product_category':
            categ = product.categ_id
            return bool(categ) and (categ == self.product_categ_id or categ.parent_path.startswith(
                self.product_categ_id.parent_path))
        return product in self.product_ids

    @api.model
    def _find_rule(self, company, role, product, date):
        rules = self.sudo().search([('company_id', '=', company.id), ('role', '=', role)])
        rules = rules.filtered(lambda r: r._matches(product, date))
        if not rules:
            return self.browse()
        return rules.sorted(lambda r: (SCOPE_PRIORITY[r.scope], r.sequence, r.id))[0]

    def _tier_rate(self, month_base):
        self.ensure_one()
        rate = self.rate
        for tier in self.tier_ids.sorted('threshold'):
            if month_base >= tier.threshold:
                rate = tier.rate
        return rate


class DmagCommissionTier(models.Model):
    _name = 'dmag.commission.tier'
    _description = 'Bậc lũy tiến hoa hồng'
    _order = 'threshold'

    rule_id = fields.Many2one('dmag.commission.rule', required=True, ondelete='cascade')
    currency_id = fields.Many2one(related='rule_id.currency_id')
    threshold = fields.Monetary('Thực thu tháng từ', required=True)
    rate = fields.Float('Tỷ lệ (%)', required=True, digits=(16, 2))
