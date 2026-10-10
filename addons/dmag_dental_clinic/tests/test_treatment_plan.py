from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import DentalCommon


@tagged('post_install', '-at_install')
class TestTreatmentPlan(DentalCommon):

    def _plan(self):
        return self.env['dmag.treatment.plan'].create_from_workspace(self.patient.id, False, [
            {'name': 'A – Sứ', 'is_recommended': True, 'installment_months': 4,
             'lines': [{'product_id': self.svc_crown.id, 'teeth': ['36', '46']}]},
            {'name': 'B – Trám', 'lines': [{'product_id': self.svc_filling.id, 'teeth': ['36'], 'surfaces': ['O']}]},
        ])

    def test_plan_two_options_and_second_opinion(self):
        data = self._plan()
        plan = self.env['dmag.treatment.plan'].browse(data['id'])
        self.assertEqual(len(plan.option_ids), 2)
        opt_a = plan.option_ids[0]
        self.assertEqual(opt_a.amount_total, 10000000)
        self.assertEqual(opt_a.monthly_amount, 2500000)
        self.assertTrue(plan.second_opinion_required)
        plan.action_present()
        # Chưa có BS thứ hai duyệt → chặn
        with self.assertRaises(UserError):
            opt_a.action_accept()
        # BS lập kế hoạch không tự duyệt
        with self.assertRaises(UserError):
            plan.action_second_opinion()
        plan.with_user(self.doctor_user2).action_second_opinion()
        self.assertEqual(plan.second_opinion_by_id, self.doctor2)
        opt_a.action_accept()
        self.assertEqual(plan.state, 'accepted')
        self.assertEqual(plan.sale_order_id.state, 'sale')
        self.assertEqual(plan.sale_order_id.amount_untaxed, 10000000)
        # Chưa làm gì → chưa xuất hóa đơn được gì
        self.assertFalse(any(plan.sale_order_id.order_line.mapped('qty_to_invoice')))

        # Làm 1 dòng trong lượt khám
        visit = self._visit(service_ids=[(6, 0, self.svc_crown.ids)], treatment_plan_id=plan.id)
        visit.action_check_in()
        visit.action_start()
        line = opt_a.line_ids
        self.env['dmag.dental.procedure'].add_from_workspace(visit.id, False, plan_line_id=line.id)
        self.assertEqual(line.state, 'done')
        self.assertEqual(plan.progress, 100)
        self.assertEqual(plan.state, 'done')
        self.assertEqual(line.sale_line_id.qty_delivered, 2)
        self.assertEqual(visit.payment_status, 'to_invoice')
        planned = self.env['dmag.dental.chart.entry'].search([
            ('patient_id', '=', self.patient.id), ('layer', '=', 'planned')])
        self.assertFalse(planned, 'Lớp kế hoạch phải được thay bằng lớp đã điều trị')

    def test_plan_without_second_opinion_service(self):
        data = self._plan()
        plan = self.env['dmag.treatment.plan'].browse(data['id'])
        opt_b = plan.option_ids[1]
        # B có dịch vụ không cần duyệt, nhưng kế hoạch có dịch vụ cần duyệt ở A → chỉ chặn khi chọn A
        opt_b.action_accept()
        self.assertEqual(plan.accepted_option_id, opt_b)
        with self.assertRaises(UserError):
            plan.option_ids[0].action_accept()

    def test_receptionist_accepts_option(self):
        """Lễ tân / tư vấn chốt phương án bệnh nhân chọn (không có quyền Bán hàng)."""
        recep = self.env['res.users'].create({
            'name': 'Lễ tân KH', 'login': 'recep_plan', 'email': 'recep_plan@dmag.test',
            'groups_id': [(6, 0, [self.env.ref('dmag_dental_base.group_dmag_receptionist').id])],
        })
        data = self._plan()
        plan = self.env['dmag.treatment.plan'].browse(data['id'])
        opt_b = plan.option_ids[1]
        opt_b.with_user(recep).action_accept()
        self.assertEqual(plan.accepted_option_id, opt_b)
        self.assertTrue(all(opt_b.line_ids.mapped('sale_line_id')))
