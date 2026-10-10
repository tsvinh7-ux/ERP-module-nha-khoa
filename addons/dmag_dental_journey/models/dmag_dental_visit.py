import logging
from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

CSKH_ACTIVITY_XMLIDS = ('dmag_dental_journey.activity_type_cskh_call', 'dmag_dental_journey.activity_type_complaint')


class DmagDentalVisit(models.Model):
    _inherit = 'dmag.dental.visit'

    pain_score_24h = fields.Integer('Điểm đau sau 24h (0–10)', readonly=True, tracking=True,
                                    help='CSKH gọi hỏi thăm sau 24 giờ (ca xâm lấn).')
    pain_score_24h_date = fields.Datetime('Hỏi điểm đau 24h lúc', readonly=True)
    pain_score_24h_note = fields.Char('Ghi chú hỏi thăm 24h', readonly=True)
    dmag_journey_today_url = fields.Char('Link "Nội dung khám hôm nay"', compute='_compute_dmag_journey_today_url')
    nps_response_ids = fields.One2many('dmag.nps.response', 'visit_id', string='Khảo sát NPS')
    journey_execution_ids = fields.One2many('dmag.journey.execution', 'visit_id', string='Điểm chạm hành trình')
    journey_execution_count = fields.Integer(compute='_compute_journey_execution_count')

    def _compute_dmag_journey_today_url(self):
        has_portal = 'dmag_portal_url' in self._fields
        for visit in self:
            url = has_portal and visit.dmag_portal_url
            visit.dmag_journey_today_url = url or visit.company_id.website or visit.get_base_url()

    def _compute_journey_execution_count(self):
        data = self.env['dmag.journey.execution']._read_group(
            [('visit_id', 'in', self.ids)], ['visit_id'], ['__count'])
        counts = {visit.id: count for visit, count in data}
        for visit in self:
            visit.journey_execution_count = counts.get(visit.id, 0)

    @api.constrains('pain_score_24h')
    def _check_pain_score_24h(self):
        for visit in self:
            if not 0 <= visit.pain_score_24h <= 10:
                raise ValidationError(_('Điểm đau phải từ 0 đến 10.'))

    # ------------------------------------------------------------------ journey hook
    def _dmag_journey_event(self, event):
        res = super()._dmag_journey_event(event)
        if self and not self.env.context.get('dmag_journey_disable'):
            try:
                with self.env.cr.savepoint():
                    self.env['dmag.journey.rule']._dmag_on_visit_event(self, event)
            except Exception:  # hành trình không được chặn nghiệp vụ phòng khám
                _logger.exception('Journey event %s failed for visits %s', event, self.ids)
        return res

    def _dmag_journey_products(self):
        """Dịch vụ của lượt khám: dự kiến + thủ thuật đã làm."""
        self.ensure_one()
        return (self.service_ids | self.procedure_ids.mapped('product_id')).sudo()

    def record_pain_score_24h(self, score, note=False):
        """CSKH ghi điểm đau sau 24h; ≥ 7 → báo bác sĩ."""
        self.ensure_one()
        try:
            score = int(score)
        except (TypeError, ValueError) as exc:
            raise ValidationError(_('Điểm đau phải từ 0 đến 10.')) from exc
        self._workflow_write({'pain_score_24h': score, 'pain_score_24h_date': fields.Datetime.now(),
                              'pain_score_24h_note': note or False})
        self.message_post(body=_('Hỏi thăm sau 24h: điểm đau %(score)s/10%(note)s – %(user)s',
                                 score=score, note=(' – %s' % note) if note else '', user=self.env.user.name))
        if score >= 7:
            doctor = self.env['dmag.journey.rule']._dmag_responsible_user('doctor', self, self.company_id)
            self.sudo().activity_schedule(
                'dmag_dental_journey.activity_type_cskh_call',
                date_deadline=fields.Date.context_today(self),
                summary=_('Điểm đau cao sau 24h (%s/10) – cần bác sĩ liên hệ', score),
                note=note or '', user_id=doctor.id)
        return True

    def action_open_pain_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Ghi điểm đau sau 24h'),
            'res_model': 'dmag.journey.pain.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_visit_id': self.id},
        }

    def action_open_journey_executions(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Điểm chạm – %s', self.name),
            'res_model': 'dmag.journey.execution',
            'view_mode': 'tree,form',
            'domain': [('visit_id', '=', self.id)],
        }

    # ------------------------------------------------------------------ recall / warranty
    @api.model
    def _dmag_recall_due(self, days_ahead=0, companies=None, lookback_days=30, today=None):
        """Danh sách nhắc tái khám đến hạn: [{'visit', 'product', 'due_date', 'patient'}].

        Hạn = ngày hoàn tất + ``product.recall_months``. Đến hạn khi hôm nay ≥ hạn − ``days_ahead`` và
        chưa quá hạn ``lookback_days`` ngày; bỏ qua nếu khách đã có lịch sắp tới hoặc đã làm lại dịch vụ.
        """
        today = today or fields.Date.context_today(self)
        companies = companies or self.env.companies
        visits = self.sudo().search([
            ('state', '=', 'done'), ('company_id', 'in', companies.ids),
            ('done_time', '>=', fields.Datetime.now() - relativedelta(years=3)),
            '|', ('procedure_ids.product_id.recall_months', '>', 0), ('service_ids.recall_months', '>', 0),
        ], order='done_time desc')
        result = []
        seen = set()
        for visit in visits:
            products = visit.procedure_ids.mapped('product_id') or visit.service_ids
            for product in products.filtered(lambda p: p.recall_months > 0):
                key = (visit.patient_id.id, product.id)
                if key in seen:  # chỉ tính lần làm gần nhất
                    continue
                seen.add(key)
                due = fields.Datetime.to_datetime(visit.done_time).date() + relativedelta(months=product.recall_months)
                if not (due - timedelta(days=days_ahead) <= today <= due + timedelta(days=lookback_days)):
                    continue
                if visit._dmag_recall_rebooked(product):
                    continue
                result.append({'visit': visit, 'product': product, 'due_date': due, 'patient': visit.patient_id})
        return result

    def _dmag_recall_rebooked(self, product):
        """Khách đã đặt lịch sắp tới, hoặc đã làm lại dịch vụ sau lượt này."""
        self.ensure_one()
        later = self.sudo().search([
            ('patient_id', '=', self.patient_id.id), ('id', '!=', self.id),
            ('state', 'in', ('draft', 'confirmed', 'arrived', 'in_chair', 'done')),
            ('scheduled_start', '>', self.scheduled_start),
        ])
        if later.filtered(lambda v: v.state != 'done'):
            return True
        return any(product in (v.procedure_ids.mapped('product_id') | v.service_ids) for v in later)

    @api.model
    def _dmag_warranty_due(self, days_ahead=30, companies=None, today=None):
        """Bảo hành sắp hết hạn: [{'key', 'visit', 'product', 'expiry_date'}].

        Mặc định tính từ thủ thuật hoàn tất + ``product.warranty_months``. Module bảo hành
        (thẻ bảo hành điện tử) có thể ghi đè để dùng ngày hết hạn trên thẻ.
        """
        today = today or fields.Date.context_today(self)
        companies = companies or self.env.companies
        procedures = self.env['dmag.dental.procedure'].sudo().search([
            ('state', '=', 'done'), ('company_id', 'in', companies.ids),
            ('visit_id.state', '=', 'done'),
            ('product_id.warranty_months', '>', 0),
        ])
        result = []
        for proc in procedures:
            done = proc.visit_id.done_time
            if not done:
                continue
            expiry = fields.Datetime.to_datetime(done).date() + relativedelta(months=proc.product_id.warranty_months)
            if expiry - timedelta(days=days_ahead) <= today <= expiry:
                result.append({'key': 'warranty:%s' % proc.id, 'visit': proc.visit_id,
                               'product': proc.product_id, 'expiry_date': expiry})
        return result

    # ------------------------------------------------------------------ dashboard
    @api.model
    def get_journey_dashboard(self, date_from=False, date_to=False):
        """Số liệu bảng điều khiển hành trình (mặc định 30 ngày gần nhất).

        :return: dict {period, visits{total, booked, showed, no_show, cancelled}, show_up_rate, no_show_rate,
                 nps{score, responses, promoters, passives, detractors, complaints_open},
                 recall_due, messages{queued, sent, delivered, failed, skipped, total},
                 call_tasks{today, overdue, planned}}
        """
        today = fields.Date.context_today(self)
        date_to = fields.Date.to_date(date_to) if date_to else today
        date_from = fields.Date.to_date(date_from) if date_from else date_to - timedelta(days=29)
        tz_offset = self._tz_offset()
        dt_from = fields.Datetime.to_datetime(date_from) - tz_offset
        dt_to = fields.Datetime.to_datetime(date_to + timedelta(days=1)) - tz_offset
        companies = self.env.companies

        counts = dict.fromkeys(('draft', 'confirmed', 'arrived', 'in_chair', 'done', 'cancel', 'no_show'), 0)
        for state, count in self._read_group([
                ('company_id', 'in', companies.ids),
                ('scheduled_start', '>=', dt_from), ('scheduled_start', '<', dt_to)], ['state'], ['__count']):
            counts[state] = count
        showed = counts['arrived'] + counts['in_chair'] + counts['done']
        base = showed + counts['no_show']

        nps_data = dict.fromkeys(('promoter', 'passive', 'detractor'), 0)
        Nps = self.env['dmag.nps.response']
        for category, count in Nps._read_group([
                ('company_id', 'in', companies.ids), ('state', '=', 'answered'),
                ('date', '>=', dt_from), ('date', '<', dt_to)], ['category'], ['__count']):
            nps_data[category] = count
        responses = sum(nps_data.values())

        msg = dict.fromkeys(('queued', 'sent', 'delivered', 'failed', 'skipped', 'cancel'), 0)
        for state, count in self.env['dmag.zns.message']._read_group([
                ('company_id', 'in', companies.ids),
                ('create_date', '>=', dt_from), ('create_date', '<', dt_to)], ['state'], ['__count']):
            msg[state] = count

        activity_types = [self.env.ref(x).id for x in CSKH_ACTIVITY_XMLIDS]
        Activity = self.env['mail.activity']
        act_domain = [('activity_type_id', 'in', activity_types)]
        tasks = {
            'today': Activity.search_count(act_domain + [('date_deadline', '=', today)]),
            'overdue': Activity.search_count(act_domain + [('date_deadline', '<', today)]),
            'planned': Activity.search_count(act_domain + [('date_deadline', '>', today)]),
        }

        def rate(part, whole):
            return round(100.0 * part / whole, 1) if whole else 0.0

        return {
            'period': {'from': fields.Date.to_string(date_from), 'to': fields.Date.to_string(date_to)},
            'visits': {
                'total': sum(counts.values()),
                'booked': counts['draft'] + counts['confirmed'],
                'showed': showed,
                'no_show': counts['no_show'],
                'cancelled': counts['cancel'],
            },
            'show_up_rate': rate(showed, base),
            'no_show_rate': rate(counts['no_show'], base),
            'nps': {
                'score': round(rate(nps_data['promoter'], responses) - rate(nps_data['detractor'], responses), 1),
                'responses': responses,
                'promoters': nps_data['promoter'],
                'passives': nps_data['passive'],
                'detractors': nps_data['detractor'],
                'complaints_open': Nps.search_count([('company_id', 'in', companies.ids),
                                                     ('is_complaint', '=', True),
                                                     ('complaint_resolved', '=', False)]),
            },
            'recall_due': len(self._dmag_recall_due(days_ahead=30, companies=companies)),
            'messages': dict(msg, total=sum(msg.values())),
            'call_tasks': tasks,
        }
