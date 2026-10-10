from datetime import datetime, time, timedelta

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models

ORTHO = 'orthodontic'


class DmagOkrGuardrail(models.Model):
    """Chỉ số sức khỏe / cầu chì y đức: vượt ngưỡng → các KR liên quan chuyển đỏ."""
    _name = 'dmag.okr.guardrail'
    _description = 'Chỉ số cầu chì OKR nha khoa'
    _inherit = ['mail.thread']
    _order = 'sequence, id'

    name = fields.Char('Chỉ số', required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', string='Phòng khám', required=True,
                                 default=lambda self: self.env.company)
    metric = fields.Selection([
        ('complaint_rate', 'Tỷ lệ phàn nàn / lượt khám (%/tháng)'),
        ('ortho_cancel_30d', 'Tỷ lệ hủy hợp đồng niềng trong 30 ngày (%)'),
        ('low_reviews', 'Số đánh giá 1–2 sao / tháng (nhập tay)'),
        ('manual', 'Nhập tay'),
    ], string='Cách đo', required=True, default='manual', tracking=True)
    threshold = fields.Float('Ngưỡng (vượt khi lớn hơn)', required=True, tracking=True)
    unit = fields.Char('Đơn vị', default='%')
    period_date = fields.Date('Tháng đo', default=lambda self: fields.Date.context_today(self).replace(day=1),
                              help='Để trống: tháng hiện tại.')
    manual_value = fields.Float('Giá trị nhập tay', tracking=True,
                                help='Dùng cho chỉ số nhập tay hoặc khi chưa có nguồn dữ liệu tự động.')
    value = fields.Float('Giá trị đo', readonly=True, tracking=True)
    is_auto = fields.Boolean('Đo tự động', readonly=True)
    breached = fields.Boolean('Vượt ngưỡng', readonly=True, tracking=True)
    last_check = fields.Datetime('Kiểm tra lúc', readonly=True)
    key_result_ids = fields.Many2many('okr.scale.key.result', 'dmag_okr_guardrail_kr_rel',
                                      'guardrail_id', 'key_result_id', string='KR liên quan')
    note = fields.Text('Ghi chú')

    def _month_window(self):
        month = (self.period_date or fields.Date.context_today(self)).replace(day=1)
        start = datetime.combine(month, time.min)
        return start, start + relativedelta(months=1)

    def _measure(self):
        """Giá trị đo được từ dữ liệu, None khi phải dùng số nhập tay."""
        self.ensure_one()
        start, end = self._month_window()
        if self.metric == 'complaint_rate':
            Visit = self.env['dmag.dental.visit'].sudo()
            if 'dmag_complaint' not in Visit._fields:
                return None
            visits = Visit.search([('company_id', '=', self.company_id.id), ('state', '=', 'done'),
                                   ('done_time', '>=', start), ('done_time', '<', end)])
            if not visits:
                return 0.0
            return round(len(visits.filtered('dmag_complaint')) * 100.0 / len(visits), 2)
        if self.metric == 'ortho_cancel_30d':
            plans = self.env['dmag.treatment.plan'].sudo().search([
                ('company_id', '=', self.company_id.id), ('accepted_date', '>=', start - timedelta(days=30)),
                ('accepted_date', '<', end)])
            plans = plans.filtered(lambda p: ORTHO in p.accepted_option_id.line_ids.mapped('product_id.dental_category'))
            if not plans:
                return 0.0
            cancelled = plans.filtered(lambda p: p.state == 'cancel' and p.write_date
                                       and p.write_date - p.accepted_date <= timedelta(days=30))
            return round(len(cancelled) * 100.0 / len(plans), 2)
        return None

    def action_check(self):
        now = fields.Datetime.now()
        for guard in self:
            measured = guard._measure()
            value = guard.manual_value if measured is None else measured
            breached = value > guard.threshold
            if breached and not guard.breached:
                guard.message_post(body=_('Vượt ngưỡng cầu chì: %(value)s > %(threshold)s – các KR liên quan chuyển đỏ.',
                                          value=value, threshold=guard.threshold))
            guard.write({'value': value, 'is_auto': measured is not None, 'breached': breached,
                         'last_check': now})
        return True

    @api.onchange('manual_value', 'threshold')
    def _onchange_manual(self):
        if self.metric in ('low_reviews', 'manual'):
            self.value = self.manual_value
            self.breached = self.manual_value > self.threshold
