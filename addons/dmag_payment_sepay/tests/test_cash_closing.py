from datetime import timedelta

from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from .common import SepayCommon


@tagged('post_install', '-at_install')
class TestCashClosing(SepayCommon):

    def test_closing_totals_and_lock(self):
        v1 = self._billable_visit()
        v1.with_user(self.receptionist).register_payment('cash', 100000)
        v1.with_user(self.receptionist).register_payment('card', 50000)
        v2 = self._billable_visit(chair_id=self.chair2.id, scheduled_start=self.start + timedelta(hours=3))
        code = v2.get_payment_qr()['code']
        self._hook(self._payload(400000, code))
        # Giao dịch không khớp vẫn vào số ngân hàng báo có → lệch chuyển khoản
        self._hook(self._payload(30000, 'khong ma'))

        Closing = self.env['dmag.cash.closing'].with_user(self.receptionist)
        closing = Closing.create({'shift': 'full', 'cash_opening': 1000000})
        self.assertEqual(closing.system_cash, 100000)
        self.assertEqual(closing.system_card, 50000)
        self.assertEqual(closing.system_transfer, 400000)
        self.assertEqual(closing.system_total, 550000)
        self.assertEqual(closing.bank_sepay_total, 430000)
        self.assertEqual(closing.bank_diff, 30000)

        closing.write({'cash_counted': 1090000, 'card_slip_total': 50000})
        self.assertEqual(closing.cash_expected, 1100000)
        self.assertEqual(closing.cash_diff, -10000)
        self.assertTrue(closing.has_difference)

        closing.action_sign_receptionist()
        self.assertEqual(closing.state, 'counted')
        self.assertEqual(closing.receptionist_sign_uid, self.receptionist)
        with self.assertRaises(AccessError):
            closing.write({'cash_counted': 1100000})
        with self.assertRaises(UserError):
            closing.action_sign_cashier()  # cùng người
        closing.with_user(self.cashier).action_sign_cashier()
        with self.assertRaises(AccessError):
            closing.action_confirm()  # lễ tân không xác nhận được
        mgr_closing = closing.with_user(self.manager)
        with self.assertRaises(UserError):
            mgr_closing.action_confirm()  # thiếu giải trình
        mgr_closing.write({'diff_reason': 'Thiếu 10.000đ tiền lẻ; 30.000đ chuyển khoản không ghi mã.'})
        mgr_closing.action_confirm()
        self.assertEqual(closing.state, 'confirmed')
        with self.assertRaises(AccessError):
            mgr_closing.write({'note': 'sửa'})
        mgr_closing.action_lock()
        self.assertEqual(closing.state, 'locked')
        with self.assertRaises(AccessError):
            closing.write({'note': 'sửa'})
        with self.assertRaises(AccessError):
            closing.unlink()
        # Khoản thu sau khi chốt không rơi vào biên bản cũ
        v1.with_user(self.receptionist).register_payment('cash', 10000)
        self.assertEqual(closing.system_cash, 100000)
        second = Closing.create({'shift': 'evening'})
        self.assertEqual(second.system_cash, 10000)
        # Giám đốc mở lại được
        closing.action_reopen()
        self.assertEqual(closing.state, 'draft')
        self.assertFalse(closing.receptionist_sign_uid)
        report = self.env['ir.actions.report']._render_qweb_html(
            'dmag_payment_sepay.report_dmag_cash_closing', closing.ids)
        self.assertIn('BIÊN BẢN CHỐT KÉT', report[0].decode())
