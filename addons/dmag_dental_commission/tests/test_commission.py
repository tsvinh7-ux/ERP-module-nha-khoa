from unittest.mock import patch

from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests import new_test_user, tagged

from odoo.addons.dmag_dental_clinic.tests.common import DentalCommon


@tagged('post_install', '-at_install')
class TestCommission(DentalCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Rule = cls.env['dmag.commission.rule']
        # Tắt các quy tắc khác (nếu có) để test độc lập
        Rule.search([]).write({'active': False})
        cls.rule_doctor = Rule.create({'name': 'BS 10%', 'role': 'doctor', 'basis': 'collected', 'rate': 10})
        cls.rule_referrer = Rule.create({'name': 'GT 5%', 'role': 'referrer', 'basis': 'revenue', 'rate': 5})
        cls.recep = new_test_user(cls.env, 'lt_comm', groups='dmag_dental_base.group_dmag_receptionist')
        cls.manager = new_test_user(cls.env, 'ql_comm', groups='dmag_dental_base.group_dmag_manager')
        cls.Line = cls.env['dmag.commission.line']

    def _done_visit(self, doctor, product, teeth=('36',)):
        visit = self._visit(doctor_id=doctor.id, service_ids=[(6, 0, product.ids)])
        visit.action_confirm()
        visit.action_check_in()
        visit.action_start()
        self.env['dmag.dental.procedure'].add_from_workspace(visit.id, product.id, teeth=list(teeth))
        return visit

    def _lines(self, visit, **kw):
        domain = [('visit_id', '=', visit.id)] + [(k, '=', v) for k, v in kw.items()]
        return self.Line.search(domain)

    def test_commission_on_collected_money_only(self):
        visit = self._done_visit(self.doctor2, self.svc_filling)
        visit._create_and_post_invoices()
        visit._dmag_compute_commissions()
        self.assertFalse(self._lines(visit), 'Chưa thu tiền thì chưa có hoa hồng')

        visit.with_user(self.recep).register_payment('cash', 100000)
        lines = self._lines(visit, role='doctor')
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines.amount, 10000)
        self.assertEqual(lines.user_id, self.doctor_user2)

        # Idempotent: tính lại nhiều lần không sinh trùng
        visit._dmag_compute_commissions()
        visit._dmag_compute_commissions()
        self.assertEqual(len(self._lines(visit, role='doctor')), 1)

        visit.with_user(self.recep).register_payment('transfer')
        lines = self._lines(visit, role='doctor', state='valid')
        self.assertEqual(sum(lines.mapped('amount')), 40000)
        self.assertEqual(len(lines), 2)

        # Hóa đơn bị đảo → dòng âm, tổng về 0
        invoice = visit.invoice_ids
        refund = invoice.sudo()._reverse_moves(cancel=False)
        refund.action_post()
        lines = self._lines(visit, role='doctor', state='valid')
        self.assertEqual(sum(lines.mapped('amount')), 0)
        self.assertTrue(lines.filtered(lambda l: l.kind == 'reversal' and l.amount == -40000))

    def test_referrer_revenue_and_statement(self):
        referrer = self.env['res.partner'].create({'name': 'Người giới thiệu A'})
        self.patient.referrer_id = referrer
        visit = self._done_visit(self.doctor2, self.svc_filling)
        visit.register_payment('cash')
        ref_line = self._lines(visit, role='referrer')
        self.assertEqual(ref_line.partner_id, referrer)
        self.assertEqual(ref_line.amount, 20000)
        statements = self.env['dmag.commission.statement']._generate(
            self.env.company, fields.Date.context_today(self))
        st_doctor = statements.filtered(lambda s: s.user_id == self.doctor_user2)
        self.assertEqual(st_doctor.total, 40000)
        st_doctor.action_confirm()
        with self.assertRaises(AccessError):
            st_doctor.with_user(self.manager).write({'date_from': '2020-01-01'})
        # Nguồn P3 cho dmag_hr_3p
        employee = self.env['hr.employee'].create({'name': 'BS Hai', 'user_id': self.doctor_user2.id})
        today = fields.Date.context_today(self)
        self.assertEqual(self.Line._dmag_amount_for_employee(employee, today.replace(day=1), today), 40000)

    def test_own_records_rule(self):
        visit = self._done_visit(self.doctor2, self.svc_filling)
        visit.register_payment('cash')
        self.assertTrue(self._lines(visit))
        own = self.Line.with_user(self.doctor_user2).search([])
        self.assertTrue(own)
        self.assertFalse(own.filtered(lambda l: l.user_id != self.doctor_user2))
        self.assertFalse(self.Line.with_user(self.recep).search([('visit_id', '=', visit.id)]))
        self.assertTrue(self.Line.with_user(self.manager).search([('visit_id', '=', visit.id)]))
        with self.assertRaises(AccessError):
            own.with_user(self.doctor_user2).write({'amount': 1})
        with self.assertRaises(AccessError):
            own[:1].with_user(self.manager).write({'amount': 1})

    def test_ethical_fuse(self):
        # Mão sứ cần bác sĩ thứ hai duyệt, làm ngoài kế hoạch đã duyệt → không hoa hồng
        visit = self._done_visit(self.doctor, self.svc_crown)
        visit.register_payment('cash')
        self.assertFalse(self._lines(visit, state='valid'))
        self.assertTrue(any('cầu chì y đức' in (m.body or '') for m in visit.message_ids))

        # Dòng đã phát sinh bị hủy khi cầu chì kích hoạt (ví dụ có phàn nàn)
        visit2 = self._done_visit(self.doctor2, self.svc_filling)
        visit2.register_payment('cash')
        self.assertTrue(self._lines(visit2, state='valid'))
        Procedure = type(self.env['dmag.dental.procedure'])
        with patch.object(Procedure, '_dmag_ethics_fuse', lambda self: 'Lượt khám có phàn nàn'):
            visit2._dmag_compute_commissions()
        self.assertFalse(self._lines(visit2, state='valid'))
        void = self._lines(visit2, state='void')
        self.assertTrue(void)
        self.assertEqual(void[0].void_reason, 'Lượt khám có phàn nàn')
