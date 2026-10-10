from werkzeug.exceptions import Forbidden, NotFound

from odoo import _, http
from odoo.http import request

from odoo.addons.portal.controllers.portal import CustomerPortal

from .common import allowed_patients, patient_visits, viewer_partner


class DmagPatientPortal(CustomerPortal):

    def _dmag_values(self, patient_id=None, page=None):
        partner = viewer_partner()
        patients = allowed_patients(partner)
        current = patients.filtered(lambda p: p.id == int(patient_id)) if patient_id else patients.browse()
        if patient_id and not current:
            raise Forbidden()
        scope = current or patients
        return {
            'viewer': partner,
            'patients': patients,
            'current_patient': current,
            'scope': scope,
            'dmag_page': page,
            'page_name': 'dmag_dental',
            'relation': lambda p: p._dmag_portal_relation(partner),
            'fmt_money': lambda amount: '{:,.0f}'.format(amount or 0).replace(',', '.') + ' ₫',
        }

    @http.route(['/my/dental'], type='http', auth='user')
    def dmag_home(self, patient_id=None, **kw):
        values = self._dmag_values(patient_id, 'home')
        scope = values['scope']
        upcoming = patient_visits(scope, upcoming=True, limit=5)
        recent = patient_visits(scope, upcoming=False, limit=3)
        loyalty_patient = values['current_patient'] or values['viewer']
        loyalty = False
        if loyalty_patient and loyalty_patient.is_patient:
            loyalty = request.env['res.partner'].sudo().get_loyalty_summary(loyalty_patient.id)
        values.update({
            'upcoming': [v._dmag_portal_card() for v in upcoming],
            'recent': [v._dmag_portal_card() for v in recent],
            'loyalty': loyalty,
        })
        return request.render('dmag_patient_portal.portal_dental_home', values)

    @http.route(['/my/dental/visits'], type='http', auth='user')
    def dmag_visits(self, patient_id=None, **kw):
        values = self._dmag_values(patient_id, 'visits')
        visits = patient_visits(values['scope'])
        values['visits'] = [v._dmag_portal_card() for v in visits]
        return request.render('dmag_patient_portal.portal_dental_visits', values)

    def _dmag_visit_check_access(self, visit_id, access_token=None):
        visit = request.env['dmag.dental.visit'].sudo().browse(visit_id).exists()
        if not visit:
            raise NotFound()
        if access_token:
            if visit._dmag_portal_check_token(access_token):
                return visit
            raise Forbidden()
        partner = viewer_partner()
        if partner and visit.patient_id in allowed_patients(partner):
            return visit
        raise Forbidden()

    @http.route(['/my/dental/visit/<int:visit_id>'], type='http', auth='public')
    def dmag_visit(self, visit_id, access_token=None, **kw):
        try:
            visit = self._dmag_visit_check_access(visit_id, access_token)
        except Forbidden:
            if request.env.user._is_public() and not access_token:
                return request.redirect('/web/login?redirect=/my/dental/visit/%s' % visit_id)
            return request.render('dmag_patient_portal.portal_dental_denied', {
                'message': _('Link đã hết hạn hoặc bạn không có quyền xem lượt khám này.'),
            }, status=403)
        values = self._dmag_values(None, 'visit') if viewer_partner() else {
            'viewer': False, 'patients': request.env['res.partner'], 'current_patient': False,
            'dmag_page': 'visit', 'page_name': 'dmag_dental',
            'fmt_money': lambda amount: '{:,.0f}'.format(amount or 0).replace(',', '.') + ' ₫',
        }
        values.update({'visit': visit._dmag_portal_detail(), 'shared_link': bool(access_token),
                       'company': visit.company_id})
        return request.render('dmag_patient_portal.portal_dental_visit', values)

    @http.route(['/my/dental/plans'], type='http', auth='user')
    def dmag_plans(self, patient_id=None, **kw):
        values = self._dmag_values(patient_id, 'plans')
        values['plans'] = request.env['dmag.dental.visit']._dmag_portal_plan_dicts(values['scope'])
        return request.render('dmag_patient_portal.portal_dental_plans', values)

    @http.route(['/my/dental/warranty'], type='http', auth='user')
    def dmag_warranty(self, patient_id=None, **kw):
        values = self._dmag_values(patient_id, 'warranty')
        values['cards'] = request.env['dmag.dental.visit']._dmag_portal_warranty_dicts(values['scope'])
        return request.render('dmag_patient_portal.portal_dental_warranty', values)

    @http.route(['/my/dental/loyalty'], type='http', auth='user')
    def dmag_loyalty(self, patient_id=None, **kw):
        values = self._dmag_values(patient_id, 'loyalty')
        patient = values['current_patient'] or values['viewer']
        if not patient.is_patient and values['patients'] - values['viewer']:
            patient = (values['patients'] - values['viewer'])[0]
        values['loyalty'] = request.env['res.partner'].sudo().get_loyalty_summary(patient.id) \
            if patient.is_patient else False
        return request.render('dmag_patient_portal.portal_dental_loyalty', values)
