from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.dmag_ai_customer.models.cccd import SAMPLE_QR, parse_cccd_qr
from odoo.addons.dmag_ai_customer.models.dmag_ai_noshow import (explain, feature_vector, heuristic_model, predict,
                                                              train_logreg)
from odoo.addons.dmag_ai_customer.models.dmag_workspace import rank_slots

from .common import AiCustomerCase


def _fixture_rows():
    """Dữ liệu cố định: khách chưa xác nhận + từng không đến + đặt trước lâu → không đến."""
    raws, labels = [], []
    for i in range(120):
        risky = i % 4 == 0
        raw = {
            'lead_days': 25 if risky else 2 + i % 3, 'prior_visits': 4 if i % 3 else 0,
            'prior_noshow': 2 if risky and i % 3 else 0, 'weekday': 5 if risky else i % 5, 'hour': 18 if risky else 10,
            'confirmed': not risky, 'light': risky, 'online': risky and i % 8 == 0,
        }
        raws.append(raw)
        labels.append(1 if (risky and i % 12 != 4) else (1 if i % 29 == 0 else 0))
    return raws, labels


@tagged('post_install', '-at_install')
class TestNoShow(AiCustomerCase):
    """AI-08 – hồi quy logistic thuần Python, xác định, có giải thích."""

    def test_logreg_deterministic_and_discriminative(self):
        raws, labels = _fixture_rows()
        rows = [feature_vector(r) for r in raws]
        m1 = train_logreg(rows, labels)
        m2 = train_logreg(rows, labels)
        self.assertEqual(m1['coef'], m2['coef'], 'Huấn luyện xác định (không ngẫu nhiên)')
        self.assertGreater(m1['auc'], 0.85)
        risky = feature_vector({'lead_days': 30, 'prior_visits': 5, 'prior_noshow': 3, 'weekday': 5, 'hour': 18,
                                'confirmed': False, 'light': True})
        safe = feature_vector({'lead_days': 1, 'prior_visits': 6, 'prior_noshow': 0, 'weekday': 2, 'hour': 10,
                               'confirmed': True, 'light': False})
        self.assertGreater(predict(m1, risky), 0.4)
        self.assertLess(predict(m1, safe), 0.15)
        self.assertGreater(predict(m1, risky), 3 * predict(m1, safe))
        self.assertGreater(m1['coef']['unconfirmed'], 0)
        reasons = explain(m1, risky, {'lead_days': 30, 'prior_visits': 5, 'prior_noshow': 3})
        self.assertTrue(reasons)
        self.assertTrue(any('xác nhận' in r or 'không đến' in r or 'Đặt trước' in r for r in reasons))

    def test_heuristic_fallback(self):
        model = heuristic_model()
        new_unconfirmed = feature_vector({'lead_days': 14, 'prior_visits': 0, 'weekday': 6, 'hour': 18, 'confirmed': False})
        regular_confirmed = feature_vector({'lead_days': 2, 'prior_visits': 8, 'prior_noshow': 0, 'weekday': 1, 'hour': 10,
                                            'confirmed': True})
        self.assertGreater(predict(model, new_unconfirmed), predict(model, regular_confirmed))
        record = self.env['dmag.ai.noshow.model'].train()
        # cơ sở dữ liệu thử ít lượt không đến → bộ trọng số kinh nghiệm, vẫn chấm điểm được
        self.assertIn(record.method, ('heuristic', 'logreg'))
        self.assertTrue(record.method_text)

    def test_visit_scored_and_card_badge(self):
        self.company.dmag_ai_noshow_threshold = 0.05
        visit = self.env['dmag.dental.visit'].create({
            'patient_id': self.patient.id, 'scheduled_start': fields.Datetime.now() + timedelta(days=10, hours=2),
            'service_ids': [(6, 0, self.scaling.ids)]})
        self.assertTrue(visit.dmag_noshow_scored_at)
        self.assertGreater(visit.dmag_noshow_risk, 0)
        card = visit._workspace_card()
        self.assertTrue(card['noshow']['show'])
        self.assertIn('Gọi', card['noshow']['suggestion'])
        self.assertTrue(card['noshow']['method'])
        before = visit.dmag_noshow_risk
        visit.action_confirm()
        self.assertLess(visit.dmag_noshow_risk, before, 'Đã xác nhận → nguy cơ giảm')
        self.env.ref('dmag_ai_core.feature_ai_08').active = False
        self.assertFalse(visit._workspace_card()['noshow'])

    def test_learns_from_clinic_history(self):
        """Đủ dữ liệu → mô hình học từ lịch sử phòng khám (không đến khi chưa xác nhận)."""
        Visit = self.env['dmag.dental.visit'].with_context(dmag_ai_no_score=True, tracking_disable=False, mail_notrack=False)
        start = fields.Datetime.now() - timedelta(days=60)
        patients = self.env['res.partner'].create([{'name': 'BN lịch sử %s' % i, 'is_patient': True} for i in range(12)])
        for i in range(60):
            visit = Visit.create({'patient_id': patients[i % 12].id,
                                  'scheduled_start': start + timedelta(days=i // 2, hours=(i % 2) * 3),
                                  'chair_id': self.chairs[i % len(self.chairs)].id})
            if i % 5 == 0:
                visit.action_no_show()
            else:
                visit.action_confirm()
                visit.action_check_in()
                visit.action_start(chair_id=visit.chair_id.id)
                visit.action_done()
        model = self.env['dmag.ai.noshow.model'].train()
        self.assertEqual(model.method, 'logreg')
        self.assertGreaterEqual(model.n_samples, 60)
        self.assertGreater(model._params()['coef']['unconfirmed'], 0)


@tagged('post_install', '-at_install')
class TestCccd(AiCustomerCase):
    """AI-10 – đọc QR CCCD gắn chip."""

    def test_parse_sample(self):
        data = parse_cccd_qr(SAMPLE_QR)
        self.assertEqual(data['citizen_id'], '079190001234')
        self.assertEqual(data['old_id'], '025123456')
        self.assertEqual(data['name'], 'Nguyễn Thị Minh Anh')
        self.assertEqual(str(data['birthdate']), '1990-08-15')
        self.assertEqual(data['gender'], 'female')
        self.assertIn('Quận 1', data['address'])
        self.assertEqual(str(data['issue_date']), '2021-04-20')

    def test_parse_variants_and_errors(self):
        data = parse_cccd_qr('001099012345||Trần  Văn   Nam|01011999|Nam|Hà Nội|\n')
        self.assertEqual(data['name'], 'Trần Văn Nam')
        self.assertEqual(data['gender'], 'male')
        self.assertFalse(data['old_id'])
        self.assertFalse(data['issue_date'])
        for bad in ('', 'abc', '12345|x|Tên|01011999|Nam|HN|01012020', '001099012345||Tên|31021999|Nam|HN|01012020',
                    '001099012345|||01011999|Nam|HN'):
            with self.assertRaises(ValueError):
                parse_cccd_qr(bad)

    def test_rpc_parse_and_duplicate(self):
        res = self.env['dmag.ai.cccd'].parse_qr(SAMPLE_QR)
        self.assertEqual(res['birthdate'], '1990-08-15')
        self.assertFalse(res['existing'])
        partner = self.env['res.partner'].create({'name': 'X', 'is_patient': True, 'citizen_id': '079190001234'})
        self.assertEqual(self.env['dmag.ai.cccd'].parse_qr(SAMPLE_QR)['existing']['id'], partner.id)
        with self.assertRaises(UserError):
            self.env['dmag.ai.cccd'].parse_qr('không phải QR')

    def test_quick_create_with_address(self):
        res = self.env['dmag.workspace'].quick_create_patient({
            'name': 'Nguyễn Thị Minh Anh', 'phone': '0977000111', 'consent': True, 'citizen_id': '079190001234',
            'birthdate': '1990-08-15', 'gender': 'female', 'street': '123 Nguyễn Thị Minh Khai, Quận 1'})
        partner = self.env['res.partner'].browse(res['id'])
        self.assertEqual(partner.street, '123 Nguyễn Thị Minh Khai, Quận 1')
        self.assertEqual(partner.citizen_id, '079190001234')


@tagged('post_install', '-at_install')
class TestSlotRanking(AiCustomerCase):
    """AI-11 – xếp hạng giờ trống tại chỗ."""

    def _ctx(self, **kw):
        ctx = {'duration': 30, 'chair_busy': {1: [(9 * 60, 10 * 60)], 2: []}, 'doctor_load': {10: 240, 11: 30},
               'utilization': {'morning': 0.9, 'afternoon': 0.2, 'evening': 0.5}, 'target': 0.75,
               'pref_minutes': None, 'pref_doctor': None,
               'names': {('chair', 1): 'Ghế 1', ('chair', 2): 'Ghế 2', ('doctor', 10): 'BS A', ('doctor', 11): 'BS B'}}
        ctx.update(kw)
        return ctx

    def test_gap_fill_beats_isolated(self):
        slots = [{'minutes': 10 * 60, 'chairs': [1, 2], 'doctors': []},   # nối liền ca 9:00–10:00 trên Ghế 1
                 {'minutes': 11 * 60, 'chairs': [1, 2], 'doctors': []}]
        ranked = rank_slots(slots, self._ctx(utilization={'morning': 0.5, 'afternoon': 0.5, 'evening': 0.5}))
        self.assertEqual(ranked[0]['time'], '10:00')
        self.assertEqual(ranked[0]['chair_id'], 1)
        self.assertIn('Nối liền', ranked[0]['reasons'][0])

    def test_afternoon_doctor_balance_and_preference(self):
        slots = [{'minutes': 10 * 60 + 30, 'chairs': [2], 'doctors': [10, 11]},
                 {'minutes': 14 * 60, 'chairs': [2], 'doctors': [10, 11]},
                 {'minutes': 14 * 60 + 15, 'chairs': [2], 'doctors': [10, 11]},
                 {'minutes': 17 * 60 + 30, 'chairs': [2], 'doctors': [10]}]
        ranked = rank_slots(slots, self._ctx())
        self.assertEqual(ranked[0]['time'], '14:00', 'Ưu tiên buổi chiều đang vắng')
        self.assertEqual(ranked[0]['doctor_id'], 11, 'Cân tải: bác sĩ ít ca')
        self.assertTrue(any('chiều' in r for r in ranked[0]['reasons']))
        times = [r['minutes'] for r in ranked]
        self.assertNotIn(14 * 60 + 15, times, 'Các gợi ý cách nhau ≥ 30 phút')
        # Thói quen của khách: hay đến 17:30 với BS A
        ranked = rank_slots(slots, self._ctx(pref_minutes=17 * 60 + 30, pref_doctor=10,
                                             utilization={'morning': 0.5, 'afternoon': 0.5, 'evening': 0.5}))
        self.assertEqual(ranked[0]['time'], '17:30')
        self.assertTrue(any('quen' in r for r in ranked[0]['reasons']))
        self.assertEqual(rank_slots(slots, self._ctx()), rank_slots(slots, self._ctx()), 'Xác định')

    def test_rpc_suggestions(self):
        res = self.env['dmag.workspace'].get_slot_suggestions(self.tomorrow.isoformat(), False, 30, self.scaling.ids,
                                                              self.patient.id)
        self.assertTrue(res['active'])
        self.assertLessEqual(len(res['suggestions']), 4)
        self.assertTrue(res['suggestions'])
        mins = sorted(s['minutes'] for s in res['suggestions'])
        self.assertTrue(all(b - a >= 30 for a, b in zip(mins, mins[1:])))
        self.assertTrue(all(s['reasons'] for s in res['suggestions']))
        self.env.ref('dmag_ai_core.feature_ai_11').active = False
        self.assertFalse(self.env['dmag.workspace'].get_slot_suggestions(self.tomorrow.isoformat())['active'])
