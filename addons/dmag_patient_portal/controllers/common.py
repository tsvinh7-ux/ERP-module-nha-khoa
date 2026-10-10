from odoo import fields
from odoo.http import request


def viewer_partner():
    """Partner của người đang đăng nhập (False nếu là khách)."""
    user = request.env.user
    if not user or user._is_public():
        return False
    return user.partner_id


def allowed_patients(partner):
    if not partner:
        return request.env['res.partner']
    return partner._dmag_portal_patients()


def patient_visits(patients, upcoming=None, limit=None):
    Visit = request.env['dmag.dental.visit'].sudo()
    domain = [('patient_id', 'in', patients.ids)]
    now = fields.Datetime.now()
    if upcoming is True:
        domain += [('state', 'in', ('draft', 'confirmed')), ('scheduled_start', '>=', now)]
        return Visit.search(domain, order='scheduled_start asc', limit=limit)
    if upcoming is False:
        domain += [('state', '=', 'done')]
    else:
        domain += [('state', '!=', 'cancel')]
    return Visit.search(domain, order='scheduled_start desc', limit=limit)
