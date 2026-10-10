import json
from datetime import datetime

import pytz

from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged

from odoo.addons.dmag_zalo_zns.models.zns_utils import eval_expression, normalize_phone, quiet_until


class ZnsCommon(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.write({'dmag_zns_mode': 'mock', 'dmag_zns_quiet_start': 0.0, 'dmag_zns_quiet_end': 0.0})
        cls.template = cls.env['dmag.zns.template'].create({
            'name': 'Test xác nhận', 'code': 'test_confirm', 'template_id': '123456',
            'preview_text': 'Chào <customer_name> – <clinic>',
            'param_ids': [
                (0, 0, {'name': 'customer_name', 'expression': 'patient.name'}),
                (0, 0, {'name': 'clinic', 'expression': 'company.name'}),
                (0, 0, {'name': 'note', 'expression': "patient.comment || 'không có'"}),
            ],
        })
        cls.partner = cls.env['res.partner'].create({'name': 'Nguyễn Văn A', 'mobile': '0912 345 678'})

    def _set_quiet_now(self, transactional=False):
        tz = pytz.timezone(self.env.user.tz or 'Asia/Ho_Chi_Minh')
        hour = pytz.utc.localize(datetime.utcnow()).astimezone(tz).hour
        self.company.write({'dmag_zns_quiet_start': float(hour), 'dmag_zns_quiet_end': float((hour + 2) % 24)})
        self.template.transactional = transactional


@tagged('post_install', '-at_install')
class TestZns(ZnsCommon):

    def test_normalize_phone(self):
        self.assertEqual(normalize_phone('0912 345 678'), '84912345678')
        self.assertEqual(normalize_phone('+84 912-345-678'), '84912345678')
        self.assertEqual(normalize_phone('84912345678'), '84912345678')
        self.assertFalse(normalize_phone('12345'))
        self.assertFalse(normalize_phone(False))
        self.partner.zalo_phone = '0988000111'
        self.assertEqual(self.partner._dmag_zns_phone(), '84988000111')

    def test_expression(self):
        dt = fields.Datetime.to_datetime('2026-10-10 02:30:00')
        variables = {'partner': self.partner, 'visit': {'start': dt}}
        self.assertEqual(eval_expression(self.env, 'partner.name', variables), 'Nguyễn Văn A')
        self.env.user.tz = 'Asia/Ho_Chi_Minh'
        self.assertEqual(eval_expression(self.env, 'visit.start|time', variables), '09:30')
        self.assertEqual(eval_expression(self.env, 'visit.start|date', variables), '10/10/2026')
        self.assertEqual(eval_expression(self.env, "partner.ref || 'mặc định'", variables), 'mặc định')

    def test_send_mock(self):
        message = self.env['dmag.zns.message'].send('test_confirm', self.partner, params_override={'extra': 1})
        self.assertEqual(message.state, 'queued')
        self.assertEqual(message.phone, '84912345678')
        data = json.loads(message.params_json)
        self.assertEqual(data['customer_name'], 'Nguyễn Văn A')
        self.assertEqual(data['note'], 'không có')
        self.assertEqual(data['extra'], '1')
        self.assertIn('Nguyễn Văn A', message.preview)
        payload = message._dmag_payload()
        self.assertEqual(set(payload), {'phone', 'template_id', 'template_data', 'tracking_id'})
        self.env['dmag.zns.message']._cron_send_queue()
        self.assertEqual(message.state, 'sent')
        self.assertTrue(message.msg_id.startswith('mock-'))

    def test_opt_out(self):
        self.partner.zns_opt_out = True
        self.assertTrue(self.partner.zns_opt_out_date)
        message = self.env['dmag.zns.message'].send('test_confirm', self.partner)
        self.assertEqual(message.state, 'skipped')
        no_phone = self.env['res.partner'].create({'name': 'Không số'})
        self.assertEqual(self.env['dmag.zns.message'].send(self.template, no_phone).state, 'skipped')

    def test_quiet_hours(self):
        self._set_quiet_now()
        self.assertTrue(quiet_until(self.env, self.company))
        message = self.env['dmag.zns.message'].send('test_confirm', self.partner, send_now=True)
        self.assertEqual(message.state, 'queued')
        self.assertGreater(message.next_try, fields.Datetime.now())
        self.env['dmag.zns.message']._cron_send_queue()
        self.assertEqual(message.state, 'queued')
        # Tin giao dịch vẫn gửi trong giờ yên lặng
        self.template.transactional = True
        urgent = self.env['dmag.zns.message'].send('test_confirm', self.partner, send_now=True)
        self.assertEqual(urgent.state, 'sent')

    def test_retry_then_failed(self):
        self.company.dmag_zns_max_retry = 2
        message = self.env['dmag.zns.message'].send('test_confirm', self.partner)
        Message = self.env['dmag.zns.message'].with_context(dmag_zns_mock_error=-2)
        Message.browse(message.id)._dmag_process()
        self.assertEqual(message.state, 'queued')
        self.assertEqual(message.attempt_count, 1)
        message.sudo().next_try = fields.Datetime.now()
        Message.browse(message.id)._dmag_process()
        self.assertEqual(message.state, 'failed')
        # Lỗi không thử lại (số không có Zalo)
        other = self.env['dmag.zns.message'].send('test_confirm', self.partner)
        self.env['dmag.zns.message'].with_context(dmag_zns_mock_error=-118).browse(other.id)._dmag_process()
        self.assertEqual(other.state, 'failed')

    def test_expired_message_cancelled(self):
        message = self.env['dmag.zns.message'].send(
            'test_confirm', self.partner, expire_at=fields.Datetime.subtract(fields.Datetime.now(), hours=1))
        message._dmag_process()
        self.assertEqual(message.state, 'cancel')

    def test_bizapps_without_module(self):
        self.company.dmag_zns_mode = 'bizapps'
        message = self.env['dmag.zns.message'].send('test_confirm', self.partner, send_now=True)
        self.assertEqual(message.state, 'failed')
        self.assertIn('biz.zalo.zns', message.error)

    def test_webhook_delivery_and_signature(self):
        message = self.env['dmag.zns.message'].send('test_confirm', self.partner, send_now=True)
        Event = self.env['dmag.zns.webhook.event']
        body = json.dumps({'app_id': 'APP1', 'event_name': 'user_received_message', 'timestamp': '1700000000000',
                           'message': {'msg_id': message.msg_id, 'delivery_time': '1700000000000'}})
        event, ok = Event._dmag_receive(body)
        self.assertTrue(ok)
        self.assertEqual(message.state, 'delivered')
        self.assertEqual(event.message_id, message)
        # Có khóa bí mật → kiểm tra chữ ký
        self.company.sudo().write({'dmag_zalo_app_id': 'APP1', 'dmag_zalo_webhook_secret': 'S3CRET'})
        _event, ok = Event._dmag_receive(body, signature='mac=wrong')
        self.assertFalse(ok)
        good = Event._dmag_compute_signature('APP1', body, '1700000000000', 'S3CRET')
        event, ok = Event._dmag_receive(body, signature='mac=%s' % good)
        self.assertTrue(ok)
        self.assertEqual(event.verified, 'ok')

    def test_log_readonly(self):
        message = self.env['dmag.zns.message'].send('test_confirm', self.partner)
        user = self.env['res.users'].create({
            'name': 'Lễ tân ZNS', 'login': 'le_tan_zns',
            'groups_id': [(6, 0, [self.env.ref('dmag_dental_base.group_dmag_manager').id])],
        })
        with self.assertRaises(AccessError):
            message.with_user(user).write({'phone': '84900000000'})
        # Nhân viên vẫn gửi được tin (tạo bằng quyền hệ thống)
        sent = self.env['dmag.zns.message'].with_user(user).send('test_confirm', self.partner)
        self.assertEqual(sent.state, 'queued')
