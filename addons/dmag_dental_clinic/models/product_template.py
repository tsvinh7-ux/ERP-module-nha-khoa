from odoo import _, api, fields, models

# Căn cứ: Điều 5 Luật Thuế GTGT số 48/2024/QH15 (hiệu lực 01/07/2025) – dịch vụ y tế (khám bệnh,
# chữa bệnh, phòng bệnh…) thuộc đối tượng KHÔNG CHỊU THUẾ GTGT; dịch vụ thẩm mỹ không nhằm mục đích
# chữa bệnh và hàng hóa bán lẻ chịu thuế theo thuế suất thông thường.
MEDICAL_CATEGORIES = {'exam', 'imaging', 'hygiene', 'restorative', 'endo', 'surgery', 'implant',
                      'prosthodontic', 'orthodontic', 'pediatric', 'other'}


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    dental_result_condition_id = fields.Many2one(
        'dmag.dental.condition', string='Tình trạng sau điều trị',
        help='Ghi lên sơ đồ răng khi thủ thuật hoàn tất (ví dụ Trám → "Đã trám", Implant → "Implant").')
    dental_vat_regime = fields.Selection([
        ('exempt', 'Không chịu thuế GTGT – dịch vụ khám chữa bệnh'),
        ('taxable', 'Chịu thuế GTGT – thẩm mỹ thuần túy / hàng hóa'),
    ], string='Chế độ thuế GTGT', compute='_compute_dental_vat_regime', store=True, readonly=False,
        help='Điều 5 Luật Thuế GTGT 48/2024/QH15: dịch vụ y tế không chịu thuế. Dịch vụ chỉ nhằm làm đẹp '
             '(không có chỉ định điều trị) chịu thuế theo thuế suất thông thường. Kế toán xác nhận cho từng dịch vụ.')

    @api.depends('is_dental_service', 'dental_category')
    def _compute_dental_vat_regime(self):
        for tmpl in self:
            if not tmpl.is_dental_service:
                tmpl.dental_vat_regime = False
            elif not tmpl.dental_vat_regime:
                tmpl.dental_vat_regime = 'taxable' if tmpl.dental_category == 'cosmetic' else 'exempt'

    @api.onchange('is_dental_service')
    def _onchange_is_dental_service(self):
        if self.is_dental_service:
            self.detailed_type = 'service'
            # Thu theo tiến độ: chỉ xuất hóa đơn phần đã làm
            self.invoice_policy = 'delivery'

    @api.onchange('dental_vat_regime')
    def _onchange_dental_vat_regime(self):
        if self.dental_vat_regime == 'exempt':
            self.taxes_id = self.env['account.tax']._dmag_exempt_tax(self.env.company)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('is_dental_service'):
                vals.setdefault('invoice_policy', 'delivery')
        templates = super().create(vals_list)
        templates.filtered(lambda t: t.dental_vat_regime == 'exempt')._dmag_apply_exempt_tax()
        return templates

    def write(self, vals):
        res = super().write(vals)
        if {'dental_vat_regime', 'is_dental_service', 'dental_category'} & set(vals) and 'taxes_id' not in vals:
            self.filtered(lambda t: t.dental_vat_regime == 'exempt')._dmag_apply_exempt_tax()
        return res

    @api.model
    def _dmag_apply_exempt_tax_all(self):
        """Khi cài / nâng cấp: gán thuế KCT cho mọi dịch vụ nha khoa thuộc diện không chịu thuế."""
        self.search([('is_dental_service', '=', True), ('dental_vat_regime', '=', 'exempt')])._dmag_apply_exempt_tax()

    def _dmag_apply_exempt_tax(self):
        for tmpl in self:
            company = tmpl.company_id or self.env.company
            tax = self.env['account.tax']._dmag_exempt_tax(company)
            other = tmpl.taxes_id.filtered(lambda t: t.company_id != company)
            super(ProductTemplate, tmpl).write({'taxes_id': [(6, 0, (other | tax).ids)]})


class AccountTax(models.Model):
    _inherit = 'account.tax'

    @api.model
    def _dmag_exempt_tax(self, company):
        """Thuế "Không chịu thuế GTGT" (KCT) – hóa đơn điện tử ghi thuế suất KCT."""
        tax = self.sudo().search([
            ('company_id', '=', company.id), ('type_tax_use', '=', 'sale'),
            ('amount', '=', 0), ('description', '=', 'KCT'),
        ], limit=1)
        if not tax:
            tax_group = self._dmag_exempt_tax_group(company)
            tax = self.sudo().create({
                'tax_group_id': tax_group.id,
                'name': _('Không chịu thuế GTGT'),
                'description': 'KCT',
                'invoice_label': 'KCT',
                'amount_type': 'percent',
                'amount': 0.0,
                'type_tax_use': 'sale',
                'company_id': company.id,
            })
        return tax

    @api.model
    def _dmag_exempt_tax_group(self, company):
        """Nhóm thuế cho KCT. Công ty chưa nạp hệ thống tài khoản (cài mới) thì chưa có nhóm nào → tạo riêng."""
        Group = self.env['account.tax.group'].sudo()
        group = Group.search([('company_id', '=', company.id), ('name', '=', 'KCT')], limit=1)
        if not group:
            group = Group.create({
                'name': 'KCT',
                'company_id': company.id,
                'country_id': company.account_fiscal_country_id.id or company.country_id.id,
            })
        return group
