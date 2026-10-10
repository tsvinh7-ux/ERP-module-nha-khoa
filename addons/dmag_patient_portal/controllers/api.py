"""REST JSON API cho ứng dụng di động bệnh nhân – /api/dmag/v1/.

Xác thực: ``Authorization: Bearer <API key>`` (res.users.apikeys của tài khoản bệnh nhân)
hoặc phiên đăng nhập cổng (cookie). Mọi dữ liệu lọc theo bệnh nhân người dùng được xem
(chính mình, gia đình khi là chủ hộ, người được giám hộ).
"""
import json
import logging

from odoo import _, fields, http
from odoo.exceptions import AccessDenied, UserError, ValidationError
from odoo.http import request

from .common import allowed_patients, patient_visits

_logger = logging.getLogger(__name__)
API_SCOPE = 'dmag_patient_api'


def _json(data, status=200):
    return request.make_json_response(data, status=status)


def _error(code, message, status):
    return _json({'error': {'code': code, 'message': message}}, status=status)


class DmagPatientApi(http.Controller):

    def _authenticate(self):
        """Trả về partner của người gọi, hoặc False."""
        auth = request.httprequest.headers.get('Authorization') or ''
        if auth.lower().startswith('bearer '):
            key = auth[7:].strip()
            try:
                uid = request.env['res.users.apikeys']._check_credentials(scope=API_SCOPE, key=key)
            except AccessDenied:
                uid = False
            if not uid:
                return False
            request.update_env(user=uid)
            return request.env.user.partner_id
        user = request.env.user
        if request.session.uid and user and not user._is_public():
            return user.partner_id
        return False

    def _scope(self, partner, patient_id=None):
        patients = allowed_patients(partner)
        if patient_id:
            try:
                patient_id = int(patient_id)
            except ValueError:
                return None
            patients = patients.filtered(lambda p: p.id == patient_id)
            if not patients:
                return None
        return patients

    def _patient_dict(self, patient, viewer):
        return {
            'id': patient.id,
            'name': patient.name,
            'patient_code': patient.patient_code or '',
            'relation': patient._dmag_portal_relation(viewer),
            'is_patient': patient.is_patient,
            'tier': patient.dmag_tier_id.name or '',
            'points': patient._dmag_points_balance() if patient.is_patient else 0,
        }

    @http.route('/api/dmag/v1/me', type='http', auth='public', methods=['GET'], csrf=False, sitemap=False)
    def me(self, **kw):
        partner = self._authenticate()
        if not partner:
            return _error('unauthorized', _('Cần đăng nhập hoặc API key.'), 401)
        patients = allowed_patients(partner)
        return _json({
            'user': {'id': request.env.user.id, 'name': request.env.user.name, 'login': request.env.user.login},
            'partner': {'id': partner.id, 'name': partner.name, 'phone': partner.mobile or partner.phone or '',
                        'email': partner.email or ''},
            'patients': [self._patient_dict(p.sudo(), partner) for p in patients],
        })

    @http.route('/api/dmag/v1/visits', type='http', auth='public', methods=['GET'], csrf=False, sitemap=False)
    def visits(self, patient_id=None, upcoming=None, limit=None, **kw):
        partner = self._authenticate()
        if not partner:
            return _error('unauthorized', _('Cần đăng nhập hoặc API key.'), 401)
        scope = self._scope(partner, patient_id)
        if scope is None:
            return _error('forbidden', _('Không có quyền xem bệnh nhân này.'), 403)
        flag = {'1': True, 'true': True, '0': False, 'false': False}.get((upcoming or '').lower())
        try:
            limit = min(int(limit), 200) if limit else 100
        except ValueError:
            limit = 100
        visits = patient_visits(scope, upcoming=flag, limit=limit)
        return _json({'items': [v._dmag_portal_card() for v in visits], 'count': len(visits)})

    @http.route('/api/dmag/v1/visit/<int:visit_id>', type='http', auth='public', methods=['GET'],
                csrf=False, sitemap=False)
    def visit(self, visit_id, **kw):
        partner = self._authenticate()
        if not partner:
            return _error('unauthorized', _('Cần đăng nhập hoặc API key.'), 401)
        visit = request.env['dmag.dental.visit'].sudo().browse(visit_id).exists()
        if not visit or visit.patient_id not in allowed_patients(partner):
            return _error('not_found', _('Không tìm thấy lượt khám.'), 404)
        return _json(visit._dmag_portal_detail())

    @http.route('/api/dmag/v1/plans', type='http', auth='public', methods=['GET'], csrf=False, sitemap=False)
    def plans(self, patient_id=None, **kw):
        partner = self._authenticate()
        if not partner:
            return _error('unauthorized', _('Cần đăng nhập hoặc API key.'), 401)
        scope = self._scope(partner, patient_id)
        if scope is None:
            return _error('forbidden', _('Không có quyền xem bệnh nhân này.'), 403)
        return _json({'items': request.env['dmag.dental.visit']._dmag_portal_plan_dicts(scope)})

    @http.route('/api/dmag/v1/loyalty', type='http', auth='public', methods=['GET'], csrf=False, sitemap=False)
    def loyalty(self, patient_id=None, **kw):
        partner = self._authenticate()
        if not partner:
            return _error('unauthorized', _('Cần đăng nhập hoặc API key.'), 401)
        scope = self._scope(partner, patient_id)
        if scope is None:
            return _error('forbidden', _('Không có quyền xem bệnh nhân này.'), 403)
        patient = scope.filtered(lambda p: p.id == int(patient_id)) if patient_id else \
            (partner if partner.sudo().is_patient else scope.filtered('is_patient')[:1])
        if not patient or not patient.sudo().is_patient:
            return _error('not_found', _('Chưa có hồ sơ bệnh nhân.'), 404)
        return _json(request.env['res.partner'].sudo().get_loyalty_summary(patient.id))

    @http.route('/api/dmag/v1/booking', type='http', auth='public', methods=['POST'], csrf=False, sitemap=False)
    def booking(self, **kw):
        partner = self._authenticate()
        if not partner:
            return _error('unauthorized', _('Cần đăng nhập hoặc API key.'), 401)
        if 'json' not in (request.httprequest.content_type or ''):
            return _error('bad_request', _('Gửi dữ liệu dạng application/json.'), 415)
        try:
            payload = json.loads(request.httprequest.get_data(as_text=True) or '{}')
        except ValueError:
            return _error('bad_request', _('JSON không hợp lệ.'), 400)
        patient = partner
        if payload.get('patient_id'):
            scope = self._scope(partner, payload['patient_id'])
            if not scope:
                return _error('forbidden', _('Không có quyền đặt lịch cho bệnh nhân này.'), 403)
            patient = scope
        patient = patient.sudo()
        values = dict(payload)
        values.setdefault('name', patient.name)
        values.setdefault('phone', patient.mobile or patient.phone or partner.sudo().mobile or partner.sudo().phone)
        try:
            visit = request.env['dmag.portal.booking.log'].sudo()._dmag_create_booking(
                values, ip=request.httprequest.remote_addr, channel='api',
                partner=patient if (patient.is_patient or payload.get('patient_id')) else None)
        except (UserError, ValidationError) as exc:
            return _error('invalid', exc.args[0], 400)
        return _json({'ok': True, 'visit': {
            'id': visit.id, 'name': visit.name, 'state': visit.state,
            'start': fields.Datetime.to_string(visit.scheduled_start),
        }}, status=201)
