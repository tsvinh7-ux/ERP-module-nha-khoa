import pytz

from odoo import _, api, fields, models
from odoo.exceptions import AccessError

from odoo.addons.dmag_dental_base.models.dmag_access import check_director, is_director, is_workflow
from odoo.addons.dmag_dental_clinic.models.dmag_dental_visit import PAYMENT_METHODS

from .dmag_sepay_config import DEFAULT_TZ


def company_today(company, dt=None):
    """Ngày địa phương (theo múi giờ của phòng khám) của một thời điểm UTC."""
    tz = pytz.timezone(company.partner_id.tz or DEFAULT_TZ)
    dt = dt or fields.Datetime.now()
    return pytz.utc.localize(dt).astimezone(tz).date()


class DmagPaymentLog(models.Model):
    """Nhật ký thu tiền: một dòng cho mỗi lần ``visit.register_payment`` – nguồn số liệu chốt két."""
    _name = 'dmag.payment.log'
    _description = 'Nhật ký thu tiền'
    _order = 'date desc, id desc'

    visit_id = fields.Many2one('dmag.dental.visit', string='Lượt khám', required=True, index=True,
                               ondelete='restrict', readonly=True)
    company_id = fields.Many2one('res.company', string='Phòng khám', required=True, index=True, readonly=True)
    patient_id = fields.Many2one(related='visit_id.patient_id', string='Bệnh nhân', store=True)
    method = fields.Selection(PAYMENT_METHODS, string='Phương thức', required=True, readonly=True)
    amount = fields.Monetary('Số tiền', currency_field='currency_id', readonly=True)
    currency_id = fields.Many2one(related='company_id.currency_id')
    reference = fields.Char('Tham chiếu', readonly=True)
    source = fields.Selection([
        ('counter', 'Tại quầy'),
        ('sepay', 'SePay tự động'),
        ('manual_match', 'Đối soát thủ công'),
    ], string='Nguồn', default='counter', required=True, readonly=True)
    user_id = fields.Many2one('res.users', string='Người thu', readonly=True)
    date = fields.Datetime('Thời điểm', default=fields.Datetime.now, required=True, readonly=True)
    local_date = fields.Date('Ngày', required=True, index=True, readonly=True)
    payment_ids = fields.Many2many('account.payment', string='Chứng từ thanh toán', readonly=True,
                                   groups='account.group_account_invoice')
    sepay_transaction_id = fields.Many2one('dmag.sepay.transaction', string='Giao dịch SePay', readonly=True)
    closing_id = fields.Many2one('dmag.cash.closing', string='Biên bản chốt két', readonly=True, index=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('local_date'):
                company = self.env['res.company'].browse(vals.get('company_id')) or self.env.company
                vals['local_date'] = company_today(company)
        return super().create(vals_list)

    def write(self, vals):
        if not (is_workflow(self.env) or is_director(self.env)):
            raise AccessError(_('Nhật ký thu tiền không sửa được – liên hệ Giám đốc / Quản lý cấp cao.'))
        return super().write(vals)

    def unlink(self):
        check_director(self.env, _('Chỉ Giám đốc / Quản lý cấp cao được xóa nhật ký thu tiền.'))
        return super().unlink()
