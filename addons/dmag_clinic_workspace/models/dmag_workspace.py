from datetime import datetime, time, timedelta

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import UserError


# Giới hạn ngoài cùng (dự phòng) – giờ làm việc thật lấy từ Lịch làm việc phòng khám (dmag.clinic.schedule)
OPEN_HOUR = 8
CLOSE_HOUR = 20
SLOT_STEP = 15


class DmagWorkspace(models.AbstractModel):
    """Dịch vụ dữ liệu cho giao diện vận hành (lễ tân, bác sĩ).

    Bảng điều hành mục tiêu cho chủ phòng khám nằm ở module ``dmag_dental_goals``.
    """
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
    def _schedule_info(self):
        return self.env['dmag.clinic.schedule'].get_info(self.env.company)

    @api.model
    def get_day_info(self, date):
        """Ngày mở cửa / nghỉ và các ca (Lịch làm việc phòng khám) cho hộp thoại đặt lịch."""
        return self.env['dmag.clinic.schedule'].get_day_info(date)

    @api.model
    def get_free_slots(self, date, doctor_id=False, duration=30):
        """Khung giờ trống trong ngày (giờ địa phương) theo Lịch làm việc phòng khám, bác sĩ và ghế.

        Chỉ trả các giờ nằm TRỌN trong một ca làm việc (không vắt qua giờ nghỉ trưa / giờ đóng cửa); ngày nghỉ lễ,
        thứ nghỉ → rỗng. Bác sĩ có ngày làm việc riêng mà không làm ngày này → ``doctor_free`` = False.
        Trả về [{'time': 'HH:MM', 'chairs': [chair_id…], 'doctor_free': bool, 'afternoon': bool}]
        – ``afternoon`` đánh dấu khung chiều (13:30–16:30) cần lấp ghế.
        """
        day = fields.Date.from_string(date)
        duration = int(duration or 30)
        info = self._schedule_info()
        shifts = info.shifts(day)
        if not shifts:
            return []
        step = info.slot_step or SLOT_STEP
        start = self._local_to_utc(day, shifts[0][0] // 60, shifts[0][0] % 60)
        end = self._local_to_utc(day, min(shifts[-1][1], 23 * 60 + 59) // 60, min(shifts[-1][1], 23 * 60 + 59) % 60)
        visits = self.env['dmag.dental.visit'].search([
            ('state', 'in', ('draft', 'confirmed', 'arrived', 'in_chair')),
            ('scheduled_start', '<', end), ('scheduled_end', '>', start),
        ])
        chairs = self.env['dmag.dental.chair'].search([])
        doctor = self.env['dmag.dental.practitioner'].browse(doctor_id) if doctor_id else None
        doctor_works = not doctor or doctor.works_on(day, info)
        now = fields.Datetime.now()
        slots = []
        for shift_start, shift_end in shifts:
            minute = shift_start
            while minute + duration <= shift_end:
                cursor = self._local_to_utc(day, minute // 60, minute % 60)
                slot_end = cursor + timedelta(minutes=duration)
                overlapping = visits.filtered(lambda v: v.scheduled_start < slot_end and v.scheduled_end > cursor)
                busy_chairs = set(overlapping.mapped('chair_id').ids)
                free_chairs = [c.id for c in chairs if c.id not in busy_chairs]
                doctor_free = doctor_works and (
                    not doctor_id or not overlapping.filtered(lambda v: v.doctor_id.id == doctor_id))
                if cursor > now and free_chairs:
                    slots.append({
                        'time': '%02d:%02d' % (minute // 60, minute % 60),
                        'chairs': free_chairs,
                        'doctor_free': bool(doctor_free),
                        'afternoon': 13 * 60 + 30 <= minute < 16 * 60 + 30,
                    })
                minute += step
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
