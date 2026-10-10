from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.osv import expression

CATEGORIES = [
    ('facility', 'Giấy phép cơ sở'),
    ('personnel', 'Nhân sự hành nghề'),
    ('radiation', 'An toàn bức xạ'),
    ('equipment', 'Kiểm định thiết bị'),
    ('infection', 'Kiểm soát nhiễm khuẩn'),
    ('waste', 'Chất thải y tế / môi trường'),
    ('fire', 'Phòng cháy chữa cháy'),
    ('business', 'Pháp lý doanh nghiệp'),
    ('premises', 'Mặt bằng'),
    ('other', 'Khác'),
]
STATES = [('valid', 'Còn hiệu lực'), ('expiring', 'Sắp hết hạn'), ('expired', 'Hết hạn')]


class DmagComplianceDocType(models.Model):
    _name = 'dmag.compliance.doc.type'
    _description = 'Loại hồ sơ pháp chế'
    _order = 'sequence, name'

    name = fields.Char('Loại hồ sơ', required=True, translate=True)
    code = fields.Char('Mã')
    sequence = fields.Integer(default=10)
    category = fields.Selection(CATEGORIES, string='Nhóm', required=True, default='other')
    alert_days = fields.Integer('Cảnh báo trước (ngày)', default=60,
                                help='Hồ sơ chuyển "Sắp hết hạn" và tạo việc nhắc trước ngày hết hạn số ngày này.')
    validity_months = fields.Integer('Thời hạn thường gặp (tháng)',
                                     help='Gợi ý ngày hết hạn khi nhập ngày cấp. 0 = không thời hạn.')
    is_mandatory = fields.Boolean('Bắt buộc cho thanh tra',
                                  help='Thiếu hồ sơ loại này → mục đỏ trong "Sẵn sàng thanh tra".')
    per_practitioner = fields.Boolean('Theo từng người hành nghề')
    per_equipment = fields.Boolean('Theo từng thiết bị')
    equipment_categories = fields.Char('Áp dụng cho loại thiết bị',
                                       help='Mã loại thiết bị, cách nhau dấu phẩy (xray,cbct). Thiết bị thuộc loại '
                                            'này mà chưa có hồ sơ còn hiệu lực → thiếu hồ sơ.')
    legal_basis = fields.Text('Căn cứ pháp lý', translate=True)
    active = fields.Boolean(default=True)


class DmagComplianceAlertMixin(models.AbstractModel):
    _name = 'dmag.compliance.alert.mixin'
    _description = 'Nhắc việc pháp chế'

    def _dmag_schedule_alert(self, summary, deadline, user):
        """Tạo một việc "Cần làm" (không tạo trùng khi việc cũ chưa xong)."""
        self.ensure_one()
        todo = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
        if not todo or self.activity_ids.filtered(lambda a: a.activity_type_id == todo):
            return False
        return self.activity_schedule(act_type_xmlid='mail.mail_activity_data_todo', date_deadline=deadline,
                                      summary=summary, user_id=user.id)


class DmagComplianceDoc(models.Model):
    """Hồ sơ pháp chế của phòng khám: giấy phép, chứng chỉ, kiểm định, hợp đồng bắt buộc."""
    _name = 'dmag.compliance.doc'
    _description = 'Hồ sơ pháp chế'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'dmag.compliance.alert.mixin']
    _order = 'expiry_date, id'

    name = fields.Char('Tên hồ sơ', required=True, tracking=True)
    type_id = fields.Many2one('dmag.compliance.doc.type', string='Loại hồ sơ', required=True, index=True,
                              tracking=True)
    category = fields.Selection(related='type_id.category', store=True, string='Nhóm')
    legal_basis = fields.Text(related='type_id.legal_basis', string='Căn cứ pháp lý')
    company_id = fields.Many2one('res.company', string='Phòng khám', required=True, index=True,
                                 default=lambda self: self.env.company)
    number = fields.Char('Số hiệu', tracking=True)
    issuer = fields.Char('Cơ quan / đơn vị cấp')
    partner_id = fields.Many2one('res.partner', string='Đối tác',
                                 help='Đơn vị xử lý chất thải, kiểm định, cho thuê mặt bằng…')
    practitioner_id = fields.Many2one('dmag.dental.practitioner', string='Người hành nghề / nhân viên')
    equipment_id = fields.Many2one('dmag.equipment', string='Thiết bị')
    issue_date = fields.Date('Ngày cấp / ký', tracking=True)
    no_expiry = fields.Boolean('Không thời hạn')
    expiry_date = fields.Date('Ngày hết hạn', tracking=True, index=True)
    alert_days = fields.Integer('Cảnh báo trước (ngày)', compute='_compute_alert_days', store=True, readonly=False)
    alert_date = fields.Date('Ngày bắt đầu cảnh báo', compute='_compute_alert_date', store=True, index=True)
    days_left = fields.Integer('Còn (ngày)', compute='_compute_status')
    state = fields.Selection(STATES, string='Tình trạng', compute='_compute_status', search='_search_state')
    responsible_id = fields.Many2one('res.users', string='Người phụ trách', default=lambda self: self.env.user,
                                     tracking=True)
    attachment_ids = fields.Many2many('ir.attachment', string='Bản scan')
    renewed_from_id = fields.Many2one('dmag.compliance.doc', string='Gia hạn từ', readonly=True, copy=False)
    note = fields.Text('Ghi chú')
    active = fields.Boolean(default=True)

    @api.depends('type_id')
    def _compute_alert_days(self):
        for doc in self:
            doc.alert_days = doc.type_id.alert_days or doc.alert_days or 60

    @api.depends('expiry_date', 'alert_days', 'no_expiry')
    def _compute_alert_date(self):
        for doc in self:
            doc.alert_date = (doc.expiry_date - timedelta(days=doc.alert_days or 0)
                              if doc.expiry_date and not doc.no_expiry else False)

    @api.depends('expiry_date', 'alert_date', 'no_expiry')
    def _compute_status(self):
        today = fields.Date.context_today(self)
        for doc in self:
            if doc.no_expiry or not doc.expiry_date:
                doc.state = 'valid' if doc.no_expiry else 'expired'
                doc.days_left = 0
                continue
            doc.days_left = (doc.expiry_date - today).days
            if doc.expiry_date < today:
                doc.state = 'expired'
            elif doc.alert_date and doc.alert_date <= today:
                doc.state = 'expiring'
            else:
                doc.state = 'valid'

    @api.model
    def _state_domain(self, state):
        today = fields.Date.context_today(self)
        if state == 'expired':
            return [('no_expiry', '=', False), '|', ('expiry_date', '=', False), ('expiry_date', '<', today)]
        if state == 'expiring':
            return [('no_expiry', '=', False), ('expiry_date', '>=', today), ('alert_date', '<=', today)]
        return ['|', ('no_expiry', '=', True), '&', ('expiry_date', '>=', today), ('alert_date', '>', today)]

    def _search_state(self, operator, value):
        values = [value] if isinstance(value, str) else list(value or [])
        if operator not in ('=', 'in', '!=', 'not in'):
            raise ValidationError(_('Toán tử tìm kiếm không hỗ trợ.'))
        domain = expression.OR([self._state_domain(v) for v in values]) if values else expression.FALSE_DOMAIN
        ids = self.with_context(active_test=False)._search(domain)
        return [('id', 'in' if operator in ('=', 'in') else 'not in', ids)]

    @api.onchange('type_id', 'issue_date')
    def _onchange_validity(self):
        if self.type_id and not self.type_id.validity_months and self.type_id.category in ('facility', 'business'):
            self.no_expiry = True
        if self.issue_date and self.type_id.validity_months and not self.expiry_date:
            self.expiry_date = self.issue_date + relativedelta(months=self.type_id.validity_months)

    @api.onchange('practitioner_id')
    def _onchange_practitioner_id(self):
        prac = self.practitioner_id
        if prac and self.type_id.per_practitioner:
            self.number = self.number or prac.license_number
            if 'license_expiry_date' in prac._fields and prac.license_expiry_date and not self.expiry_date:
                self.expiry_date = prac.license_expiry_date

    @api.constrains('issue_date', 'expiry_date')
    def _check_dates(self):
        for doc in self:
            if doc.issue_date and doc.expiry_date and doc.expiry_date < doc.issue_date:
                raise ValidationError(_('Ngày hết hạn phải sau ngày cấp.'))

    @api.model_create_multi
    def create(self, vals_list):
        docs = super().create(vals_list)
        docs.filtered('renewed_from_id').mapped('renewed_from_id').write({'active': False})
        return docs

    def action_renew(self):
        """Gia hạn: mở hồ sơ mới cùng loại; hồ sơ cũ tự lưu trữ khi lưu hồ sơ mới."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Gia hạn hồ sơ'),
            'res_model': 'dmag.compliance.doc',
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'default_name': self.name,
                'default_type_id': self.type_id.id,
                'default_company_id': self.company_id.id,
                'default_issuer': self.issuer,
                'default_partner_id': self.partner_id.id,
                'default_practitioner_id': self.practitioner_id.id,
                'default_equipment_id': self.equipment_id.id,
                'default_responsible_id': self.responsible_id.id,
                'default_renewed_from_id': self.id,
            },
        }

    def _item_dict(self, kind='document'):
        self.ensure_one()
        return {
            'kind': kind,
            'model': self._name,
            'id': self.id,
            'name': self.name,
            'type': self.type_id.name,
            'category': self.category,
            'number': self.number or '',
            'expiry_date': fields.Date.to_string(self.expiry_date) if self.expiry_date else False,
            'days_left': self.days_left if self.expiry_date else None,
            'state': self.state,
            'responsible': self.responsible_id.name or '',
            'legal_basis': self.type_id.legal_basis or '',
        }

    # ------------------------------------------------------------------ dashboard
    @api.model
    def get_compliance_status(self, company_id=False):
        """Checklist "Sẵn sàng thanh tra" cho Buồng lái chủ phòng khám."""
        company = self.env['res.company'].browse(company_id) if company_id else self.env.company
        Doc = self.sudo().with_context(active_test=True)
        docs = Doc.search([('company_id', '=', company.id)])
        red_items, expiring_items = [], []
        doc_counts = {'valid': 0, 'expiring': 0, 'expired': 0}
        for doc in docs:
            doc_counts[doc.state] += 1
            if doc.state == 'expired':
                red_items.append(doc._item_dict())
            elif doc.state == 'expiring':
                expiring_items.append(doc._item_dict())

        # Hồ sơ bắt buộc còn thiếu
        missing = []
        live = docs.filtered(lambda d: d.state != 'expired')
        Equipment = self.env['dmag.equipment'].sudo()
        equipments = Equipment.search([('company_id', '=', company.id), ('state', '!=', 'retired')])
        for dtype in self.env['dmag.compliance.doc.type'].sudo().search([('is_mandatory', '=', True)]):
            typed = live.filtered(lambda d, t=dtype: d.type_id == t)
            if dtype.per_equipment and dtype.equipment_categories:
                cats = [c.strip() for c in dtype.equipment_categories.split(',') if c.strip()]
                for eq in equipments.filtered(lambda e: e.category in cats):
                    if not typed.filtered(lambda d, e=eq: d.equipment_id == e):
                        missing.append({'kind': 'missing', 'model': 'dmag.equipment', 'id': eq.id,
                                        'name': _('%(type)s – %(eq)s', type=dtype.name, eq=eq.name),
                                        'type': dtype.name, 'category': dtype.category, 'expiry_date': False,
                                        'days_left': None, 'state': 'missing', 'responsible': '',
                                        'legal_basis': dtype.legal_basis or ''})
            elif not typed:
                missing.append({'kind': 'missing', 'model': 'dmag.compliance.doc.type', 'id': dtype.id,
                                'name': dtype.name, 'type': dtype.name, 'category': dtype.category,
                                'expiry_date': False, 'days_left': None, 'state': 'missing',
                                'responsible': '', 'legal_basis': dtype.legal_basis or ''})
        red_items += missing

        # Thiết bị: kiểm định / hiệu chuẩn / bảo trì
        eq_counts = {'ok': 0, 'due_soon': 0, 'overdue': 0}
        for eq in equipments:
            status = eq.inspection_status
            if status == 'na':
                continue
            eq_counts[status] += 1
            if status == 'overdue':
                red_items.append(eq._item_dict())
            elif status == 'due_soon':
                expiring_items.append(eq._item_dict())

        # Tiệt khuẩn 30 ngày gần nhất
        Batch = self.env['dmag.sterilization.batch'].sudo()
        since = fields.Datetime.now() - timedelta(days=30)
        batches = Batch.search([('company_id', '=', company.id), ('date', '>=', since)])
        failed = batches.filtered(lambda b: b.state in ('failed', 'recalled'))
        for batch in failed:
            red_items.append(batch._item_dict())
        sterilization = {
            'batches_30d': len(batches),
            'failed_30d': len(failed),
            'pending_biological': len(batches.filtered(lambda b: b.biological_result == 'pending')),
        }

        counts = {
            'valid': doc_counts['valid'] + eq_counts['ok'],
            'expiring': doc_counts['expiring'] + eq_counts['due_soon'],
            'expired': doc_counts['expired'] + eq_counts['overdue'],
            'missing': len(missing),
        }
        total_checks = sum(counts.values())
        score = round(100.0 * (counts['valid'] + counts['expiring']) / total_checks) if total_checks else 100
        return {
            'company_id': company.id,
            'date': fields.Date.to_string(fields.Date.context_today(self)),
            'ready': not red_items,
            'score': score,
            'counts': counts,
            'documents': doc_counts,
            'equipment': eq_counts,
            'sterilization': sterilization,
            'red_items': red_items,
            'expiring_items': sorted(expiring_items, key=lambda i: i.get('days_left') or 0),
        }

    # ------------------------------------------------------------------ cron
    @api.model
    def _dmag_alert_user(self, record, user=None):
        if user:
            return user
        group = self.env.ref('dmag_dental_base.group_dmag_manager', raise_if_not_found=False)
        managers = group.users.filtered(lambda u: record.company_id in u.company_ids) if group else False
        return managers[:1] if managers else self.env.user

    @api.model
    def _cron_compliance_alerts(self):
        """Hằng ngày: tạo việc cho hồ sơ / thiết bị sắp hết hạn (trong số ngày cảnh báo) hoặc đã quá hạn."""
        today = fields.Date.context_today(self)
        docs = self.sudo().search([('state', 'in', ('expiring', 'expired')), ('no_expiry', '=', False)])
        for doc in docs:
            user = self._dmag_alert_user(doc, doc.responsible_id)
            if doc.state == 'expired':
                summary = _('Hồ sơ "%s" đã hết hạn – gia hạn ngay', doc.name)
            else:
                summary = _('Hồ sơ "%(name)s" hết hạn ngày %(date)s – chuẩn bị gia hạn',
                            name=doc.name, date=doc.expiry_date)
            doc._dmag_schedule_alert(summary, min(doc.expiry_date or today, today + timedelta(days=7)), user)
        equipments = self.env['dmag.equipment'].sudo().search([('state', '!=', 'retired')])
        for eq in equipments.filtered(lambda e: e.inspection_status in ('due_soon', 'overdue')):
            user = self._dmag_alert_user(eq, eq.responsible_id)
            eq._dmag_schedule_alert(
                _('Thiết bị "%(name)s": %(what)s đến hạn %(date)s', name=eq.name,
                  what=eq._due_label(), date=eq.next_due_date),
                min(eq.next_due_date or today, today + timedelta(days=7)), user)
        return True
