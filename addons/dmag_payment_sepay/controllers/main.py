import json
import logging

from odoo import SUPERUSER_ID, http
from odoo.http import request

_logger = logging.getLogger(__name__)


class DmagSepayWebhook(http.Controller):

    @http.route('/dmag/sepay/webhook', type='http', auth='none', methods=['POST'], csrf=False, save_session=False)
    def sepay_webhook(self, **_kw):
        """Webhook SePay: body JSON, header ``Authorization: Apikey <key>``.

        Trả ``{"success": true}`` (HTTP 200) khi đã ghi nhận; 401 nếu sai khóa (SePay sẽ gửi lại).
        """
        if not request.db:
            return request.make_json_response({'success': False, 'message': 'No database'}, status=404)
        try:
            payload = json.loads(request.httprequest.get_data(as_text=True) or 'null')
        except ValueError:
            payload = None
        auth = request.httprequest.headers.get('Authorization', '')
        env = request.env(user=SUPERUSER_ID, su=True)
        status, body = env['dmag.sepay.transaction']._sepay_handle_webhook(auth, payload)
        return request.make_json_response(body, status=status)
