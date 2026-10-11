"""AI-11 – Gợi ý xếp lịch (tại chỗ, không cần AI) + mở rộng tạo nhanh bệnh nhân (địa chỉ từ CCCD)."""
from collections import Counter, defaultdict
from datetime import timedelta

import pytz

from odoo import api, fields, models

from odoo.addons.dmag_clinic_workspace.models.dmag_workspace import CLOSE_HOUR, OPEN_HOUR

AFTERNOON = (13 * 60 + 30, 16 * 60 + 30)
# Buổi trong ngày; giờ mở / đóng cửa thật lấy từ Lịch làm việc phòng khám (ctx['shifts'])
PARTS = {'morning': (0, 12 * 60), 'afternoon': (12 * 60, 17 * 60), 'evening': (17 * 60, 24 * 60)}
PART_LABEL = {'morning': 'buổi sáng', 'afternoon': 'buổi chiều', 'evening': 'buổi tối'}


def part_of(minutes):
    for key, (start, end) in PARTS.items():
        if start <= minutes < end:
            return key
    return 'evening'


def hhmm(minutes):
    return '%02d:%02d' % (minutes // 60, minutes % 60)


def rank_slots(slots, ctx, limit=4):
    """Xếp hạng khung giờ trống – hàm thuần (kiểm thử được, kết quả xác định).

    :param slots: ``[{'minutes': int, 'chairs': [id], 'doctors': [id]}]`` – giờ bắt đầu (phút từ 0:00),
        ghế trống, bác sĩ rảnh (đã lọc theo bác sĩ được chọn / phạm vi hành nghề)
    :param ctx: ``duration``, ``chair_busy {chair: [(start, end)]}``, ``doctor_load {doctor: phút}``,
        ``utilization {morning|afternoon|evening: 0..1}``, ``target`` (0..1), ``pref_minutes`` (giờ quen của
        khách hoặc None), ``pref_doctor``, ``names {('chair'|'doctor', id): tên}``
    :return: tối đa ``limit`` gợi ý ``{'minutes','time','chair_id','doctor_id','score','reasons'}``,
        các giờ cách nhau ≥ 30 phút để có lựa chọn đa dạng.
    """
    duration = ctx.get('duration') or 30
    shifts = ctx.get('shifts') or [(OPEN_HOUR * 60, CLOSE_HOUR * 60)]
    names = ctx.get('names') or {}
    loads = ctx.get('doctor_load') or {}
    max_load = max(list(loads.values()) + [1])
    target = ctx.get('target') or 0.75
    util = ctx.get('utilization') or {}
    scored = []
    for slot in slots:
        start = slot['minutes']
        end = start + duration
        if not slot.get('chairs'):
            continue
        # khoảng hở tính trong ca làm việc chứa khung giờ (không tính giờ nghỉ trưa / sau giờ đóng cửa)
        open_m, close_m = next(((a, b) for a, b in shifts if a <= start < b), shifts[0])
        # 1) Lấp khoảng trống: chọn ghế làm lịch liền mạch nhất
        best_chair, best_gap_score, best_gap_reason = None, None, None
        for chair in slot['chairs']:
            busy = (ctx.get('chair_busy') or {}).get(chair, [])
            prev_end = max([e for s, e in busy if open_m <= e <= start], default=None)
            next_start = min([s for s, e in busy if end <= s <= close_m], default=None)
            gap_before = start - (prev_end if prev_end is not None else open_m)
            gap_after = (next_start if next_start is not None else close_m) - end
            score, reason = 0.0, None
            joined_prev = prev_end is not None and gap_before == 0
            joined_next = next_start is not None and gap_after == 0
            if joined_prev and joined_next:
                score, reason = 4.0, 'Lấp kín khoảng trống trên %s' % names.get(('chair', chair), 'ghế')
            elif joined_prev or joined_next:
                score, reason = 2.5, 'Nối liền ca trên %s' % names.get(('chair', chair), 'ghế')
            for gap in (gap_before, gap_after):
                if 0 < gap < 30:
                    score -= 1.5  # tạo khoảng hở lẻ không dùng được
            if best_gap_score is None or score > best_gap_score:
                best_chair, best_gap_score, best_gap_reason = chair, score, reason
        score = best_gap_score
        reasons = [best_gap_reason] if best_gap_reason else []
        # 2) Buổi đang dưới mục tiêu công suất (ưu tiên buổi chiều)
        part = part_of(start)
        rate = util.get(part, 0.0)
        if rate < target:
            score += 2.0 * (target - rate) / target
            if part == 'afternoon' and AFTERNOON[0] <= start < AFTERNOON[1]:
                score += 1.0
                reasons.append('Buổi chiều đang vắng (%d%% ghế)' % round(rate * 100))
            elif target - rate > 0.25:
                reasons.append('%s còn trống nhiều (%d%%)' % (PART_LABEL[part].capitalize(), round(rate * 100)))
        # 3) Cân tải bác sĩ
        doctor = None
        doctors = slot.get('doctors') or []
        if doctors:
            pref = ctx.get('pref_doctor')
            doctor = min(doctors, key=lambda d: (0 if d == pref else 1, loads.get(d, 0), d)) \
                if pref in doctors and loads.get(pref, 0) < max_load else min(doctors, key=lambda d: (loads.get(d, 0), d))
            score += 1.5 * (1 - loads.get(doctor, 0) / max_load)
            if doctor == pref:
                score += 1.0
                reasons.append('%s – bác sĩ quen của khách' % names.get(('doctor', doctor), 'Bác sĩ'))
            elif len(doctors) > 1 and loads.get(doctor, 0) < max_load:
                reasons.append('%s đang ít ca (%d phút)' % (names.get(('doctor', doctor), 'Bác sĩ'), loads.get(doctor, 0)))
        # 4) Thói quen của khách
        pref_minutes = ctx.get('pref_minutes')
        if pref_minutes is not None:
            diff = abs(start - pref_minutes)
            score += 2.0 * max(0.0, 1 - diff / 180.0)
            if diff <= 60:
                reasons.append('Gần giờ khách hay đến (%s)' % hhmm(pref_minutes))
        score -= start / 100000.0  # hòa điểm → giờ sớm hơn
        scored.append({'minutes': start, 'time': hhmm(start), 'chair_id': best_chair, 'doctor_id': doctor,
                       'score': round(score, 3), 'reasons': reasons or ['Còn trống']})
    scored.sort(key=lambda s: (-s['score'], s['minutes']))
    picked = []
    for cand in scored:
        if all(abs(cand['minutes'] - p['minutes']) >= 30 for p in picked):
            picked.append(cand)
        if len(picked) >= limit:
            break
    return picked


class DmagWorkspace(models.AbstractModel):
    _inherit = 'dmag.workspace'

    # ------------------------------------------------------------------ AI-10: CCCD → địa chỉ
    @api.model
    def quick_create_patient(self, vals):
        street = (vals or {}).pop('street', False)
        res = super().quick_create_patient(vals)
        if street and res.get('id') and not res.get('duplicate'):
            self.env['res.partner'].browse(res['id']).write({'street': street})
        return res

    # ------------------------------------------------------------------ AI-11
    @api.model
    def _slot_context(self, day, duration, doctor_id=False, service_ids=None, patient_id=False):
        tz = self._tz()
        info = self._schedule_info()
        shifts = info.shifts(day) or [(OPEN_HOUR * 60, CLOSE_HOUR * 60)]
        start = self._local_to_utc(day, shifts[0][0] // 60, shifts[0][0] % 60)
        last = min(shifts[-1][1], 23 * 60 + 59)
        end = self._local_to_utc(day, last // 60, last % 60)
        visits = self.env['dmag.dental.visit'].sudo().search([
            ('company_id', 'in', self.env.companies.ids),
            ('state', 'in', ('draft', 'confirmed', 'arrived', 'in_chair')),
            ('scheduled_start', '<', end), ('scheduled_end', '>', start),
        ])
        chairs = self.env['dmag.dental.chair'].search([('company_id', 'in', self.env.companies.ids)])
        doctors = self.env['dmag.dental.practitioner'].search([
            ('role', '=', 'doctor'), ('company_id', 'in', self.env.companies.ids)])
        if doctor_id:
            doctors = doctors.filtered(lambda d: d.id == doctor_id)
        doctors = doctors.filtered(lambda d: d.works_on(day, info))  # ngày làm việc riêng của bác sĩ
        services = self.env['product.product'].browse(service_ids or [])
        if services:
            doctors = doctors.filtered(lambda d: not d._get_service_blockers(services))

        def local_minutes(dt):
            local = pytz.utc.localize(dt).astimezone(tz)
            return local.hour * 60 + local.minute

        chair_busy = defaultdict(list)
        doctor_busy = defaultdict(list)
        doctor_load = {d.id: 0 for d in doctors}
        part_busy = Counter()
        for visit in visits:
            s, e = local_minutes(max(visit.scheduled_start, start)), local_minutes(min(visit.scheduled_end, end))
            if e <= s:
                continue
            if visit.chair_id:
                chair_busy[visit.chair_id.id].append((s, e))
            if visit.doctor_id:
                doctor_busy[visit.doctor_id.id].append((s, e))
                if visit.doctor_id.id in doctor_load:
                    doctor_load[visit.doctor_id.id] += e - s
            for key, (ps, pe) in PARTS.items():
                part_busy[key] += max(0, min(e, pe) - max(s, ps))
        n_chairs = max(len(chairs), 1)
        open_minutes = {key: sum(max(0, min(b, pe) - max(a, ps)) for a, b in shifts) for key, (ps, pe) in PARTS.items()}
        utilization = {key: (part_busy[key] / float(open_minutes[key] * n_chairs)) if open_minutes[key] else 1.0
                       for key in PARTS}
        pref_minutes, pref_doctor = None, None
        if patient_id:
            past = self.env['dmag.dental.visit'].sudo().search([
                ('patient_id', '=', patient_id), ('state', '=', 'done')], limit=10, order='scheduled_start desc')
            if past:
                mins = sorted(local_minutes(v.scheduled_start) for v in past)
                pref_minutes = mins[len(mins) // 2]
                counts = Counter(v.doctor_id.id for v in past if v.doctor_id)
                pref_doctor = counts.most_common(1)[0][0] if counts else None
        names = {('chair', c.id): c.name for c in chairs}
        names.update({('doctor', d.id): ('%s %s' % (d.title or 'BS', d.name)).strip() for d in doctors})
        return {
            'duration': duration, 'chair_busy': dict(chair_busy), 'doctor_busy': dict(doctor_busy),
            'doctor_load': doctor_load, 'utilization': utilization,
            'target': self.env.company.dmag_ai_chair_target or 0.75,
            'pref_minutes': pref_minutes, 'pref_doctor': pref_doctor, 'names': names,
            'doctor_ids': doctors.ids, 'shifts': shifts,
        }

    @api.model
    def get_slot_suggestions(self, date, doctor_id=False, duration=30, service_ids=None, patient_id=False,
                             part_of_day='any', limit=4):
        """Gợi ý khung giờ tốt nhất (AI-11). Trả ``{'active', 'suggestions': [...], 'utilization', 'method'}``."""
        if not self.env['dmag.ai'].is_feature_active('AI-11'):
            return {'active': False, 'suggestions': []}
        day = fields.Date.from_string(date)
        duration = int(duration or 30)
        free = self.get_free_slots(date, False, duration)
        ctx = self._slot_context(day, duration, doctor_id, service_ids, patient_id)
        slots = []
        for slot in free:
            hour, minute = (int(x) for x in slot['time'].split(':'))
            start = hour * 60 + minute
            if part_of_day in PARTS and part_of(start) != part_of_day:
                continue
            end = start + duration
            doctors = [d for d in ctx['doctor_ids']
                       if not any(s < end and e > start for s, e in ctx['doctor_busy'].get(d, []))]
            if doctor_id and not doctors:
                continue
            slots.append({'minutes': start, 'chairs': slot['chairs'], 'doctors': doctors})
        ranked = rank_slots(slots, ctx, limit=limit)
        for item in ranked:
            item['doctor'] = ctx['names'].get(('doctor', item['doctor_id']), '') if item['doctor_id'] else ''
            item['chair'] = ctx['names'].get(('chair', item['chair_id']), '')
        return {
            'active': True,
            'suggestions': ranked,
            'utilization': {k: round(v, 2) for k, v in ctx['utilization'].items()},
            'target': ctx['target'],
            'method': 'Chấm điểm tại chỗ: lấp khoảng trống ghế, buổi dưới mục tiêu công suất (ưu tiên chiều), '
                      'cân tải bác sĩ, giờ & bác sĩ quen của khách. Không gửi dữ liệu ra ngoài.',
        }
