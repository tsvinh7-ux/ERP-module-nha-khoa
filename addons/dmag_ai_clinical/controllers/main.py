import json

from odoo import http
from odoo.exceptions import AccessError, UserError
from odoo.http import request


class DmagAiClinicalController(http.Controller):

    @http.route('/dmag_ai_clinical/stt', type='http', auth='user', methods=['POST'], csrf=True)
    def stt(self, visit_id=None, provider=None, audio=None, **kw):
        """Nhận file ghi âm (MediaRecorder) từ trình duyệt → chuyển tiếp tới FPT.AI / Viettel AI → trả văn bản."""
        try:
            data = audio.read() if audio else b''
            mimetype = (audio.mimetype if audio else '') or 'audio/webm'
            res = request.env['dmag.ai.clinical'].stt_transcribe(int(visit_id or 0), provider, data, mimetype)
            body = {'ok': True, 'text': res['text'], 'provider': res['provider']}
        except (UserError, AccessError) as e:
            body = {'ok': False, 'error': str(e.args[0] if e.args else e)}
        return request.make_response(json.dumps(body, ensure_ascii=False),
                                     headers=[('Content-Type', 'application/json; charset=utf-8')])
