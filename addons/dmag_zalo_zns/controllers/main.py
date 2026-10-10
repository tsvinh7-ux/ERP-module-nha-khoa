import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class DmagZaloWebhook(http.Controller):

    @http.route(['/dmag/zalo/webhook', '/dmag/zalo/webhook/<string:company_key>'],
                type='http', auth='public', methods=['POST'], csrf=False, save_session=False)
    def dmag_zalo_webhook(self, company_key=None, **kwargs):
        raw = request.httprequest.get_data(as_text=True)
        signature = request.httprequest.headers.get('X-ZEvent-Signature')
        _event, accepted = request.env['dmag.zns.webhook.event'].sudo()._dmag_receive(
            raw, signature=signature, company_key=company_key)
        # Zalo yêu cầu phản hồi HTTP 200 nhanh; sai chữ ký trả 401.
        return request.make_response('ok' if accepted else 'invalid signature',
                                     status=200 if accepted else 401)
