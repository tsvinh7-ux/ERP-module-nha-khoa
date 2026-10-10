import base64
import json
import logging
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

from odoo.addons.dmag_dental_base.models.dmag_access import check_director, is_director

from .dmag_esign_provider import parse_certificate

_logger = logging.getLogger(__name__)

try:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding, utils as asym_utils
except ImportError:  # pragma: no cover
    InvalidSignature = None

# Thư viện nhúng chữ ký vào PDF (PAdES) – phụ thuộc mềm
try:  # pragma: no cover - tùy môi trường
    import pyhanko  # noqa: F401
    PADES_LIB = 'pyhanko'
except ImportError:
    try:  # pragma: no cover
        import endesive  # noqa: F401
        PADES_LIB = 'endesive'
    except ImportError:
        PADES_LIB = None

ESIGN_STATES = [
    ('draft', 'Nháp'),
    ('sent', 'Đã gửi'),
    ('waiting', 'Chờ bác sĩ xác nhận trên MySign'),
    ('signed', 'Đã ký số'),
    ('rejected', 'Bị từ chối'),
    ('expired', 'Hết hạn'),
    ('error', 'Lỗi'),
]
PENDING_STATES = ('sent', 'waiting')
FAILED_STATES = ('rejected', 'expired', 'error')


class DmagEsignRequest(models.Model):
    """Yêu cầu ký số một tài liệu (bệnh án, đơn thuốc, phiếu đồng ý…) gắn với bản ghi bất kỳ."""
    _name = 'dmag.esign.request'
    _description = 'Yêu cầu ký số'
    _inherit = ['mail.thread']
    _order = 'id desc'

    name = fields.Char('Mã yêu cầu', required=True, readonly=True, copy=False, default='/')
    company_id = fields.Many2one('res.company', string='Phòng khám', required=True, readonly=True,
                                 default=lambda self: self.env.company, index=True)
    res_model = fields.Char('Mô hình tài liệu', required=True, readonly=True, index=True)
    res_id = fields.Many2oneReference('ID tài liệu', model_field='res_model', required=True, readonly=True, index=True)
    res_name = fields.Char('Tài liệu gốc', compute='_compute_res_name')
    document_name = fields.Char('Tên tài liệu', required=True, readonly=True)
    document_format = fields.Selection([('pdf', 'PDF'), ('html', 'HTML (chưa có wkhtmltopdf)')],
                                       string='Định dạng', readonly=True, default='pdf')
    document_hash = fields.Char('Mã băm SHA-256', readonly=True, copy=False)
    unsigned_attachment_id = fields.Many2one('ir.attachment', string='Tài liệu chưa ký', readonly=True, copy=False)
    signed_attachment_id = fields.Many2one('ir.attachment', string='PDF đã nhúng chữ ký (PAdES)', readonly=True,
                                           copy=False)
    signature_attachment_id = fields.Many2one('ir.attachment', string='Tệp chữ ký rời', readonly=True, copy=False,
                                              help='Chữ ký CMS (.p7s) hoặc gói chữ ký JSON kèm chứng thư.')
    signer_id = fields.Many2one('dmag.dental.practitioner', string='Bác sĩ ký', required=True, readonly=True)
    signer_user_id = fields.Many2one('res.users', string='Tài khoản ký', related='signer_id.user_id', store=True)
    provider_id = fields.Many2one('dmag.esign.provider', string='Nhà cung cấp', required=True, readonly=True)
    provider_type = fields.Selection(related='provider_id.provider_type', string='Loại nhà cung cấp')
    state = fields.Selection(ESIGN_STATES, string='Trạng thái', default='draft', required=True, readonly=True,
                             tracking=True, index=True, copy=False)
    transaction_id = fields.Char('Mã giao dịch nhà cung cấp', readonly=True, copy=False, index=True)
    credential_id = fields.Char('Credential ID', readonly=True, copy=False)
    certificate_subject = fields.Char('Chủ thể chứng thư', readonly=True, copy=False)
    certificate_serial = fields.Char('Số serial chứng thư', readonly=True, copy=False)
    certificate_valid_to = fields.Datetime('Chứng thư hiệu lực đến', readonly=True, copy=False)
    certificate_data = fields.Binary('Chứng thư (DER)', attachment=False, readonly=True, copy=False)
    signature_format = fields.Selection([
        ('cms', 'CMS / PKCS#7 rời'), ('pkcs1', 'PKCS#1 (ký hash)'), ('hmac', 'HMAC (giả lập)'),
    ], string='Dạng chữ ký', readonly=True, copy=False)
    sent_at = fields.Datetime('Gửi lúc', readonly=True, copy=False)
    expire_at = fields.Datetime('Hết hạn lúc', readonly=True, copy=False)
    signed_at = fields.Datetime('Ký lúc', readonly=True, copy=False)
    error_message = fields.Text('Thông báo lỗi', readonly=True, copy=False)
    log_ids = fields.One2many('dmag.esign.log', 'request_id', string='Nhật ký', readonly=True)

    @api.depends('res_model', 'res_id')
    def _compute_res_name(self):
        for req in self:
            record = req._get_target()
            req.res_name = record.display_name if record else False

    # ------------------------------------------------------------------ CRUD
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                vals['name'] = self.env['ir.sequence'].sudo().next_by_code('dmag.esign.request') or '/'
        return super().create(vals_list)

    def unlink(self):
        check_director(self.env, _('Chỉ Giám đốc / Quản lý cấp cao được xóa hồ sơ ký số.'))
        return super().unlink()

    # ------------------------------------------------------------------ helpers
    def _get_target(self):
        self.ensure_one()
        if not self.res_model or not self.res_id or self.res_model not in self.env:
            return None
        return self.env[self.res_model].browse(self.res_id).exists()

    def _get_document_content(self):
        self.ensure_one()
        att = self.unsigned_attachment_id.sudo()
        return base64.b64decode(att.datas) if att.datas else b''

    def _log(self, event, message=''):
        Log = self.env['dmag.esign.log'].sudo()
        for req in self:
            Log.create({'request_id': req.id, 'event': event, 'message': message})

    # ------------------------------------------------------------------ workflow
    def _dmag_send(self):
        for req in self.sudo():
            res = req.provider_id._esign_send(req)
            now = fields.Datetime.now()
            req.write({
                'state': 'sent', 'sent_at': now,
                'expire_at': now + timedelta(minutes=req.provider_id.request_ttl or 10),
            })
            req._log('sent', _('Gửi yêu cầu ký tới %s (bác sĩ %s).', req.provider_id.name, req.signer_id.name))
            req._dmag_apply_result(res)
        return True

    def _dmag_poll(self):
        for req in self.sudo().filtered(lambda r: r.state in PENDING_STATES):
            if req.expire_at and req.expire_at < fields.Datetime.now():
                req._dmag_apply_result({'state': 'expired', 'message': _('Bác sĩ chưa xác nhận trên MySign trong thời hạn.')})
                continue
            req._dmag_apply_result(req.provider_id._esign_poll(req))
        return True

    def _dmag_apply_result(self, res):
        self.ensure_one()
        vals = {}
        for key, field in (('transaction_id', 'transaction_id'), ('credential_id', 'credential_id'),
                           ('subject', 'certificate_subject'), ('serial', 'certificate_serial'),
                           ('valid_to', 'certificate_valid_to'), ('signature_format', 'signature_format')):
            if res.get(key):
                vals[field] = res[key]
        if res.get('certificate'):
            vals['certificate_data'] = base64.b64encode(res['certificate'])
        state = res.get('state') or 'error'
        if state == 'signed' and not res.get('signature'):
            state, res['message'] = 'error', _('Nhà cung cấp báo đã ký nhưng không trả chữ ký.')
        if state == 'waiting':
            vals['state'] = 'waiting'
            self.write(vals)
            self._log('waiting', _('Đang chờ bác sĩ xác nhận trên ứng dụng MySign (giao dịch %s).',
                                   vals.get('transaction_id') or self.transaction_id or ''))
            return
        if state == 'signed':
            self.write(vals)
            self._dmag_finalize(res)
            return
        vals.update(state=state, error_message=res.get('message') or res.get('raw_status') or '')
        self.write(vals)
        self._log(state, vals['error_message'])
        target = self._get_target()
        if target is not None and hasattr(target, '_dmag_on_esign_failed'):
            target._dmag_on_esign_failed(self)

    def _dmag_verify(self, signature, certificate):
        """Kiểm tra chữ ký PKCS#1 trên mã băm bằng khóa công khai của chứng thư (nếu đọc được)."""
        if self.signature_format != 'pkcs1' or not certificate or InvalidSignature is None:
            return None
        parsed = parse_certificate(certificate)
        if not parsed:
            return None
        try:
            parsed['object'].public_key().verify(
                signature, bytes.fromhex(self.document_hash), padding.PKCS1v15(),
                asym_utils.Prehashed(hashes.SHA256()))
        except InvalidSignature:
            return False
        except Exception:  # noqa: BLE001 – khóa EC / định dạng khác: không kết luận
            _logger.info('Không kiểm tra được chữ ký %s', self.name, exc_info=True)
            return None
        return True

    def _dmag_finalize(self, res):
        self.ensure_one()
        signature = res['signature']
        certificate = res.get('certificate') or (base64.b64decode(self.certificate_data) if self.certificate_data else None)
        verified = self._dmag_verify(signature, certificate)
        if verified is False:
            self.write({'state': 'error', 'error_message': _('Chữ ký trả về không khớp mã băm / chứng thư.')})
            self._log('error', self.error_message)
            return
        base = self.document_name
        if self.signature_format == 'cms':
            fname, mimetype, payload = '%s.p7s' % base, 'application/pkcs7-signature', signature
        else:
            fname, mimetype = '%s.sig.json' % base, 'application/json'
            payload = json.dumps({
                'document': self.unsigned_attachment_id.name,
                'sha256': self.document_hash,
                'hash_algo': self.provider_id.hash_algo,
                'sign_algo': self.provider_id.sign_algo,
                'signature_format': self.signature_format,
                'signature': base64.b64encode(signature).decode(),
                'certificate': base64.b64encode(certificate).decode() if certificate else None,
                'certificate_subject': self.certificate_subject,
                'certificate_serial': self.certificate_serial,
                'transaction_id': self.transaction_id,
                'signer': self.signer_id.name,
                'signed_at': fields.Datetime.to_string(fields.Datetime.now()),
            }, ensure_ascii=False, indent=2).encode()
        Attachment = self.env['ir.attachment'].sudo()
        sig_att = Attachment.create({
            'name': fname, 'raw': payload, 'mimetype': mimetype,
            'res_model': self.res_model, 'res_id': self.res_id,
            'description': _('Chữ ký số rời của %s (SHA-256 %s)', self.unsigned_attachment_id.name, self.document_hash),
        })
        vals = {'state': 'signed', 'signed_at': fields.Datetime.now(), 'signature_attachment_id': sig_att.id,
                'error_message': False}
        pades = self._dmag_embed_pades(signature, certificate)
        if pades:
            vals['signed_attachment_id'] = Attachment.create({
                'name': '%s (đã ký).pdf' % base, 'raw': pades, 'mimetype': 'application/pdf',
                'res_model': self.res_model, 'res_id': self.res_id,
            }).id
        self.write(vals)
        self._log('signed', _('Đã ký số. Chứng thư %s – serial %s%s.', self.certificate_subject or '',
                              self.certificate_serial or '',
                              _(' – đã kiểm tra chữ ký khớp chứng thư') if verified else ''))
        target = self._get_target()
        if target is not None and hasattr(target, '_dmag_on_esign_done'):
            target._dmag_on_esign_done(self)

    def _dmag_embed_pades(self, signature, certificate):
        """Nhúng chữ ký vào PDF (PAdES). Trả bytes PDF đã ký hoặc False.

        Ký PAdES từ xa cần luồng 2 pha: chuẩn bị PDF có vùng chữ ký → băm *signed attributes*
        → gửi MySign ký → nhúng CMS. Chỉ bật khi đã cài ``pyhanko``/``endesive`` và xác nhận
        định dạng chữ ký MySign trả về; hiện lưu chữ ký rời (.p7s / .sig.json) kèm mã băm.
        """
        if self.document_format != 'pdf' or not PADES_LIB:
            return False
        _logger.info('%s có sẵn nhưng luồng PAdES 2 pha chưa được bật – lưu chữ ký rời cho %s.', PADES_LIB, self.name)
        return False

    # ------------------------------------------------------------------ actions
    def _check_signer_or_director(self):
        for req in self:
            if not is_director(self.env) and req.signer_user_id != self.env.user:
                raise AccessError(_('Chỉ bác sĩ ký hoặc Giám đốc được thao tác yêu cầu ký %s.', req.name))

    def action_check_status(self):
        self.check_access_rights('read')
        self.check_access_rule('read')
        self._dmag_poll()
        return True

    def action_resend(self):
        self.check_access_rule('read')
        self._check_signer_or_director()
        for req in self.sudo():
            if req.state not in FAILED_STATES:
                raise UserError(_('Chỉ gửi lại yêu cầu bị từ chối / hết hạn / lỗi.'))
            req._log('resend', _('Gửi lại bởi %s.', self.env.user.name))
            req.write({'state': 'draft', 'error_message': False, 'transaction_id': False})
            req._dmag_send()
        return True

    def action_open_document(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': self.res_model, 'res_id': self.res_id,
                'view_mode': 'form', 'target': 'current'}

    @api.model
    def _cron_poll_pending(self):
        pending = self.sudo().search([('state', 'in', PENDING_STATES)], limit=200)
        for req in pending:
            try:
                with self.env.cr.savepoint():
                    req._dmag_poll()
            except Exception as exc:  # noqa: BLE001 – một yêu cầu lỗi không chặn các yêu cầu khác
                _logger.exception('Lỗi kiểm tra trạng thái ký %s', req.name)
                req.write({'state': 'error', 'error_message': str(exc)})


class DmagEsignLog(models.Model):
    _name = 'dmag.esign.log'
    _description = 'Nhật ký ký số'
    _order = 'id desc'

    request_id = fields.Many2one('dmag.esign.request', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='request_id.company_id', store=True)
    date = fields.Datetime('Thời điểm', default=fields.Datetime.now, required=True, readonly=True)
    user_id = fields.Many2one('res.users', string='Người thao tác', default=lambda self: self.env.user, readonly=True)
    event = fields.Char('Sự kiện', readonly=True)
    message = fields.Text('Nội dung', readonly=True)

    def write(self, vals):
        raise UserError(_('Nhật ký ký số không được sửa.'))

    def unlink(self):
        check_director(self.env, _('Chỉ Giám đốc được xóa nhật ký ký số.'))
        return super().unlink()
