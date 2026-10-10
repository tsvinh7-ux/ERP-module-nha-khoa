import itertools
from datetime import datetime

import pytz

from odoo.addons.dmag_dental_clinic.tests.common import DentalCommon

API_KEY = 'test-sepay-key-123'
_SEQ = itertools.count(1000)


class SepayCommon(DentalCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.company = env.company
        cls.company.partner_id.tz = 'Asia/Ho_Chi_Minh'
        cls.config = env['dmag.sepay.config'].create({
            'company_id': cls.company.id,
            'bank_code': 'MBBank',
            'account_number': '0123456789',
            'account_name': 'NHA KHOA DMAG',
            'api_key': API_KEY,
            'code_prefix': 'DMAG',
            'amount_tolerance': 0,
        })
        ref = env.ref
        cls.receptionist = env['res.users'].create({
            'name': 'Lễ tân A', 'login': 'le_tan_a_sepay', 'email': 'la@dmag.test',
            'groups_id': [(6, 0, [ref('dmag_dental_base.group_dmag_receptionist').id])],
        })
        cls.cashier = env['res.users'].create({
            'name': 'Thu ngân B', 'login': 'thu_ngan_b_sepay', 'email': 'tnb@dmag.test',
            'groups_id': [(6, 0, [ref('dmag_dental_base.group_dmag_receptionist').id])],
        })
        cls.manager = env['res.users'].create({
            'name': 'Quản lý C', 'login': 'quan_ly_c_sepay', 'email': 'qlc@dmag.test',
            'groups_id': [(6, 0, [ref('dmag_dental_base.group_dmag_manager').id])],
        })

    def _billable_visit(self, **kw):
        """Lượt khám đã làm 1 thủ thuật 400.000đ, chưa lập hóa đơn."""
        visit = self._visit(**kw)
        visit.action_confirm()
        visit.action_check_in()
        visit.action_start()
        self.env['dmag.dental.procedure'].add_from_workspace(
            visit.id, self.svc_filling.id, teeth=['36'], surfaces=['O'])
        self.assertEqual(visit.amount_due, 400000)
        return visit

    def _payload(self, amount, content, sepay_id=None, transfer_type='in', code=None):
        seq = next(_SEQ)
        now = datetime.now(pytz.timezone('Asia/Ho_Chi_Minh')).strftime('%Y-%m-%d %H:%M:%S')
        return {
            'id': sepay_id or seq,
            'gateway': 'MBBank',
            'transactionDate': now,
            'accountNumber': '0123456789',
            'code': code,
            'content': content,
            'transferType': transfer_type,
            'transferAmount': amount,
            'accumulated': 99000000,
            'subAccount': None,
            'referenceCode': 'MBVCB.%s' % seq,
            'description': 'BankAPINotify %s' % content,
        }

    def _hook(self, payload, key=API_KEY):
        return self.env['dmag.sepay.transaction'].sudo()._sepay_handle_webhook('Apikey %s' % key, payload)
