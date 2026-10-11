from odoo.tests import tagged

from odoo.addons.dmag_dental_clinic.tests.common import DentalCommon
from odoo.addons.dmag_dental_emr.models.odontogram_svg import occlusal_geometry, tooth_info


@tagged('post_install', '-at_install')
class TestOdontogramPrint(DentalCommon):

    def test_orientation_rules(self):
        # bên phải bệnh nhân (cung 1, 4) không lật ngang: mặt gần quay sang phải, về đường giữa
        self.assertEqual(tooth_info(16)['sx'], 1)
        self.assertEqual(tooth_info(46)['sx'], 1)
        self.assertEqual(tooth_info(26)['sx'], -1)
        self.assertEqual(tooth_info(36)['sx'], -1)
        self.assertTrue(tooth_info(55)['upper'] and tooth_info(55)['primary'])
        self.assertEqual(tooth_info(36)['roots'], 2)
        self.assertEqual(tooth_info(16)['roots'], 3)
        self.assertEqual(occlusal_geometry(tooth_info(11))['center_surface'], 'I')
        self.assertEqual(occlusal_geometry(tooth_info(36))['center_surface'], 'O')

    def test_chart_svg_in_record(self):
        visit = self._visit()
        self.env['dmag.dental.chart.entry'].add_from_chart(
            self.patient.id, ['36'], self.env.ref('dmag_dental_base.condition_caries').id,
            surfaces=['M', 'O'], visit_id=visit.id)
        chart = visit._emr_tooth_chart()
        svg = str(chart['svg'])
        self.assertTrue(svg.startswith('<svg'))
        self.assertIn('>36<', svg)
        self.assertIn('1MO', svg)  # ký hiệu chú giải + mặt răng dưới số răng
        self.assertIn('HÀM TRÊN', svg)
        self.assertIn('#E5484D', svg)  # màu sâu răng tô trên mặt răng
        html = self.env['ir.actions.report']._render_qweb_html(
            'dmag_dental_emr.report_dental_record', visit.ids)[0].decode()
        self.assertIn('PHẢI BỆNH NHÂN', html)
        self.assertIn('Mặt gần', html)
