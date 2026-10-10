import json

from odoo.tests import tagged

from .common import RxCommon


@tagged('post_install', '-at_install')
class TestNationalInterconnection(RxCommon):

    def test_mock_send_success_and_token_cache(self):
        # Chỉ xét nhật ký phát sinh trong bài test (CSDL có thể đã có nhật ký cũ)
        last_log = self.env['dmag.rx.send.log'].search([], order='id desc', limit=1).id or 0
        rx = self._rx()
        rx.action_issue()
        self.assertEqual(rx.state, 'sent')
        self.assertTrue(rx.sent_at)
        ops = rx.send_log_ids.mapped('operation')
        self.assertIn('send', ops)
        logs = self.env['dmag.rx.send.log'].search([('config_id', '=', self.config.id), ('id', '>', last_log)])
        self.assertEqual(set(logs.mapped('operation')), {'login_facility', 'login_doctor', 'send'})
        send_log = rx.send_log_ids.filtered(lambda log: log.operation == 'send')
        self.assertTrue(send_log.success)
        payload = json.loads(send_log.request_body)
        self.assertEqual(payload['ma_don_thuoc'], rx.name)
        self.assertEqual(payload['loai_don_thuoc'], 'c')
        self.assertEqual(payload['ma_so_the_bao_hiem_y_te'], 'DN4797900000111')
        self.assertEqual(payload['chan_doan'][0]['ma_chan_doan'], 'K04.0')
        self.assertEqual(payload['thong_tin_don_thuoc'][0]['ten_thuoc'], 'Amoxicillin 500 mg')
        self.assertEqual(payload['thong_tin_don_thuoc'][0]['so_luong'], 10)
        for key in ('hinh_thuc_dieu_tri', 'ho_ten_benh_nhan', 'ngay_sinh_benh_nhan', 'gioi_tinh', 'dia_chi',
                    'loi_dan', 'ngay_gio_ke_don', 'so_dien_thoai_nguoi_kham_benh', 'thong_tin_nguoi_giam_ho'):
            self.assertIn(key, payload)
        # Mật khẩu không lưu trong nhật ký
        login_log = logs.filtered(lambda log: log.operation == 'login_doctor')
        self.assertNotIn('secret', login_log.request_body)
        # Token được dùng lại cho đơn thứ hai (không đăng nhập lại)
        rx2 = self._rx()
        rx2.action_issue()
        self.assertEqual(rx2.state, 'sent')
        logs = self.env['dmag.rx.send.log'].search([('config_id', '=', self.config.id), ('id', '>', last_log)])
        self.assertEqual(len(logs.filtered(lambda log: log.operation == 'login_doctor')), 1)

    def test_mock_error_then_retry(self):
        self.config.mock_fail = True
        rx = self._rx()
        rx.action_issue()
        self.assertEqual(rx.state, 'send_error')
        self.assertIn('Giả lập lỗi', rx.send_error)
        self.assertEqual(rx.send_attempts, 1)
        failed = rx.send_log_ids.filtered(lambda log: log.operation == 'send')
        self.assertFalse(failed.success)
        self.assertEqual(failed.status_code, 400)
        # Nút "Gửi lại" khi vẫn lỗi
        rx.action_resend()
        self.assertEqual(rx.send_attempts, 2)
        self.assertEqual(rx.state, 'send_error')
        # Hết lỗi → cron gửi lại thành công
        self.config.mock_fail = False
        self.env['dmag.prescription']._cron_send_pending()
        self.assertEqual(rx.state, 'sent')
        self.assertFalse(rx.send_error)
        self.assertEqual(len(rx.send_log_ids.filtered(lambda log: log.operation == 'send')), 3)

    def test_disabled_queue(self):
        self.config.enabled = False
        rx = self._rx()
        rx.action_issue()
        self.assertEqual(rx.state, 'issued')
        self.assertFalse(rx.send_log_ids)
        self.env['dmag.prescription']._cron_send_pending()
        self.assertEqual(rx.state, 'issued')
        self.config.enabled = True
        self.env['dmag.prescription']._cron_send_pending()
        self.assertEqual(rx.state, 'sent')

    def test_max_attempts(self):
        self.config.write({'mock_fail': True, 'max_attempts': 2})
        rx = self._rx()
        rx.action_issue()
        Rx = self.env['dmag.prescription']
        Rx._cron_send_pending()
        Rx._cron_send_pending()
        self.assertEqual(rx.send_attempts, 2)

    def test_live_requires_credentials(self):
        self.config.mode = 'live'
        self.doctor.rx_link_code = False
        rx = self._rx()
        rx.action_issue()
        self.assertEqual(rx.state, 'send_error')
        self.assertIn('mã liên thông', rx.send_error)
