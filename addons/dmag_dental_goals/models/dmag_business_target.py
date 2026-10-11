from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError

from odoo.addons.dmag_dental_base.models.dmag_access import check_director, is_director, is_workflow

from .dmag_goal_metrics import (METRIC_SELECTION, METRICS, PERIOD_TYPES, UNIT_LABELS, period_bounds,
                                period_label)


class DmagBusinessTarget(models.Model):
    """Mục tiêu kinh doanh do Giám đốc đặt cho một kỳ (tháng / quý / năm).

    * Một dòng = một chỉ số (doanh thu, khách mới, tỷ lệ chốt…) cho toàn phòng khám hoặc cho một bác sĩ.
    * Nhóm các dòng theo ``objective`` (Mục tiêu – Objective) → hiển thị như OKR: Objective → các KR.
    * Tạo được – không sửa: Quản lý được soạn đề xuất (nháp); Giám đốc chốt; sau khi chốt chỉ Giám đốc sửa / xóa.
    """
    _name = 'dmag.business.target'
    _description = 'Mục tiêu kinh doanh'
    _inherit = ['mail.thread']
    _order = 'date_from desc, period_type, objective, sequence, id'
    _rec_name = 'name'

    name = fields.Char('Tên', compute='_compute_name', store=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', string='Phòng khám', required=True, index=True,
                                 default=lambda self: self.env.company, tracking=True)
    currency_id = fields.Many2one(related='company_id.currency_id')
    period_type = fields.Selection(PERIOD_TYPES, string='Loại kỳ', required=True, default='month', tracking=True)
    date_from = fields.Date('Từ ngày', required=True, tracking=True,
                            default=lambda self: fields.Date.context_today(self).replace(day=1),
                            help='Tự đưa về ngày đầu tháng / quý / năm.')
    date_to = fields.Date('Đến ngày', compute='_compute_date_to', store=True)
    period_label = fields.Char('Kỳ', compute='_compute_name', store=True)
    metric = fields.Selection(METRIC_SELECTION, string='Chỉ số', required=True, tracking=True)
    metric_kind = fields.Char(compute='_compute_metric_info')
    metric_unit = fields.Char('Đơn vị', compute='_compute_metric_info')
    direction = fields.Selection([('higher', 'Càng cao càng tốt'), ('lower', 'Càng thấp càng tốt')],
                                 string='Chiều', compute='_compute_metric_info')
    formula = fields.Text('Cách tính', compute='_compute_metric_info')
    target_value = fields.Float('Mục tiêu', required=True, tracking=True, digits=(16, 1))
    objective = fields.Char('Mục tiêu (Objective)', tracking=True,
                            help='Nhóm các chỉ số theo một Objective (OKR), ví dụ "Tăng trưởng doanh thu bền vững". '
                                 'Bảng điều hành hiển thị Objective → các kết quả then chốt (KR).')
    practitioner_id = fields.Many2one('dmag.dental.practitioner', string='Bác sĩ', index=True, ondelete='cascade',
                                      tracking=True, help='Để trống: mục tiêu toàn phòng khám.')
    user_id = fields.Many2one('res.users', string='Người phụ trách', tracking=True,
                              domain=[('share', '=', False)])
    note = fields.Text('Ghi chú / sáng kiến')
    state = fields.Selection([('draft', 'Đề xuất'), ('confirmed', 'Đã chốt')], string='Trạng thái',
                             default='draft', required=True, tracking=True, copy=False)
    confirmed_by_id = fields.Many2one('res.users', string='Người chốt', readonly=True, copy=False)
    confirmed_date = fields.Datetime('Thời điểm chốt', readonly=True, copy=False)

    _sql_constraints = [('target_positive', 'CHECK(target_value >= -100)', 'Giá trị mục tiêu không hợp lệ.')]

    # ------------------------------------------------------------------ compute
    @api.depends('period_type', 'date_from')
    def _compute_date_to(self):
        for target in self:
            target.date_to = period_bounds(target.period_type, target.date_from)[1] \
                if target.date_from and target.period_type else False

    @api.depends('metric', 'period_type', 'date_from', 'practitioner_id')
    def _compute_name(self):
        labels = dict(METRIC_SELECTION)
        for target in self:
            label = period_label(target.period_type, target.date_from) \
                if target.date_from and target.period_type else ''
            target.period_label = label
            name = labels.get(target.metric, '')
            if target.practitioner_id:
                name = '%s – %s' % (name, target.practitioner_id.name)
            target.name = '%s · %s' % (name, label) if label else name

    @api.depends('metric')
    def _compute_metric_info(self):
        for target in self:
            info = METRICS.get(target.metric) or {}
            target.metric_kind = info.get('kind')
            target.metric_unit = UNIT_LABELS.get(info.get('unit'), '')
            target.direction = info.get('direction')
            target.formula = info.get('formula')

    # ------------------------------------------------------------------ constraints
    @api.constrains('metric', 'period_type', 'date_from', 'company_id', 'practitioner_id', 'active')
    def _check_unique(self):
        for target in self.filtered('active'):
            dup = self.search_count([
                ('id', '!=', target.id), ('company_id', '=', target.company_id.id), ('metric', '=', target.metric),
                ('period_type', '=', target.period_type), ('date_from', '=', target.date_from),
                ('practitioner_id', '=', target.practitioner_id.id or False)])
            if dup:
                raise ValidationError(_('Đã có mục tiêu "%s" cho kỳ này – sửa dòng cũ thay vì tạo thêm.', target.name))

    @api.constrains('metric', 'target_value')
    def _check_value(self):
        for target in self:
            unit = (METRICS.get(target.metric) or {}).get('unit')
            if unit == 'pct' and not 0 <= target.target_value <= 100:
                raise ValidationError(_('Mục tiêu tỷ lệ phải trong khoảng 0–100%.'))
            if unit == 'score' and not -100 <= target.target_value <= 100:
                raise ValidationError(_('NPS nằm trong thang −100…100.'))
            if unit in ('money', 'count', 'min') and target.target_value < 0:
                raise ValidationError(_('Mục tiêu không được âm.'))

    # ------------------------------------------------------------------ "tạo được – không sửa"
    @api.model
    def _normalize_vals(self, vals, period_type=None):
        if vals.get('date_from'):
            ptype = vals.get('period_type') or period_type or 'month'
            vals['date_from'] = period_bounds(ptype, fields.Date.to_date(vals['date_from']))[0]
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._normalize_vals(vals)
            if vals.get('state') == 'confirmed' and not is_workflow(self.env):
                check_director(self.env, _('Chỉ Giám đốc / Quản lý cấp cao được chốt mục tiêu kinh doanh.'))
        return super().create(vals_list)

    def write(self, vals):
        if not is_workflow(self.env) and not is_director(self.env):
            if any(t.state == 'confirmed' for t in self) or vals.get('state') == 'confirmed':
                raise AccessError(_('Mục tiêu đã chốt – chỉ Giám đốc / Quản lý cấp cao được sửa.'))
        if 'date_from' in vals or 'period_type' in vals:
            for target in self:
                own = dict(vals)
                own.setdefault('date_from', target.date_from)
                self._normalize_vals(own, own.get('period_type') or target.period_type)
                super(DmagBusinessTarget, target).write(own)
            return True
        return super().write(vals)

    def unlink(self):
        if not is_workflow(self.env) and not is_director(self.env) and any(t.state == 'confirmed' for t in self):
            raise AccessError(_('Mục tiêu đã chốt – chỉ Giám đốc / Quản lý cấp cao được xóa.'))
        return super().unlink()

    # ------------------------------------------------------------------ actions
    def action_confirm(self):
        check_director(self.env, _('Chỉ Giám đốc / Quản lý cấp cao được chốt mục tiêu kinh doanh.'))
        self.filtered(lambda t: t.state == 'draft').write({
            'state': 'confirmed', 'confirmed_by_id': self.env.user.id, 'confirmed_date': fields.Datetime.now()})
        return True

    def action_reset_draft(self):
        check_director(self.env)
        self.write({'state': 'draft', 'confirmed_by_id': False, 'confirmed_date': False})
        return True

    def action_open_dashboard(self):
        return self.env['ir.actions.actions']._for_xml_id('dmag_clinic_workspace.action_dmag_owner_cockpit')
