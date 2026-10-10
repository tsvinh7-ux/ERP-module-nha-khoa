from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from odoo.addons.dmag_dental_clinic.tests.common import DentalCommon


@tagged('post_install', '-at_install')
class TestLabOrder(DentalCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.lab = cls.env['res.partner'].create({'name': 'Labo T', 'is_dental_lab': True, 'is_company': True})
        cls.assistant_user = cls.env['res.users'].create({
            'name': 'Phụ tá Lab', 'login': 'pt_lab_test', 'email': 'ptlab@dmag.test',
            'groups_id': [(6, 0, [cls.env.ref('dmag_dental_base.group_dmag_assistant').id])],
        })
        cls.today = fields.Date.context_today(cls.env.user)

    def _order(self, **kw):
        vals = {
            'patient_id': self.patient.id,
            'lab_partner_id': self.lab.id,
            'work_type': 'crown_bridge',
            'tooth_ids': [(6, 0, self.tooth_36.ids)],
            'shade': 'A2',
            'material': 'zirconia',
            'impression_type': 'scan',
            'cost': 900000,
            'due_date': self.today + timedelta(days=5),
        }
        vals.update(kw)
        return self.env['dmag.lab.order'].with_user(self.assistant_user).create(vals)

    def test_send_creates_purchase_order(self):
        order = self._order()
        self.assertTrue(order.name.startswith('LAB'))
        order.action_send()
        self.assertEqual(order.state, 'sent')
        self.assertEqual(order.sent_date, self.today)
        po = order.sudo().purchase_order_id
        self.assertTrue(po)
        self.assertEqual(po.partner_id, self.lab)
        self.assertEqual(po.state, 'purchase')
        self.assertEqual(po.amount_untaxed, 900000)
        self.assertIn(order.name, po.order_line.name)
        # Sau khi gửi, nhân viên không sửa được chi phí
        with self.assertRaises(AccessError):
            order.write({'cost': 500000})
        with self.assertRaises(AccessError):
            order.write({'state': 'fitted'})
        # Ghi chú / hạn trả vẫn sửa được
        order.write({'note': 'Gọi labo xác nhận'})
        # Giám đốc sửa chi phí → đồng bộ đơn mua
        order.with_user(self.env.ref('base.user_admin')).write({'cost': 1000000})
        self.assertEqual(po.amount_untaxed, 1000000)
        # Nhân viên không hủy được phiếu đã gửi
        with self.assertRaises(AccessError):
            order.action_cancel()

    def test_flow_tryin_fit_and_remake(self):
        order = self._order()
        order.action_send()
        order.action_start()
        self.env['dmag.lab.tryin'].with_user(self.assistant_user).create({
            'order_id': order.id, 'step': 'framework', 'result': 'ok'})
        self.assertEqual(order.state, 'try_in')
        order.action_receive()
        self.assertEqual(order.received_date, self.today)
        with self.assertRaises(UserError):
            order.action_remake()  # thiếu lý do
        order.remake_reason = 'Sai màu'
        action = order.action_remake()
        self.assertEqual(order.state, 'remake')
        new = self.env['dmag.lab.order'].browse(action['res_id'])
        self.assertEqual(new.remake_of_id, order)
        self.assertEqual(new.state, 'draft')
        self.assertEqual(new.shade, 'A2')
        new.write({'due_date': self.today + timedelta(days=3)})
        new.action_send()
        new.action_receive()
        new.action_fit()
        self.assertEqual(new.state, 'fitted')

    def test_overdue_and_kpi(self):
        order = self._order(due_date=self.today, sent_date=self.today - timedelta(days=7))
        order.action_send()
        self.assertFalse(order.is_late)
        order.sudo().with_context(dmag_workflow=True).write({'due_date': self.today - timedelta(days=2)})
        self.assertTrue(order.is_late)
        self.assertEqual(order.late_days, 2)
        Order = self.env['dmag.lab.order']
        self.assertIn(order, Order.search([('is_late', '=', True)]))
        self.assertNotIn(order, Order.search([('is_late', '=', False)]))
        Order._cron_check_overdue()
        self.assertEqual(len(order.activity_ids), 1)
        Order._cron_check_overdue()
        self.assertEqual(len(order.activity_ids), 1, 'Không tạo trùng việc nhắc')

        # Doanh thu: 1 thủ thuật trám 400.000 hôm nay
        visit = self._visit(scheduled_start=fields.Datetime.now())
        visit.action_check_in()
        visit.action_start()
        self.env['dmag.dental.procedure'].add_from_workspace(visit.id, self.svc_filling.id, teeth=['36'])
        kpi = Order.get_lab_kpis(self.today - timedelta(days=30), self.today)
        self.assertEqual(kpi['lab_cost'], 900000)
        self.assertGreaterEqual(kpi['revenue'], 400000)
        self.assertEqual(kpi['late_count'] >= 1, True)
        self.assertAlmostEqual(kpi['lab_cost_ratio'], round(900000 / kpi['revenue'] * 100, 2))
        self.assertTrue(kpi['alert'])
        order.action_receive()
        self.assertFalse(order.is_late)
        self.assertFalse(order.activity_ids)
