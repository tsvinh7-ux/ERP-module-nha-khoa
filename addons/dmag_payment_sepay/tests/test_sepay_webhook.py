import json

from odoo.exceptions import AccessError, UserError
from odoo.tests import HttpCase, tagged

from .common import API_KEY, SepayCommon


@tagged('post_install', '-at_install')
class TestSepayWebhook(SepayCommon):

    def test_get_payment_qr(self):
        visit = self._billable_visit()
        data = visit.with_user(self.receptionist).get_payment_qr()
        self.assertEqual(visit.payment_status, 'to_pay')
        self.assertEqual(data['amount'], 400000)
        self.assertTrue(data['code'].startswith('DMAG'))
        self.assertEqual(len(data['code']), 12)
        self.assertIn('acc=0123456789', data['qr_url'])
        self.assertIn('bank=MBBank', data['qr_url'])
        self.assertIn('amount=400000', data['qr_url'])
        self.assertIn('des=%s' % data['code'], data['qr_url'])
        self.assertEqual(data['content'], data['code'])
        # Gọi lại → dùng lại yêu cầu đang chờ
        again = visit.with_user(self.receptionist).get_payment_qr()
        self.assertEqual(again['request_id'], data['request_id'])

    def test_exact_match_pays_visit(self):
        visit = self._billable_visit()
        data = visit.get_payment_qr()
        status, body = self._hook(self._payload(400000, '%s thanh toan rang' % data['code']))
        self.assertEqual((status, body), (200, {'success': True}))
        request = self.env['dmag.payment.request'].browse(data['request_id'])
        self.assertEqual(request.state, 'paid')
        self.assertEqual(request.paid_amount, 400000)
        visit.invalidate_recordset()
        self.assertEqual(visit.payment_status, 'paid')
        self.assertEqual(visit.amount_due, 0)
        tx = request.transaction_ids
        self.assertEqual(tx.state, 'matched')
        self.assertFalse(tx.needs_review)
        log = visit.payment_log_ids
        self.assertEqual((log.method, log.amount, log.source), ('transfer', 400000, 'sepay'))

    def test_demo_simulated_transfer(self):
        visit = self._billable_visit()
        data = visit.with_user(self.receptionist).get_payment_qr()
        self.assertFalse(data['demo'])
        request = self.env['dmag.payment.request'].browse(data['request_id'])
        with self.assertRaises(UserError):
            request.with_user(self.receptionist).action_simulate_transfer()
        self.config.demo_mode = True
        self.assertTrue(visit.get_payment_qr()['demo'])
        status = request.with_user(self.receptionist).action_simulate_transfer()
        self.assertEqual(status['state'], 'paid')
        visit.invalidate_recordset()
        self.assertEqual(visit.payment_status, 'paid')
        self.assertEqual(request.transaction_ids.state, 'matched')
        with self.assertRaises(UserError):
            request.with_user(self.receptionist).action_simulate_transfer()

    def test_code_with_spaces_and_lowercase(self):
        visit = self._billable_visit()
        code = visit.get_payment_qr()['code']
        content = 'IBFT %s %s' % (code[:6].lower(), code[6:].lower())
        self._hook(self._payload(400000, content))
        visit.invalidate_recordset()
        self.assertEqual(visit.payment_status, 'paid')

    def test_idempotency(self):
        visit = self._billable_visit()
        data = visit.get_payment_qr()
        payload = self._payload(200000, data['code'], sepay_id=777001)
        self.assertEqual(self._hook(payload)[0], 200)
        status, body = self._hook(payload)
        self.assertEqual(status, 200)
        self.assertTrue(body['success'])
        txs = self.env['dmag.sepay.transaction'].search([('sepay_id', '=', '777001')])
        self.assertEqual(sorted(txs.mapped('state')), ['duplicate', 'matched'])
        self.assertEqual(len(visit.payment_log_ids), 1)
        visit.invalidate_recordset()
        self.assertEqual(visit.amount_due, 200000)

    def test_partial_then_complete(self):
        visit = self._billable_visit()
        data = visit.get_payment_qr()
        request = self.env['dmag.payment.request'].browse(data['request_id'])
        self._hook(self._payload(150000, data['code']))
        self.assertEqual(request.state, 'partial')
        self.assertEqual(request.residual, 250000)
        visit.invalidate_recordset()
        self.assertEqual(visit.amount_due, 250000)
        self._hook(self._payload(250000, data['code']))
        self.assertEqual(request.state, 'paid')
        visit.invalidate_recordset()
        self.assertEqual(visit.payment_status, 'paid')

    def test_overpayment_goes_to_queue(self):
        visit = self._billable_visit()
        data = visit.get_payment_qr()
        self._hook(self._payload(500000, data['code']))
        tx = self.env['dmag.payment.request'].browse(data['request_id']).transaction_ids
        self.assertEqual(tx.state, 'matched')
        self.assertTrue(tx.needs_review)
        self.assertEqual(tx.unapplied_amount, 100000)
        visit.invalidate_recordset()
        self.assertEqual(visit.payment_status, 'paid')

    def test_unmatched_queue_and_manual_match(self):
        visit = self._billable_visit()
        visit.get_payment_qr()
        self._hook(self._payload(400000, 'chuyen tien kham rang'))
        tx = self.env['dmag.sepay.transaction'].search([('content', '=', 'chuyen tien kham rang')])
        self.assertEqual(tx.state, 'unmatched')
        self.assertTrue(tx.needs_review)
        queue = self.env['dmag.sepay.transaction'].search([('needs_review', '=', True)])
        self.assertIn(tx, queue)
        # Lễ tân không đối soát được
        with self.assertRaises(AccessError):
            tx.with_user(self.receptionist).action_open_match_wizard()
        wizard = self.env['dmag.sepay.match.wizard'].with_user(self.manager).with_context(
            default_transaction_id=tx.id).create({'visit_id': visit.id})
        self.assertEqual(wizard.amount, 400000)
        wizard.action_apply()
        self.assertEqual(tx.state, 'matched')
        self.assertFalse(tx.needs_review)
        self.assertEqual(tx.matched_by_id, self.manager)
        visit.invalidate_recordset()
        self.assertEqual(visit.payment_status, 'paid')
        self.assertEqual(visit.payment_log_ids.source, 'manual_match')

    def test_out_transfer_ignored(self):
        visit = self._billable_visit()
        data = visit.get_payment_qr()
        status, _body = self._hook(self._payload(400000, data['code'], transfer_type='out'))
        self.assertEqual(status, 200)
        tx = self.env['dmag.sepay.transaction'].search([], limit=1)
        self.assertEqual(tx.state, 'ignored')
        visit.invalidate_recordset()
        self.assertEqual(visit.amount_due, 400000)

    def test_auth_rejected_direct(self):
        count = self.env['dmag.sepay.transaction'].search_count([])
        status, body = self._hook(self._payload(1000, 'x'), key='wrong')
        self.assertEqual(status, 401)
        self.assertFalse(body['success'])
        status, _b = self.env['dmag.sepay.transaction'].sudo()._sepay_handle_webhook('', self._payload(1000, 'x'))
        self.assertEqual(status, 401)
        self.assertEqual(self.env['dmag.sepay.transaction'].search_count([]), count)

    def test_receptionist_cannot_edit_amount(self):
        visit = self._billable_visit()
        data = visit.with_user(self.receptionist).get_payment_qr()
        request = self.env['dmag.payment.request'].with_user(self.receptionist).browse(data['request_id'])
        with self.assertRaises(AccessError):
            request.write({'amount': 1000})
        with self.assertRaises(AccessError):
            request.write({'state': 'paid'})
        request.write({'note': 'Khách quét QR'})
        # Không tạo được yêu cầu vượt số phải thu
        with self.assertRaises(AccessError):
            self.env['dmag.payment.request'].with_user(self.receptionist).create(
                {'visit_id': visit.id, 'amount': 9000000})
        # Giám đốc (admin) sửa được
        self.env['dmag.payment.request'].browse(data['request_id']).write({'amount': 390000})
        # Giao dịch không xóa được bởi quản lý
        self._hook(self._payload(390000, data['code']))
        tx = self.env['dmag.sepay.transaction'].search([], limit=1)
        with self.assertRaises(AccessError):
            tx.with_user(self.manager).unlink()


@tagged('post_install', '-at_install')
class TestSepayWebhookHttp(HttpCase, SepayCommon):

    def _post(self, payload, key=None):
        headers = {'Content-Type': 'application/json'}
        if key:
            headers['Authorization'] = 'Apikey %s' % key
        return self.url_open('/dmag/sepay/webhook', data=json.dumps(payload), headers=headers)

    def test_http_auth_and_match(self):
        self.authenticate(None, None)
        visit = self._billable_visit()
        data = visit.get_payment_qr()
        res = self._post(self._payload(400000, data['code']))
        self.assertEqual(res.status_code, 401)
        res = self._post(self._payload(400000, data['code']), key='bad-key')
        self.assertEqual(res.status_code, 401)
        self.assertFalse(self.env['dmag.sepay.transaction'].search_count([]))
        res = self._post(self._payload(400000, data['code']), key=API_KEY)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {'success': True})
        visit.invalidate_recordset()
        self.assertEqual(visit.payment_status, 'paid')
