import json
import re
from datetime import timedelta
from urllib.parse import urlparse

from odoo import fields
from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestPatientPortal(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        portal_group = env.ref('base.group_portal')
        Partner = env['res.partner']
        cls.pa = Partner.create({'name': 'Nguyễn Văn An', 'is_patient': True, 'mobile': '0911000001',
                                 'email': 'an@dmag.test'})
        cls.child = Partner.create({'name': 'Nguyễn Bé Con', 'is_patient': True})
        cls.pb = Partner.create({'name': 'Trần Thị Bình', 'is_patient': True, 'mobile': '0911000002',
                                 'email': 'binh@dmag.test'})
        family = env['dmag.patient.family'].create({'name': 'Nhà An', 'head_id': cls.pa.id})
        (cls.pa | cls.child).write({'dental_family_id': family.id})
        Users = env['res.users'].with_context(no_reset_password=True)
        cls.user_a = Users.create({'name': cls.pa.name, 'login': 'portal_an', 'password': 'portal_an',
                                   'partner_id': cls.pa.id, 'groups_id': [(6, 0, portal_group.ids)]})
        cls.user_b = Users.create({'name': cls.pb.name, 'login': 'portal_binh', 'password': 'portal_binh',
                                   'partner_id': cls.pb.id, 'groups_id': [(6, 0, portal_group.ids)]})
        cls.service = env['product.product'].create({
            'name': 'Cạo vôi Portal', 'is_dental_service': True, 'list_price': 300000, 'dental_requires_tooth': False,
            'aftercare_note': '<p>Không ăn uống đồ nóng trong 2 giờ.</p>'})
        cls.chair = env['dmag.dental.chair'].create({'name': 'Ghế Portal'})
        start = fields.Datetime.now().replace(microsecond=0) - timedelta(days=1)
        cls.visit_a = cls._done_visit(cls.pa, start)
        cls.visit_child = cls._done_visit(cls.child, start + timedelta(hours=1))
        cls.visit_b = cls._done_visit(cls.pb, start + timedelta(hours=2))

    @classmethod
    def _done_visit(cls, patient, start):
        visit = cls.env['dmag.dental.visit'].create({
            'patient_id': patient.id, 'scheduled_start': start, 'chair_id': cls.chair.id,
            'service_ids': [(6, 0, cls.service.ids)], 'assessment': 'Viêm nướu nhẹ',
            'advice': 'Chải răng 2 lần/ngày',
        })
        visit.action_check_in()
        visit.action_start()
        cls.env['dmag.dental.procedure'].add_from_workspace(visit.id, cls.service.id)
        visit.action_done()
        return visit

    def _path(self, url):
        parsed = urlparse(url)
        return '%s?%s' % (parsed.path, parsed.query)

    # ------------------------------------------------------------------ portal
    def test_portal_access_isolation(self):
        self.authenticate('portal_an', 'portal_an')
        res = self.url_open('/my/dental/visit/%s' % self.visit_a.id)
        self.assertEqual(res.status_code, 200)
        self.assertIn('Viêm nướu nhẹ', res.text)
        self.assertIn('Không ăn uống đồ nóng', res.text)
        # Chủ hộ xem được lượt khám của con
        res = self.url_open('/my/dental/visit/%s' % self.visit_child.id)
        self.assertEqual(res.status_code, 200)
        self.assertIn('Nguyễn Bé Con', res.text)
        # Không xem được bệnh nhân khác
        res = self.url_open('/my/dental/visit/%s' % self.visit_b.id)
        self.assertEqual(res.status_code, 403)
        self.assertNotIn('Trần Thị Bình', res.text)
        res = self.url_open('/my/dental/visits')
        self.assertEqual(res.status_code, 200)
        self.assertIn(self.visit_a.name, res.text)
        self.assertIn(self.visit_child.name, res.text)
        self.assertNotIn(self.visit_b.name, res.text)
        for page in ('/my/dental', '/my/dental/plans', '/my/dental/warranty', '/my/dental/loyalty'):
            self.assertEqual(self.url_open(page).status_code, 200, page)
        res = self.url_open('/my/dental/visits?patient_id=%s' % self.pb.id)
        self.assertEqual(res.status_code, 403)

        # Con (không phải chủ hộ) không xem được lượt khám của bố/mẹ
        self.authenticate('portal_binh', 'portal_binh')
        res = self.url_open('/my/dental/visit/%s' % self.visit_a.id)
        self.assertEqual(res.status_code, 403)
        res = self.url_open('/my/dental/visits')
        self.assertIn(self.visit_b.name, res.text)
        self.assertNotIn(self.visit_a.name, res.text)

    def test_token_link_and_expiry(self):
        url = self.visit_a.dmag_portal_url
        self.assertTrue(url and 'access_token=' in url)
        self.assertEqual(self.visit_a.dmag_portal_url, url, 'Token ổn định trong thời hạn')
        res = self.url_open(self._path(url))
        self.assertEqual(res.status_code, 200)
        self.assertIn('Viêm nướu nhẹ', res.text)
        # Sai token
        res = self.url_open('/my/dental/visit/%s?access_token=sai-token' % self.visit_a.id)
        self.assertEqual(res.status_code, 403)
        # Token của lượt khám này không mở được lượt khám khác
        token = self.visit_a.sudo().access_token
        res = self.url_open('/my/dental/visit/%s?access_token=%s' % (self.visit_b.id, token))
        self.assertEqual(res.status_code, 403)
        # Hết hạn sau 30 ngày
        self.visit_a.sudo().write({'dmag_portal_token_date': fields.Datetime.now() - timedelta(days=31)})
        res = self.url_open(self._path(url))
        self.assertEqual(res.status_code, 403)
        self.visit_a.invalidate_recordset()
        new_url = self.visit_a.dmag_portal_url
        self.assertNotEqual(new_url, url)
        self.assertEqual(self.url_open(self._path(new_url)).status_code, 200)

    # ------------------------------------------------------------------ booking
    def _csrf(self):
        res = self.url_open('/dental/booking')
        self.assertEqual(res.status_code, 200)
        return re.search(r'name="csrf_token" value="([^"]+)"', res.text).group(1)

    def _booking_data(self, **kw):
        tomorrow = (fields.Date.today() + timedelta(days=2)).isoformat()
        data = {'name': 'Lê Khách Mới', 'phone': '0987 654 321', 'date': tomorrow, 'time': '09:30',
                'service_id': str(self.service.id), 'company_id': str(self.env.company.id),
                'note': 'Đau răng hàm', 'consent': 'on'}
        data.update(kw)
        return data

    def test_booking_requires_consent_and_creates_draft(self):
        Visit = self.env['dmag.dental.visit']
        csrf = self._csrf()
        data = self._booking_data()
        data.pop('consent')
        res = self.url_open('/dental/booking', data=dict(data, csrf_token=csrf))
        self.assertEqual(res.status_code, 400)
        self.assertIn('Nghị định 13/2023', res.text)
        self.assertFalse(self.env['res.partner'].search([('mobile', '=', '0987654321')]))

        res = self.url_open('/dental/booking', data=dict(self._booking_data(), csrf_token=csrf))
        self.assertEqual(res.status_code, 200)
        self.assertIn('Đã nhận yêu cầu đặt lịch', res.text)
        patient = self.env['res.partner'].search([('mobile', '=', '0987654321')])
        self.assertEqual(len(patient), 1)
        self.assertTrue(patient.is_patient)
        self.assertTrue(patient.data_consent)
        self.assertTrue(patient.data_consent_date)
        visit = Visit.search([('patient_id', '=', patient.id)])
        self.assertEqual(visit.state, 'draft')
        self.assertEqual(visit.service_ids, self.service)
        self.assertIn('Đặt lịch trực tuyến', visit.reason)

        # Bệnh nhân cũ: không tạo hồ sơ trùng
        self.url_open('/dental/booking', data=dict(self._booking_data(time='15:00'), csrf_token=csrf))
        self.assertEqual(self.env['res.partner'].search_count([('mobile', '=', '0987654321')]), 1)
        self.assertEqual(Visit.search_count([('patient_id', '=', patient.id)]), 2)

        # Chống spam: tối đa 3 yêu cầu / số điện thoại / 24 giờ
        self.url_open('/dental/booking', data=dict(self._booking_data(time='16:00'), csrf_token=csrf))
        res = self.url_open('/dental/booking', data=dict(self._booking_data(time='17:00'), csrf_token=csrf))
        self.assertEqual(res.status_code, 400)
        self.assertEqual(Visit.search_count([('patient_id', '=', patient.id)]), 3)

    # ------------------------------------------------------------------ API
    def _api_key(self, user):
        return self.env['res.users.apikeys'].with_user(user)._generate('dmag_patient_api', 'Ứng dụng di động')

    def test_api_returns_only_own_data(self):
        self.assertEqual(self.url_open('/api/dmag/v1/me').status_code, 401)
        key = self._api_key(self.user_a)
        headers = {'Authorization': 'Bearer %s' % key}
        res = self.url_open('/api/dmag/v1/me', headers=headers)
        self.assertEqual(res.status_code, 200)
        me = res.json()
        self.assertEqual(me['partner']['id'], self.pa.id)
        self.assertEqual({p['id'] for p in me['patients']}, {self.pa.id, self.child.id})

        items = self.url_open('/api/dmag/v1/visits', headers=headers).json()['items']
        ids = {v['id'] for v in items}
        self.assertIn(self.visit_a.id, ids)
        self.assertIn(self.visit_child.id, ids)
        self.assertNotIn(self.visit_b.id, ids)
        self.assertEqual(self.url_open('/api/dmag/v1/visit/%s' % self.visit_b.id, headers=headers).status_code, 404)
        detail = self.url_open('/api/dmag/v1/visit/%s' % self.visit_a.id, headers=headers).json()
        self.assertEqual(detail['assessment'], 'Viêm nướu nhẹ')
        self.assertEqual(self.url_open('/api/dmag/v1/visits?patient_id=%s' % self.pb.id,
                                       headers=headers).status_code, 403)
        self.assertEqual(self.url_open('/api/dmag/v1/plans', headers=headers).status_code, 200)
        loyalty = self.url_open('/api/dmag/v1/loyalty', headers=headers).json()
        self.assertEqual(loyalty['partner']['id'], self.pa.id)
        self.assertEqual(self.url_open('/api/dmag/v1/loyalty?patient_id=%s' % self.pb.id,
                                       headers=headers).status_code, 403)

        bad = self.url_open('/api/dmag/v1/me', headers={'Authorization': 'Bearer sai'})
        self.assertEqual(bad.status_code, 401)

        payload = {'date': (fields.Date.today() + timedelta(days=3)).isoformat(), 'time': '10:00',
                   'service_id': self.service.id, 'consent': True, 'patient_id': self.child.id}
        res = self.url_open('/api/dmag/v1/booking', data=json.dumps(payload),
                            headers=dict(headers, **{'Content-Type': 'application/json'}))
        self.assertEqual(res.status_code, 201, res.text)
        visit = self.env['dmag.dental.visit'].browse(res.json()['visit']['id'])
        self.assertEqual(visit.patient_id, self.child)
        self.assertEqual(visit.state, 'draft')
        payload['patient_id'] = self.pb.id
        res = self.url_open('/api/dmag/v1/booking', data=json.dumps(payload),
                            headers=dict(headers, **{'Content-Type': 'application/json'}))
        self.assertEqual(res.status_code, 403)
