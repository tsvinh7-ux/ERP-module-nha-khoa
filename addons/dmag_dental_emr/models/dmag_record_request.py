from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

from odoo.addons.dmag_dental_base.models.dmag_access import is_director, is_manager, is_workflow

REQUESTER_TYPES = [
    ('patient', 'Người bệnh'),
    ('representative', 'Người đại diện hợp pháp của người bệnh'),
    ('authority', 'Cơ quan nhà nước có thẩm quyền'),
    ('insurer', 'Cơ quan bảo hiểm'),
    ('researcher', 'Nghiên cứu, đào tạo'),
]
REQUEST_SCOPES = [
    ('summary', 'Bản tóm tắt hồ sơ bệnh án'),
    ('copy', 'Bản sao / sao chụp hồ sơ bệnh án'),
    ('view', 'Đọc, xem hồ sơ bệnh án tại cơ sở'),
]
EDITABLE_AFTER_APPROVAL = {'provided_method', 'note'}


class DmagRecordRequest(models.Model):
    """Yêu cầu xem / sao chụp / tóm tắt hồ sơ bệnh án (Luật KCB 2023 Điều 12, Điều 69).

    Yêu cầu phải bằng văn bản (đính kèm bắt buộc); Quản lý duyệt; ghi rõ người cung cấp, thời điểm.
    """
    _name = 'dmag.record.request'
    _description = 'Yêu cầu sao chụp / tóm tắt hồ sơ bệnh án'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'request_date desc, id desc'

    name = fields.Char('Số yêu cầu', required=True, readonly=True, copy=False, default='/')
    company_id = fields.Many2one('res.company', string='Phòng khám', required=True,
                                 default=lambda self: self.env.company, index=True)
    patient_id = fields.Many2one('res.partner', string='Người bệnh', required=True, index=True, tracking=True,
                                 domain=[('is_patient', '=', True)])
    visit_ids = fields.Many2many('dmag.dental.visit', string='Hồ sơ / lượt khám được yêu cầu',
                                 domain="[('patient_id', '=', patient_id)]")
    request_date = fields.Date('Ngày nhận yêu cầu', required=True, default=fields.Date.context_today)
    requester_type = fields.Selection(REQUESTER_TYPES, string='Người yêu cầu là', required=True,
                                      default='patient', tracking=True)
    requester_name = fields.Char('Họ tên / tên cơ quan yêu cầu', tracking=True)
    requester_identity = fields.Char('Số định danh / số văn bản của người yêu cầu')
    requester_relation = fields.Char('Quan hệ với người bệnh')
    legal_basis = fields.Text('Căn cứ pháp lý / mục đích yêu cầu', tracking=True)
    scope = fields.Selection(REQUEST_SCOPES, string='Nội dung yêu cầu', required=True, default='summary',
                             tracking=True)
    attachment_ids = fields.Many2many('ir.attachment', string='Văn bản yêu cầu (bản quét)',
                                      help='Bắt buộc: yêu cầu cung cấp hồ sơ phải bằng văn bản.')
    state = fields.Selection([
        ('draft', 'Mới tiếp nhận'),
        ('approved', 'Đã duyệt'),
        ('provided', 'Đã cung cấp'),
        ('rejected', 'Từ chối'),
    ], string='Trạng thái', default='draft', required=True, tracking=True, copy=False)
    approved_by_id = fields.Many2one('res.users', string='Người duyệt', readonly=True, copy=False)
    approved_at = fields.Datetime('Thời điểm duyệt', readonly=True, copy=False)
    provided_by_id = fields.Many2one('res.users', string='Người cung cấp', readonly=True, copy=False)
    provided_at = fields.Datetime('Thời điểm cung cấp', readonly=True, copy=False)
    provided_method = fields.Selection([
        ('direct', 'Trao trực tiếp'),
        ('post', 'Gửi bưu điện'),
        ('electronic', 'Gửi điện tử'),
        ('onsite', 'Đọc, xem tại cơ sở'),
    ], string='Hình thức cung cấp', tracking=True)
    reject_reason = fields.Text('Lý do từ chối', tracking=True)
    note = fields.Text('Ghi chú')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                vals['name'] = self.env['ir.sequence'].next_by_code('dmag.record.request') or '/'
        return super().create(vals_list)

    def write(self, vals):
        if not is_workflow(self.env) and not is_director(self.env):
            locked = self.filtered(lambda r: r.state != 'draft')
            if locked and set(vals) - EDITABLE_AFTER_APPROVAL - {'message_main_attachment_id'}:
                raise AccessError(_('Yêu cầu %s đã được xử lý – không sửa được.', ', '.join(locked.mapped('name'))))
        return super().write(vals)

    def unlink(self):
        if self.filtered(lambda r: r.state != 'draft'):
            raise UserError(_('Không xóa được yêu cầu đã duyệt / đã cung cấp / đã từ chối (lưu vết theo luật).'))
        return super().unlink()

    def _check_request_complete(self):
        self.ensure_one()
        missing = []
        if not self.attachment_ids:
            missing.append(_('Văn bản yêu cầu (bản quét) – Luật Khám bệnh, chữa bệnh yêu cầu bằng văn bản'))
        if self.requester_type != 'patient' and not self.requester_name:
            missing.append(_('Họ tên / tên cơ quan yêu cầu'))
        if self.requester_type != 'patient' and not self.legal_basis:
            missing.append(_('Căn cứ pháp lý / mục đích yêu cầu'))
        if self.requester_type == 'representative' and not self.requester_relation:
            missing.append(_('Quan hệ với người bệnh'))
        if missing:
            raise UserError(_('Yêu cầu %(name)s còn thiếu:\n%(items)s', name=self.name,
                              items='\n'.join('  • ' + m for m in missing)))

    def action_approve(self):
        if not is_manager(self.env):
            raise AccessError(_('Chỉ Quản lý phòng khám trở lên được duyệt yêu cầu cung cấp hồ sơ bệnh án.'))
        for req in self:
            if req.state != 'draft':
                raise UserError(_('Yêu cầu %s không ở trạng thái chờ duyệt.', req.name))
            req._check_request_complete()
        self.with_context(dmag_workflow=True).write({
            'state': 'approved', 'approved_by_id': self.env.uid, 'approved_at': fields.Datetime.now()})
        return True

    def action_reject(self):
        if not is_manager(self.env):
            raise AccessError(_('Chỉ Quản lý phòng khám trở lên được từ chối yêu cầu.'))
        for req in self:
            if req.state != 'draft':
                raise UserError(_('Yêu cầu %s không ở trạng thái chờ duyệt.', req.name))
            if not req.reject_reason:
                raise UserError(_('Ghi rõ lý do từ chối cho yêu cầu %s.', req.name))
        self.with_context(dmag_workflow=True).write({
            'state': 'rejected', 'approved_by_id': self.env.uid, 'approved_at': fields.Datetime.now()})
        return True

    def _get_visits(self):
        self.ensure_one()
        return self.visit_ids or self.env['dmag.dental.visit'].search([
            ('patient_id', '=', self.patient_id.id), ('record_state', '=', 'signed')])

    def action_provide(self):
        for req in self:
            if req.state != 'approved':
                raise UserError(_('Yêu cầu %s chưa được duyệt.', req.name))
            if not req.provided_method:
                raise UserError(_('Chọn hình thức cung cấp cho yêu cầu %s.', req.name))
            visits = req._get_visits()
            self.env['dmag.record.access.log']._log(
                visits or req, 'provide',
                document=_('%(req)s – %(scope)s – cho %(who)s', req=req.name, scope=dict(REQUEST_SCOPES)[req.scope],
                           who=req.requester_name or req.patient_id.name))
        self.with_context(dmag_workflow=True).write({
            'state': 'provided', 'provided_by_id': self.env.uid, 'provided_at': fields.Datetime.now()})
        return True

    def action_print(self):
        self.ensure_one()
        if self.state not in ('approved', 'provided'):
            raise UserError(_('Chỉ in hồ sơ cho yêu cầu đã được duyệt.'))
        visits = self._get_visits()
        if not visits:
            raise UserError(_('Người bệnh chưa có bệnh án đã ký để cung cấp.'))
        xmlid = ('dmag_dental_emr.action_report_record_summary' if self.scope == 'summary'
                 else 'dmag_dental_emr.action_report_dental_record')
        return self.env.ref(xmlid).report_action(visits)
