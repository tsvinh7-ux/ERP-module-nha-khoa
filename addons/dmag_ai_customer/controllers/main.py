import base64
import logging

from werkzeug.exceptions import Forbidden, NotFound

from odoo import _, fields, http
from odoo.exceptions import AccessError, UserError
from odoo.http import request

from odoo.addons.dmag_patient_portal.controllers.common import allowed_patients, viewer_partner
from odoo.addons.dmag_patient_portal.controllers.portal import DmagPatientPortal

_logger = logging.getLogger(__name__)
MAX_UPLOAD = 8 * 1024 * 1024


class DmagAiCustomerPortal(DmagPatientPortal):

    # ------------------------------------------------------------------ /my/dental: câu hỏi theo dõi đang chờ (AI-18)
    @http.route()
    def dmag_home(self, patient_id=None, **kw):
        response = super().dmag_home(patient_id=patient_id, **kw)
        partner = viewer_partner()
        if partner and hasattr(response, 'qcontext'):
            followups = request.env['dmag.ai.followup'].sudo().search([
                ('patient_id', 'in', allowed_patients(partner).ids), ('state', '=', 'sent')], limit=3)
            response.qcontext['dmag_ai_followups'] = [{
                'token': f.token, 'name': f.name, 'procedures': f.procedures or '',
                'checkpoint': dict(f._fields['checkpoint'].selection)[f.checkpoint]} for f in followups]
        return response

    # ------------------------------------------------------------------ AI-17 trợ lý cổng bệnh nhân
    @http.route('/my/dental/assistant/ask', type='json', auth='user', methods=['POST'])
    def dmag_ai_assistant_ask(self, question=None, history=None, **kw):
        partner = viewer_partner()
        if not partner:
            raise Forbidden()
        try:
            return request.env['dmag.ai.portal.assistant'].sudo().ask(partner, question, history)
        except (UserError, AccessError) as e:
            return {'answer': str(e), 'error': True}

    @http.route('/my/dental/assistant/consent', type='json', auth='user', methods=['POST'])
    def dmag_ai_assistant_consent(self, **kw):
        partner = viewer_partner()
        if not partner:
            raise Forbidden()
        partner.sudo().write({'dmag_ai_consent': True})
        partner.sudo().message_post(body=_('Bệnh nhân tự đồng ý hỗ trợ bằng AI trên cổng bệnh nhân (trợ lý AI-17).'))
        return {'ok': True}

    # ------------------------------------------------------------------ AI-19 mô phỏng nụ cười trên cổng
    @http.route('/my/dental/smile', type='http', auth='user', website=True, methods=['GET', 'POST'])
    def dmag_ai_smile(self, smile_id=None, **post):
        values = self._dmag_values(None, 'smile')
        partner = values['viewer']
        error = None
        smile = request.env['dmag.ai.smile']
        if request.httprequest.method == 'POST':
            upload = request.httprequest.files.get('photo')
            data = upload.read(MAX_UPLOAD + 1) if upload else b''
            if not data:
                error = _('Bạn chưa chọn ảnh.')
            elif len(data) > MAX_UPLOAD:
                error = _('Ảnh quá lớn (tối đa 8 MB).')
            elif not post.get('consent'):
                error = _('Cần đồng ý để phòng khám xử lý ảnh.')
            else:
                try:
                    if not partner.sudo().dmag_ai_consent:
                        partner.sudo().write({'dmag_ai_consent': True})
                    smile = request.env['dmag.ai.smile'].sudo().create({
                        'patient_id': partner.id, 'source': 'portal', 'image_before': base64.b64encode(data),
                        'company_id': request.env.company.id})
                    smile.action_generate()
                    return request.redirect('/my/dental/smile?smile_id=%s' % smile.id)
                except UserError as e:
                    error = str(e)
        elif smile_id:
            smile = self._dmag_smile_check(smile_id)
        values.update({'smile': smile, 'error': error,
                       'smiles': request.env['dmag.ai.smile'].sudo().search([('patient_id', '=', partner.id)], limit=5)})
        return request.render('dmag_ai_customer.portal_dental_smile', values)

    def _dmag_smile_check(self, smile_id):
        partner = viewer_partner()
        smile = request.env['dmag.ai.smile'].sudo().browse(int(smile_id)).exists()
        if not smile or not partner or smile.patient_id not in allowed_patients(partner):
            raise NotFound()
        return smile

    @http.route('/my/dental/smile/<int:smile_id>/image', type='http', auth='user')
    def dmag_ai_smile_image(self, smile_id, **kw):
        smile = self._dmag_smile_check(smile_id)
        data = base64.b64decode(smile.image_result or smile.image_before)
        return request.make_response(data, headers=[('Content-Type', 'image/jpeg'), ('Cache-Control', 'private, max-age=600')])


class DmagAiFollowupController(http.Controller):
    """AI-18 – trang công khai (link trong tin nhắn) để khách trả lời câu hỏi theo dõi sau điều trị."""

    def _get(self, token):
        followup = request.env['dmag.ai.followup'].sudo().search([('token', '=', token)], limit=1) if token else None
        if not followup:
            raise NotFound()
        return followup

    @http.route('/dmag/followup/<string:token>', type='http', auth='public', methods=['GET'], website=False, sitemap=False)
    def dmag_followup_form(self, token, **kw):
        followup = self._get(token)
        return request.render('dmag_ai_customer.followup_page', {'fu': followup, 'done': followup.state in ('answered', 'alert', 'closed'),
                                                                 'reply': followup.reply_to_patient, 'error': None})

    @http.route('/dmag/followup/<string:token>', type='http', auth='public', methods=['POST'], csrf=True, sitemap=False)
    def dmag_followup_submit(self, token, **post):
        followup = self._get(token)
        if followup.state == 'expired':
            return request.render('dmag_ai_customer.followup_page', {'fu': followup, 'done': True,
                                                                     'reply': _('Phiếu đã hết hạn.'), 'error': None})
        try:
            reply = followup.submit_answers(post.get('pain'), post.get('bleeding'), post.get('swelling'),
                                            post.get('fever') == '1', post.get('free_text'), channel='portal')
        except UserError as e:
            return request.render('dmag_ai_customer.followup_page', {'fu': followup, 'done': False, 'reply': None,
                                                                     'error': str(e)})
        return request.render('dmag_ai_customer.followup_page', {'fu': followup, 'done': True, 'reply': reply, 'error': None})
