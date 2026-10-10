from odoo import _, fields, http
from odoo.exceptions import UserError, ValidationError
from odoo.http import request


class DmagNpsController(http.Controller):

    def _company(self, response):
        return response.company_id if response else request.env.company.sudo()

    def _unavailable(self, response, title, message, status=200):
        return request.render('dmag_dental_journey.nps_unavailable', {
            'company': self._company(response), 'title': title, 'message': message,
        }, status=status)

    def _thanks(self, response):
        company = response.company_id
        return request.render('dmag_dental_journey.nps_thanks', {
            'company': company,
            'category': response.category,
            'review_url': company.dmag_google_review_url,
            'referral_message': company.dmag_referral_message,
            'referral_code': response.partner_id.patient_code,
        })

    @http.route('/dmag/nps/<string:token>', type='http', auth='public', methods=['GET'], sitemap=False)
    def nps_form(self, token, score=None, **kwargs):
        response = request.env['dmag.nps.response'].sudo()._dmag_from_token(token)
        if not response:
            return self._unavailable(response, _('Không tìm thấy phiếu khảo sát'),
                                     _('Đường dẫn không đúng hoặc đã bị thu hồi.'), status=404)
        if response.state == 'answered':
            return self._thanks(response)
        if response.expire_date and response.expire_date < fields.Datetime.now():
            return self._unavailable(response, _('Phiếu khảo sát đã hết hạn'),
                                     _('Cảm ơn bạn đã quan tâm. Bạn có thể góp ý trực tiếp qua hotline phòng khám.'))
        try:
            preset = int(score) if score not in (None, '') else None
        except ValueError:
            preset = None
        return request.render('dmag_dental_journey.nps_page', {
            'company': response.company_id,
            'partner_name': response.partner_id.name,
            'token': token,
            'preset': preset,
            'error': False,
        })

    @http.route('/dmag/nps/<string:token>/submit', type='http', auth='public', methods=['POST'], sitemap=False)
    def nps_submit(self, token, score=None, comment=None, **kwargs):
        response = request.env['dmag.nps.response'].sudo()._dmag_from_token(token)
        if not response:
            return self._unavailable(response, _('Không tìm thấy phiếu khảo sát'),
                                     _('Đường dẫn không đúng hoặc đã bị thu hồi.'), status=404)
        if response.state == 'answered':
            return self._thanks(response)
        try:
            response.submit(score, (comment or '').strip()[:2000] or False)
        except (UserError, ValidationError) as exc:
            return request.render('dmag_dental_journey.nps_page', {
                'company': response.company_id, 'partner_name': response.partner_id.name,
                'token': token, 'preset': None, 'error': str(exc.args[0] if exc.args else exc),
            })
        return self._thanks(response)
