from datetime import datetime, time, timedelta

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

from odoo.addons.dmag_dental_base.models.dmag_access import is_manager

OPEN_HOUR = 8
CLOSE_HOUR = 20
SLOT_STEP = 15


class DmagWorkspace(models.AbstractModel):
    """Dịch vụ dữ liệu cho giao diện vận hành (lễ tân, bác sĩ, chủ phòng khám)."""
    _name = 'dmag.workspace'
    _description = 'DMAG Workspace services'

    # ------------------------------------------------------------------ helpers
    @api.model
    def _tz(self):
        return pytz.timezone(self.env.user.tz or 'Asia/Ho_Chi_Minh')

    @api.model
    def _local_to_utc(self, day, hour, minute=0):
        local = self._tz().localize(datetime.combine(day, time(hour, minute)))
        return local.astimezone(pytz.utc).replace(tzinfo=None)

    # ------------------------------------------------------------------ patients
    @api.model
    def search_patients(self, query, limit=8):
        Partner = self.env['res.partner']
        if not query or len(query.strip()) < 2:
            return []
        q = query.strip()
        digits = ''.join(ch for ch in q if ch.isdigit())
        # Số điện thoại có thể lưu kèm khoảng trắng / dấu chấm: so khớp từng chữ số
        phone_pattern = '%'.join(digits) if len(digits) >= 4 else q
        partners = Partner.search([
            ('is_patient', '=', True),
            '|', '|', '|', ('name', 'ilike', q), ('patient_code', 'ilike', q),
            ('mobile', 'ilike', phone_pattern), ('phone', 'ilike', phone_pattern),
        ], limit=limit)
        return [{
            'id': p.id, 'name': p.name, 'code': p.patient_code or '', 'phone': p.mobile or p.phone or '',
            'age': p.age, 'alerts': [{'name': a.name, 'severity': a.severity} for a in p.patient_alert_ids],
        } for p in partners]

    @api.model
    def quick_create_patient(self, vals):
        """Tạo nhanh bệnh nhân tại quầy. Bắt buộc có đồng ý xử lý dữ liệu cá nhân (NĐ 13/2023)."""
        name = (vals.get('name') or '').strip()
        phone = (vals.get('phone') or '').strip()
        if not name or not phone:
            raise UserError(_('Cần nhập họ tên và số điện thoại.'))
        if not vals.get('consent'):
            raise UserError(_('Cần bệnh nhân đồng ý cho phép xử lý dữ liệu cá nhân (Nghị định 13/2023/NĐ-CP).'))
        digits = ''.join(ch for ch in phone if ch.isdigit())
        duplicate = self._find_by_phone(digits)
        if duplicate and not vals.get('force'):
            return {'duplicate': {'id': duplicate.id, 'name': duplicate.name, 'code': duplicate.patient_code}}
        partner = self.env['res.partner'].create({
            'name': name,
            'mobile': phone,
            'is_patient': True,
            'is_company': False,
            'birthdate': vals.get('birthdate') or False,
            'gender': vals.get('gender') or False,
            'citizen_id': vals.get('citizen_id') or False,
            'customer_source_id': vals.get('source_id') or False,
            'referrer_id': vals.get('referrer_id') or False,
            'allergy': vals.get('allergy') or False,
            'patient_alert_ids': [(6, 0, vals.get('alert_ids') or [])],
            'data_consent': True,
        })
        return {'id': partner.id, 'name': partner.name, 'code': partner.patient_code}

    @api.model
    def _find_by_phone(self, digits):
        """So khớp số điện thoại bỏ qua khoảng trắng / dấu chấm / mã quốc gia (9 số cuối)."""
        tail = digits[-9:]
        if len(tail) < 9:
            return self.env['res.partner']
        candidates = self.env['res.partner'].search([
            ('is_patient', '=', True), '|', ('mobile', 'ilike', tail[-3:]), ('phone', 'ilike', tail[-3:])])
        for partner in candidates:
            for number in (partner.mobile, partner.phone):
                if number and ''.join(ch for ch in number if ch.isdigit()).endswith(tail):
                    return partner
        return self.env['res.partner']

    @api.model
    def get_booking_catalog(self):
        return {
            'doctors': [{'id': d.id, 'name': d.name, 'title': d.title or '', 'color': d.color,
                         'level': d.clinical_level_id.name or ''}
                        for d in self.env['dmag.dental.practitioner'].search([('role', '=', 'doctor')])],
            'chairs': [{'id': c.id, 'name': c.name, 'room': c.room or ''}
                       for c in self.env['dmag.dental.chair'].search([])],
            'services': [{'id': p.id, 'name': p.name, 'duration': p.dental_duration, 'price': p.lst_price,
                          'category': p.dental_category or 'other', 'heavy': p.dental_complexity == 'heavy'}
                         for p in self.env['product.product'].search([('is_dental_service', '=', True)])],
            'sources': [{'id': s.id, 'name': s.name, 'referral': s.is_referral}
                        for s in self.env['dmag.customer.source'].search([])],
            'alerts': [{'id': a.id, 'name': a.name, 'severity': a.severity}
                       for a in self.env['dmag.patient.alert'].search([])],
        }

    # ------------------------------------------------------------------ slots
    @api.model
    def get_free_slots(self, date, doctor_id=False, duration=30):
        """Khung giờ trống trong ngày (giờ địa phương) theo bác sĩ và ghế.

        Trả về [{'time': 'HH:MM', 'chairs': [chair_id…], 'doctor_free': bool, 'afternoon': bool}]
        – ưu tiên hiển thị khung chiều (13:30–16:30) để lấp ghế trống.
        """
        day = fields.Date.from_string(date)
        duration = int(duration or 30)
        start = self._local_to_utc(day, OPEN_HOUR)
        end = self._local_to_utc(day, CLOSE_HOUR)
        visits = self.env['dmag.dental.visit'].search([
            ('state', 'in', ('draft', 'confirmed', 'arrived', 'in_chair')),
            ('scheduled_start', '<', end), ('scheduled_end', '>', start),
        ])
        chairs = self.env['dmag.dental.chair'].search([])
        now = fields.Datetime.now()
        slots = []
        cursor = start
        while cursor + timedelta(minutes=duration) <= end:
            slot_end = cursor + timedelta(minutes=duration)
            overlapping = visits.filtered(lambda v: v.scheduled_start < slot_end and v.scheduled_end > cursor)
            busy_chairs = set(overlapping.mapped('chair_id').ids)
            free_chairs = [c.id for c in chairs if c.id not in busy_chairs]
            doctor_free = not doctor_id or not overlapping.filtered(lambda v: v.doctor_id.id == doctor_id)
            local = pytz.utc.localize(cursor).astimezone(self._tz())
            if cursor > now and free_chairs:
                minutes = local.hour * 60 + local.minute
                slots.append({
                    'time': local.strftime('%H:%M'),
                    'chairs': free_chairs,
                    'doctor_free': bool(doctor_free),
                    'afternoon': 13 * 60 + 30 <= minutes < 16 * 60 + 30,
                })
            cursor += timedelta(minutes=SLOT_STEP)
        return slots

    @api.model
    def quick_book(self, vals):
        """Đặt lịch nhanh: bệnh nhân + dịch vụ + bác sĩ + ngày giờ (địa phương)."""
        day = fields.Date.from_string(vals['date'])
        hour, minute = (int(x) for x in vals['time'].split(':'))
        services = vals.get('service_ids') or []
        visit = self.env['dmag.dental.visit'].create({
            'patient_id': vals['patient_id'],
            'doctor_id': vals.get('doctor_id') or False,
            'chair_id': vals.get('chair_id') or False,
            'service_ids': [(6, 0, services)],
            'scheduled_start': self._local_to_utc(day, hour, minute),
            'reason': vals.get('reason') or False,
            'source_id': vals.get('source_id') or False,
        })
        if vals.get('confirm'):
            visit.action_confirm()
        return {'id': visit.id, 'name': visit.name}

    # ------------------------------------------------------------------ payment
    @api.model
    def get_payment_panel(self, visit_id):
        visit = self.env['dmag.dental.visit'].browse(visit_id)
        visit.check_access_rights('read')
        lines = []
        for proc in visit.procedure_ids.filtered(lambda p: p.state == 'done'):
            lines.append({'name': proc.display_name, 'amount': proc.amount})
        return {
            'visit_id': visit.id,
            'patient': visit.patient_id.name,
            'code': visit.patient_id.patient_code or '',
            'amount_due': visit.amount_due,
            'payment_status': visit.payment_status,
            'lines': lines,
            'sepay': 'dmag.payment.request' in self.env and hasattr(visit, 'get_payment_qr'),
        }

    # ------------------------------------------------------------------ owner cockpit
    @api.model
    def get_owner_cockpit(self, date_from=False, date_to=False):
        """Buồng lái chủ phòng khám: số liệu điều hành trong kỳ (mặc định tháng hiện tại)."""
        if not is_manager(self.env):
            raise AccessError(_('Buồng lái chỉ dành cho Quản lý phòng khám / Giám đốc.'))
        today = fields.Date.context_today(self)
        d_from = fields.Date.from_string(date_from) if date_from else today.replace(day=1)
        d_to = fields.Date.from_string(date_to) if date_to else today
        start = self._local_to_utc(d_from, 0)
        end = self._local_to_utc(d_to + timedelta(days=1), 0)
        Visit = self.env['dmag.dental.visit'].sudo()
        company_ids = self.env.companies.ids
        visits = Visit.search([('company_id', 'in', company_ids),
                               ('scheduled_start', '>=', start), ('scheduled_end', '<', end)])
        done = visits.filtered(lambda v: v.state == 'done')
        booked = visits.filtered(lambda v: v.state != 'cancel')
        no_show = visits.filtered(lambda v: v.state == 'no_show')
        waits = [v.wait_minutes for v in done if v.checkin_time and v.chair_time]
        procedures = self.env['dmag.dental.procedure'].sudo().search([
            ('visit_id', 'in', done.ids), ('state', '=', 'done')])
        revenue = sum(procedures.mapped('amount'))
        moves = self.env['account.move'].sudo().search([
            ('company_id', 'in', company_ids), ('move_type', '=', 'out_invoice'), ('state', '=', 'posted'),
            ('invoice_date', '>=', d_from), ('invoice_date', '<=', d_to)])
        collected = sum(m.amount_total - m.amount_residual for m in moves)
        receivable = sum(moves.mapped('amount_residual'))
        plans = self.env['dmag.treatment.plan'].sudo().search([
            ('company_id', 'in', company_ids), ('date', '>=', d_from), ('date', '<=', d_to)])
        presented = plans.filtered(lambda p: p.state != 'draft')
        accepted = plans.filtered(lambda p: p.state in ('accepted', 'in_progress', 'done'))

        # Công suất ghế buổi chiều (13:30–16:30)
        chairs = self.env['dmag.dental.chair'].sudo().search([('company_id', 'in', company_ids)])
        days = (d_to - d_from).days + 1
        capacity = len(chairs) * days * 180
        afternoon_minutes = 0
        tz = self._tz()
        for v in booked:
            local_start = pytz.utc.localize(v.scheduled_start).astimezone(tz)
            local_end = pytz.utc.localize(v.scheduled_end).astimezone(tz)
            win_start = local_start.replace(hour=13, minute=30, second=0)
            win_end = local_start.replace(hour=16, minute=30, second=0)
            overlap = (min(local_end, win_end) - max(local_start, win_start)).total_seconds() / 60
            afternoon_minutes += max(overlap, 0)

        # Bác sĩ phụ đảm nhận (bậc < 3)
        by_doctor = {}
        for p in procedures:
            key = p.doctor_id.name or _('Chưa rõ')
            by_doctor.setdefault(key, {'name': key, 'revenue': 0.0, 'count': 0,
                                       'level': p.doctor_id.clinical_level_id.level or 0})
            by_doctor[key]['revenue'] += p.amount
            by_doctor[key]['count'] += 1
        associate = sum(d['count'] for d in by_doctor.values() if d['level'] and d['level'] < 3)

        # Doanh thu theo nhóm dịch vụ
        categories = dict(self.env['product.template']._fields['dental_category'].selection)
        by_category = {}
        for p in procedures:
            cat = categories.get(p.product_id.dental_category, _('Khác'))
            by_category[cat] = by_category.get(cat, 0.0) + p.amount

        # Doanh thu theo ngày (giờ địa phương)
        by_day = {}
        for p in procedures:
            d = pytz.utc.localize(p.visit_id.scheduled_start).astimezone(tz).date().isoformat()
            by_day[d] = by_day.get(d, 0.0) + p.amount
        series = []
        cursor = d_from
        while cursor <= d_to:
            series.append({'date': cursor.isoformat(), 'revenue': by_day.get(cursor.isoformat(), 0.0)})
            cursor += timedelta(days=1)

        sources = {}
        for v in done.filtered('is_new_patient'):
            key = v.patient_id.customer_source_id.name or _('Không rõ')
            sources[key] = sources.get(key, 0) + 1

        result = {
            'period': {'from': d_from.isoformat(), 'to': d_to.isoformat()},
            'kpis': {
                'revenue': revenue,
                'collected': collected,
                'receivable': receivable,
                'visits_done': len(done),
                'new_patients': len(done.filtered('is_new_patient')),
                'no_show_rate': (100.0 * len(no_show) / len(booked)) if booked else 0.0,
                'avg_wait': (sum(waits) / len(waits)) if waits else 0.0,
                'plan_acceptance': (100.0 * len(accepted) / len(presented)) if presented else 0.0,
                'afternoon_utilization': (100.0 * afternoon_minutes / capacity) if capacity else 0.0,
                'associate_share': (100.0 * associate / len(procedures)) if procedures else 0.0,
                'avg_ticket': (revenue / len(done)) if done else 0.0,
            },
            'targets': {'afternoon_utilization': 65, 'associate_share': 50, 'avg_wait': 15,
                        'plan_acceptance': 60, 'material_ratio': 22},
            'series': series,
            'by_doctor': sorted(by_doctor.values(), key=lambda d: -d['revenue']),
            'by_category': sorted([{'name': k, 'revenue': v} for k, v in by_category.items()],
                                  key=lambda d: -d['revenue']),
            'sources': sorted([{'name': k, 'count': v} for k, v in sources.items()], key=lambda d: -d['count']),
            'extras': {},
        }
        result['extras'] = self._cockpit_extras(d_from, d_to)
        return result

    @api.model
    def _cockpit_extras(self, d_from, d_to):
        """Số liệu từ các module tùy chọn (pháp chế, vật tư, labo, CSKH) nếu đã cài."""
        extras = {}
        providers = [
            ('compliance', 'dmag.compliance.doc', 'get_compliance_status', ()),
            ('material', 'dmag.service.bom', 'get_material_kpis', (d_from, d_to)),
            ('lab', 'dmag.lab.order', 'get_lab_kpis', (d_from, d_to)),
            ('journey', 'dmag.journey.rule', 'get_journey_dashboard', ()),
        ]
        for key, model, method, args in providers:
            if model in self.env and hasattr(self.env[model], method):
                try:
                    extras[key] = getattr(self.env[model].sudo(), method)(*args)
                except Exception as exc:  # noqa: BLE001 – không để một module tùy chọn làm hỏng buồng lái
                    extras[key] = {'error': str(exc)}
        return extras
