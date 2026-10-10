from odoo.tests import HttpCase, tagged

from .common import JourneyCommon


@tagged('post_install', '-at_install')
class TestNpsHttp(HttpCase, JourneyCommon):

    def test_nps_page(self):
        visit = self._done_visit()
        response = self.env['dmag.nps.response']._dmag_create_for_visit(visit)
        res = self.url_open('/dmag/nps/%s' % response.sudo().token)
        self.assertEqual(res.status_code, 200)
        self.assertIn('Gửi đánh giá', res.text)
        res = self.url_open('/dmag/nps/khong-ton-tai')
        self.assertEqual(res.status_code, 404)
        response.submit(9)
        res = self.url_open('/dmag/nps/%s' % response.sudo().token)
        self.assertIn('g.page/r/dmag-test', res.text)
