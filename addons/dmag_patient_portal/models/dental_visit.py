import uuid
from datetime import timedelta

import pytz

from odoo import _, api, fields, models
from odoo.tools import consteq, html2plaintext

TOKEN_VALIDITY_DAYS = 30
LOCAL_TZ = 'Asia/Ho_Chi_Minh'
PORTAL_STATES = ('draft', 'confirmed', 'arrived', 'in_chair', 'done', 'cancel', 'no_show')


def to_local(env, value):
    if not value:
        return False
    tz = pytz.timezone(env.context.get('tz') or env.user.tz or LOCAL_TZ)
    return pytz.utc.localize(fields.Datetime.to_datetime(value)).astimezone(tz)


def fmt_dt(env, value, pattern='%H:%M %d/%m/%Y'):
    local = to_local(env, value)
    return local.strftime(pattern) if local else ''


class DmagDentalVisit(models.Model):
    _name = 'dmag.dental.visit'
    _inherit = ['dmag.dental.visit', 'portal.mixin']

    dmag_portal_token_date = fields.Datetime('Token cổng bệnh nhân tạo lúc', readonly=True, copy=False)
    dmag_portal_url = fields.Char('Link "Nội dung khám hôm nay"', compute='_compute_dmag_portal_url',
                                  help='Link chia sẻ (không cần đăng nhập), hiệu lực 30 ngày – gửi kèm lời cảm ơn qua Zalo.')

    def _compute_access_url(self):
        super()._compute_access_url()
        for visit in self:
            visit.access_url = '/my/dental/visit/%s' % visit.id

    def _dmag_portal_token_valid(self):
        self.ensure_one()
        return bool(self.access_token and self.dmag_portal_token_date and
                    self.dmag_portal_token_date >= fields.Datetime.now() - timedelta(days=TOKEN_VALIDITY_DAYS))

    def _dmag_portal_ensure_token(self):
        """Token chia sẻ hiệu lực 30 ngày; hết hạn thì cấp token mới (link cũ vô hiệu)."""
        for visit in self.sudo():
            if not visit._dmag_portal_token_valid():
                visit.with_context(dmag_workflow=True).write({
                    'access_token': str(uuid.uuid4()),
                    'dmag_portal_token_date': fields.Datetime.now(),
                })
        return True

    def _portal_ensure_token(self):
        self._dmag_portal_ensure_token()
        return self.sudo().access_token

    def _dmag_portal_check_token(self, token):
        self.ensure_one()
        visit = self.sudo()
        return bool(token and visit.access_token and consteq(visit.access_token, token)
                    and visit._dmag_portal_token_valid())

    def _compute_dmag_portal_url(self):
        for visit in self:
            if not visit.id or not isinstance(visit.id, int):
                visit.dmag_portal_url = False
                continue
            visit._dmag_portal_ensure_token()
            sudo = visit.sudo()
            visit.dmag_portal_url = '%s/my/dental/visit/%s?access_token=%s' % (
                sudo.get_base_url(), visit.id, sudo.access_token)

    # ------------------------------------------------------------------ data for portal / API
    def _dmag_portal_card(self):
        """Tóm tắt một lượt khám (danh sách)."""
        self.ensure_one()
        visit = self.sudo()
        return {
            'id': visit.id,
            'name': visit.name,
            'patient_id': visit.patient_id.id,
            'patient': visit.patient_id.name,
            'state': visit.state,
            'state_label': dict(visit._fields['state'].selection).get(visit.state),
            'start': fields.Datetime.to_string(visit.scheduled_start),
            'start_display': fmt_dt(self.env, visit.scheduled_start),
            'doctor': visit.doctor_id.name or '',
            'branch': visit.company_id.name,
            'services': visit.service_ids.mapped('name'),
            'procedures': visit.procedure_ids.filtered(lambda p: p.state == 'done').mapped('display_name'),
        }

    def _dmag_portal_detail(self):
        """"Nội dung khám hôm nay" – ngôn ngữ dễ hiểu cho bệnh nhân."""
        self.ensure_one()
        visit = self.sudo()
        env = self.env
        procedures = visit.procedure_ids.filtered(lambda p: p.state == 'done')
        aftercare = []
        for product in procedures.mapped('product_id'):
            note = html2plaintext(product.aftercare_note or '').strip()
            if note:
                aftercare.append({'service': product.name, 'note': note})
        next_visit = visit.search([
            ('patient_id', '=', visit.patient_id.id), ('id', '!=', visit.id),
            ('state', 'in', ('draft', 'confirmed')),
            ('scheduled_start', '>', visit.scheduled_start)], order='scheduled_start asc', limit=1)
        prescriptions = []
        if 'dmag.prescription' in env:
            Rx = env['dmag.prescription'].sudo()
            domain = [('visit_id', '=', visit.id)]
            if 'state' in Rx._fields:
                domain.append(('state', 'not in', ('draft', 'cancelled', 'replaced')))
            for rx in Rx.search(domain):
                prescriptions.append({
                    'code': rx.name or '',
                    'date': fmt_dt(env, rx.date) if 'date' in rx._fields else '',
                })
        invoices = [{
            'name': inv.name,
            'date': inv.invoice_date and inv.invoice_date.strftime('%d/%m/%Y') or '',
            'amount_total': inv.amount_total,
            'amount_residual': inv.amount_residual,
            'payment_state': inv.payment_state,
            'paid': inv.payment_state in ('paid', 'in_payment'),
        } for inv in visit.invoice_ids.filtered(lambda m: m.state == 'posted')]
        diagnoses = [d.name for d in visit.diagnosis_ids]
        return dict(
            self._dmag_portal_card(),
            date_display=fmt_dt(env, visit.scheduled_start, '%d/%m/%Y'),
            doctor_title=(visit.doctor_id.title or '') if 'title' in visit.doctor_id._fields else '',
            complaint=visit.chief_complaint or '',
            diagnoses=diagnoses,
            assessment=visit.assessment or '',
            treatment_note=visit.treatment_note or '',
            procedure_lines=[{
                'name': p.display_name,
                'teeth': p.tooth_ids.mapped('code'),
                'quantity': p.quantity,
                'amount': p.amount,
            } for p in procedures],
            advice=visit.advice or '',
            aftercare=aftercare,
            next_visit={
                'id': next_visit.id, 'name': next_visit.name,
                'start': fields.Datetime.to_string(next_visit.scheduled_start),
                'start_display': fmt_dt(env, next_visit.scheduled_start),
                'doctor': next_visit.doctor_id.name or '',
                'services': next_visit.service_ids.mapped('name'),
            } if next_visit else False,
            prescriptions=prescriptions,
            invoices=invoices,
            amount_total=sum(i['amount_total'] for i in invoices),
            amount_due=sum(i['amount_residual'] for i in invoices),
            currency=visit.currency_id.symbol or '₫',
            signed=visit.record_state == 'signed',
        )

    @api.model
    def _dmag_portal_plan_dicts(self, patients):
        plans = self.env['dmag.treatment.plan'].sudo().search([
            ('patient_id', 'in', patients.ids), ('state', 'not in', ('draft', 'cancel'))])
        result = []
        for plan in plans:
            options = []
            for option in plan.option_ids:
                options.append({
                    'id': option.id,
                    'name': option.name,
                    'recommended': option.is_recommended,
                    'accepted': option == plan.accepted_option_id,
                    'summary': option.summary or '',
                    'amount_total': option.amount_total,
                    'estimated_visits': option.estimated_visits,
                    'deposit': option.deposit_amount,
                    'installment_months': option.installment_months,
                    'monthly_amount': option.monthly_amount,
                    'lines': [{
                        'name': line.display_name,
                        'phase': line.phase,
                        'amount': line.price_subtotal,
                        'done': line.state == 'done',
                    } for line in option.line_ids],
                })
            result.append({
                'id': plan.id,
                'name': plan.name,
                'title': plan.title or plan.name,
                'patient_id': plan.patient_id.id,
                'patient': plan.patient_id.name,
                'date': plan.date.strftime('%d/%m/%Y') if plan.date else '',
                'doctor': plan.doctor_id.name or '',
                'state': plan.state,
                'state_label': dict(plan._fields['state'].selection).get(plan.state),
                'progress': round(plan.progress or 0.0),
                'amount_accepted': plan.amount_accepted,
                'options': options,
                'currency': plan.currency_id.symbol or '₫',
            })
        return result

    @api.model
    def _dmag_portal_warranty_dicts(self, patients):
        if 'dmag.warranty.card' not in self.env:
            return False
        Card = self.env['dmag.warranty.card'].sudo()
        field = 'patient_id' if 'patient_id' in Card._fields else 'partner_id'
        result = []
        for card in Card.search([(field, 'in', patients.ids)]):
            get = lambda name: card[name] if name in card._fields else False  # noqa: E731
            end = get('end_date')
            state = get('state')
            result.append({
                'id': card.id,
                'name': card.name,
                'patient': card[field].name,
                'service': get('product_id').name if get('product_id') else '',
                'teeth': get('teeth_label') or '',
                'start_date': get('start_date').strftime('%d/%m/%Y') if get('start_date') else '',
                'end_date': end.strftime('%d/%m/%Y') if end else '',
                'days_left': get('days_left') or 0,
                'state': state or '',
                'state_label': dict(card._fields['state'].selection).get(state) if state else '',
                'conditions': get('conditions') or '',
            })
        return result
