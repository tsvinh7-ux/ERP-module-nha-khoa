from odoo import _, http
from odoo.exceptions import UserError, ValidationError
from odoo.http import request

from .common import viewer_partner


class DmagBooking(http.Controller):

    def _booking_values(self, post=None, error=None):
        Log = request.env['dmag.portal.booking.log'].sudo()
        partner = viewer_partner()
        post = dict(post or {})
        if partner and not post:
            post = {'name': partner.name, 'phone': partner.mobile or partner.phone or ''}
        slots = ['%02d:%02d' % (h, m) for h in range(8, 20) for m in (0, 30)]
        return {
            'services': Log._booking_services(),
            'branches': Log._booking_branches(),
            'slots': slots,
            'post': post,
            'error': error,
        }

    @http.route(['/dental/booking'], type='http', auth='public', methods=['GET'], sitemap=False, website=True)
    def booking_form(self, **kw):
        return request.render('dmag_patient_portal.booking_page', self._booking_values(kw if kw else None))

    @http.route(['/dental/booking'], type='http', auth='public', methods=['POST'], csrf=True, sitemap=False, website=True)
    def booking_submit(self, **post):
        if post.get('website_url'):  # bẫy bot (trường ẩn)
            return request.redirect('/dental/booking/thanks')
        post.pop('csrf_token', None)
        values = dict(post, consent=post.get('consent') in ('on', '1', 'true', True))
        try:
            visit = request.env['dmag.portal.booking.log'].sudo()._dmag_create_booking(
                values, ip=request.httprequest.remote_addr, channel='web')
        except (UserError, ValidationError) as exc:
            return request.render('dmag_patient_portal.booking_page',
                                  self._booking_values(post, error=exc.args[0]), status=400)
        request.session['dmag_last_booking'] = visit.name
        return request.redirect('/dental/booking/thanks')

    @http.route(['/dental/booking/thanks'], type='http', auth='public', sitemap=False, website=True)
    def booking_thanks(self, **kw):
        return request.render('dmag_patient_portal.booking_thanks', {
            'booking_name': request.session.get('dmag_last_booking') or '',
        })
