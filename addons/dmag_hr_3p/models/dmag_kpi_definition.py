import logging

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

DATA_SOURCES = [
    ('manual', 'Nhập tay'),
    ('nps', 'NPS (khảo sát hài lòng)'),
    ('retention', 'Tỷ lệ khách quay lại (%)'),
    ('wait_time', 'Thời gian chờ trung bình (phút)'),
    ('revenue', 'Doanh thu thủ thuật'),
    ('okr_score', 'Điểm OKR (%)'),
    ('commission', 'Hoa hồng / thủ thuật phí'),
]


class DmagKpiDefinition(models.Model):
    """Chỉ tiêu KPI của một vị trí (P3).

    ``data_source`` khác "manual" là khóa của hàm ``_dmag_kpi_value_<key>`` – module khác có thể
    thêm nguồn mới bằng ``selection_add`` + định nghĩa hàm tương ứng, không cần sửa module này.
    """
    _name = 'dmag.kpi.definition'
    _description = 'Chỉ tiêu KPI (P3)'
    _order = 'profile_id, sequence, id'

    profile_id = fields.Many2one('dmag.job.position.profile', string='Vị trí', required=True,
                                 ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    name = fields.Char('Chỉ tiêu', required=True, translate=True)
    code = fields.Char('Mã')
    description = fields.Text('Cách đo / ghi chú')
    weight = fields.Float('Trọng số (%)', required=True, default=0.0)
    target = fields.Float('Mục tiêu', required=True, default=100.0)
    unit = fields.Char('Đơn vị', default='%')
    direction = fields.Selection([('higher', 'Càng cao càng tốt'), ('lower', 'Càng thấp càng tốt')],
                                 string='Chiều đánh giá', default='higher', required=True)
    data_source = fields.Selection(DATA_SOURCES, string='Nguồn dữ liệu', default='manual', required=True)
    scope = fields.Selection([('personal', 'Cá nhân'), ('clinic', 'Toàn phòng khám')],
                             string='Phạm vi đo', default='personal', required=True,
                             help='Cá nhân: theo bác sĩ / phụ tá gắn với nhân viên. '
                                  'Toàn phòng khám: dùng cho lễ tân, quản lý.')
    is_sample = fields.Boolean('Dữ liệu mẫu')

    @api.constrains('weight', 'target')
    def _check_values(self):
        for kpi in self:
            if kpi.weight < 0:
                raise ValidationError(_('Trọng số KPI không được âm.'))
            if not kpi.target:
                raise ValidationError(_('Mục tiêu KPI "%s" phải khác 0.', kpi.name))

    # ------------------------------------------------------------------ achievement
    def _achievement(self, actual):
        """% hoàn thành (chưa áp trần)."""
        self.ensure_one()
        if actual is None:
            return 0.0
        if self.direction == 'lower':
            if actual <= 0:
                return 100.0 if self.target > 0 else 0.0
            return self.target * 100.0 / actual
        return actual * 100.0 / self.target

    # ------------------------------------------------------------------ data sources
    def _compute_actual(self, employee, date_from, date_to):
        """Giá trị thực tế từ dữ liệu, ``None`` khi không có nguồn (giữ số nhập tay)."""
        self.ensure_one()
        if self.data_source == 'manual':
            return None
        method = getattr(self, '_dmag_kpi_value_%s' % self.data_source, None)
        if not method:
            return None
        try:
            return method(employee, date_from, date_to)
        except Exception:  # nguồn mềm: không chặn kỳ lương
            _logger.exception('Không tính được KPI %s', self.data_source)
            return None

    def _scope_practitioners(self, employee):
        Practitioner = self.env['dmag.dental.practitioner'].sudo()
        if self.scope == 'clinic':
            return None
        practitioners = Practitioner.search([('employee_id', '=', employee.id)])
        if not practitioners and employee.user_id:
            practitioners = Practitioner.search([('user_id', '=', employee.user_id.id)])
        return practitioners

    def _visit_domain(self, employee, date_from, date_to, date_field):
        domain = [('company_id', '=', employee.company_id.id),
                  (date_field, '>=', fields.Datetime.to_datetime(date_from)),
                  (date_field, '<', fields.Datetime.to_datetime(date_to) + _one_day())]
        practitioners = self._scope_practitioners(employee)
        if practitioners is not None:
            domain += ['|', ('doctor_id', 'in', practitioners.ids), ('assistant_id', 'in', practitioners.ids)]
        return domain

    def _dmag_kpi_value_wait_time(self, employee, date_from, date_to):
        if 'dmag.dental.visit' not in self.env:
            return None
        visits = self.env['dmag.dental.visit'].sudo().search(
            self._visit_domain(employee, date_from, date_to, 'checkin_time') + [('chair_time', '!=', False)])
        if not visits:
            return None
        return sum(visits.mapped('wait_minutes')) / len(visits)

    def _dmag_kpi_value_retention(self, employee, date_from, date_to):
        if 'dmag.dental.visit' not in self.env:
            return None
        Visit = self.env['dmag.dental.visit'].sudo()
        visits = Visit.search(self._visit_domain(employee, date_from, date_to, 'scheduled_start')
                              + [('state', '=', 'done')])
        patients = visits.mapped('patient_id')
        if not patients:
            return None
        returning = Visit.search([
            ('patient_id', 'in', patients.ids), ('state', '=', 'done'),
            ('scheduled_start', '<', fields.Datetime.to_datetime(date_from)),
            ('scheduled_start', '>=', fields.Datetime.to_datetime(date_from) - _one_day(365)),
        ]).mapped('patient_id')
        return len(returning) * 100.0 / len(patients)

    def _dmag_kpi_value_revenue(self, employee, date_from, date_to):
        if 'dmag.dental.procedure' not in self.env:
            return None
        domain = [('state', '=', 'done'), ('company_id', '=', employee.company_id.id),
                  ('visit_id.scheduled_start', '>=', fields.Datetime.to_datetime(date_from)),
                  ('visit_id.scheduled_start', '<', fields.Datetime.to_datetime(date_to) + _one_day())]
        practitioners = self._scope_practitioners(employee)
        if practitioners is not None:
            domain += ['|', ('doctor_id', 'in', practitioners.ids), ('assistant_id', 'in', practitioners.ids)]
        return sum(self.env['dmag.dental.procedure'].sudo().search(domain).mapped('amount'))

    def _dmag_kpi_value_nps(self, employee, date_from, date_to):
        if 'dmag.nps.response' not in self.env:
            return None
        Response = self.env['dmag.nps.response'].sudo()
        score_field = next((f for f in ('score', 'nps_score', 'rating') if f in Response._fields), None)
        if not score_field:
            return None
        date_field = next((f for f in ('date', 'response_date') if f in Response._fields), 'create_date')
        domain = [(date_field, '>=', date_from), (date_field, '<=', date_to)]
        if 'company_id' in Response._fields:
            domain.append(('company_id', '=', employee.company_id.id))
        scores = [s for s in Response.search(domain).mapped(score_field) if s is not False]
        if not scores:
            return None
        promoters = len([s for s in scores if s >= 9])
        detractors = len([s for s in scores if s <= 6])
        return (promoters - detractors) * 100.0 / len(scores)

    def _dmag_kpi_value_okr_score(self, employee, date_from, date_to):
        if 'okr.scale.key.result' not in self.env or not employee.user_id:
            return None
        krs = self.env['okr.scale.key.result'].sudo().search([
            ('owner_id', '=', employee.user_id.id),
            ('cycle_id.date_start', '<=', date_to), ('cycle_id.date_end', '>=', date_from),
        ])
        if not krs:
            return None
        total_weight = sum(krs.mapped('weight')) or len(krs)
        return sum(kr.progress * (kr.weight or 1.0) for kr in krs) / total_weight

    def _dmag_kpi_value_commission(self, employee, date_from, date_to):
        Line = self.env.get('dmag.commission.line')
        if Line is None or not hasattr(Line, '_dmag_amount_for_employee'):
            return None
        return Line._dmag_amount_for_employee(employee, date_from, date_to)


def _one_day(days=1):
    from datetime import timedelta
    return timedelta(days=days)
