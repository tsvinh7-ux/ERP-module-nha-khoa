import base64
import hashlib
import logging
import re

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

from odoo.addons.dmag_dental_base.models.dmag_access import is_director

from .dmag_esign_request import ESIGN_STATES, FAILED_STATES, PENDING_STATES

_logger = logging.getLogger(__name__)


class DmagEsignMixin(models.AbstractModel):
    """Mixin ký số: kế thừa để có ``action_request_esign()`` và móc ``_dmag_on_esign_done()``.

    Ví dụ trong module khác::

        class Prescription(models.Model):
            _name = 'dmag.prescription'
            _inherit = ['mail.thread', 'dmag.esign.mixin']

            def action_sign(self):
                self.action_request_esign('dmag_dental_prescription.action_report_prescription',
                                          signer=self.doctor_id)

            def _dmag_on_esign_done(self, request):
                res = super()._dmag_on_esign_done(request)
                ...  # khóa đơn, gửi liên thông
                return res
    """
    _name = 'dmag.esign.mixin'
    _description = 'Mixin ký số'

    esign_request_id = fields.Many2one('dmag.esign.request', string='Yêu cầu ký số', readonly=True, copy=False)
    esign_state = fields.Selection([('none', 'Chưa ký số')] + ESIGN_STATES, string='Ký số',
                                   compute='_compute_esign_state', store=True, copy=False)
    esign_request_count = fields.Integer('Số lần ký số', compute='_compute_esign_request_count')

    @api.depends('esign_request_id.state')
    def _compute_esign_state(self):
        for record in self:
            record.esign_state = record.esign_request_id.state or 'none'

    def _compute_esign_request_count(self):
        Request = self.env['dmag.esign.request'].sudo()
        for record in self:
            record.esign_request_count = Request.search_count(
                [('res_model', '=', self._name), ('res_id', '=', record.id)]) if record.id else 0

    # ------------------------------------------------------------------ hooks to override
    def _dmag_esign_signer(self):
        """Bác sĩ ký mặc định: hồ sơ lâm sàng của người đang thao tác."""
        return self.env['dmag.dental.practitioner'].search([
            ('user_id', '=', self.env.uid), ('company_id', 'in', self.env.companies.ids)], limit=1)

    def _dmag_esign_report_ref(self):
        """Báo cáo QWeb mặc định dùng để dựng tài liệu ký (xmlid ``ir.actions.report``)."""
        return None

    def _dmag_esign_document_name(self):
        self.ensure_one()
        return re.sub(r'[\\/:*?"<>|]+', '-', self.display_name or '%s-%s' % (self._name, self.id))

    def _dmag_esign_render(self, report_ref):
        """Dựng tài liệu cần ký → (bytes, 'pdf' | 'html').

        Không có wkhtmltopdf (hoặc đang chạy kiểm thử) thì Odoo trả HTML: vẫn băm và ký bản HTML.
        """
        self.ensure_one()
        Report = self.env['ir.actions.report']
        if not report_ref:
            raise UserError(_('Chưa xác định mẫu in để ký số cho %s.', self.display_name))
        content, fmt = None, None
        if Report.get_wkhtmltopdf_state() in ('ok', 'upgrade', 'workers'):
            try:
                content, fmt = Report._render_qweb_pdf(report_ref, res_ids=self.ids)
            except (UserError, OSError) as exc:
                _logger.warning('Không dựng được PDF %s: %s – dùng HTML.', report_ref, exc)
        if content is None:
            content, fmt = Report._render_qweb_html(report_ref, self.ids)
        if isinstance(content, str):
            content = content.encode()
        fmt = 'pdf' if content[:4] == b'%PDF' else 'html'
        return content, fmt

    def _dmag_on_esign_done(self, request):
        """Gọi khi ký số xong: lưu trạng thái, đính tài liệu + chữ ký lên chatter."""
        self.ensure_one()
        self._dmag_esign_write({'esign_request_id': request.id})
        if hasattr(self, 'message_post'):
            attachments = (request.unsigned_attachment_id | request.signature_attachment_id
                           | request.signed_attachment_id)
            self.sudo().message_post(
                body=_('Đã ký số %(doc)s bởi %(signer)s qua %(provider)s. SHA-256: %(hash)s. Chứng thư: %(cert)s (serial %(serial)s).',
                       doc=request.document_name, signer=request.signer_id.name, provider=request.provider_id.name,
                       hash=request.document_hash, cert=request.certificate_subject or '-',
                       serial=request.certificate_serial or '-'),
                attachment_ids=attachments.ids,
                author_id=request.signer_user_id.partner_id.id or None,
            )
        return True

    def _dmag_on_esign_failed(self, request):
        self.ensure_one()
        if hasattr(self, 'message_post'):
            self.sudo().message_post(body=_('Ký số %(doc)s không thành công (%(state)s): %(msg)s',
                                            doc=request.document_name,
                                            state=dict(ESIGN_STATES).get(request.state),
                                            msg=request.error_message or ''))
        return True

    def _dmag_esign_write(self, vals):
        return self.sudo().with_context(dmag_workflow=True).write(vals)

    def _dmag_esign_check_signer(self, signer):
        if not signer:
            raise UserError(_('Không xác định được bác sĩ ký (tài khoản chưa gắn hồ sơ bác sĩ).'))
        if signer.role != 'doctor':
            raise UserError(_('%s không phải bác sĩ – không ký số được.', signer.name))
        if signer.user_id != self.env.user and not is_director(self.env):
            raise AccessError(_('Chỉ chính bác sĩ %s mới gửi được yêu cầu ký số của mình.', signer.name))
        if signer.mysign_cert_valid_to and signer.mysign_cert_valid_to < fields.Datetime.now():
            raise UserError(_('Chứng thư số của bác sĩ %(name)s đã hết hạn ngày %(date)s – liên hệ Viettel-CA gia hạn '
                              'trước khi ký.', name=signer.name, date=signer.mysign_cert_valid_to))

    # ------------------------------------------------------------------ public API
    def action_request_esign(self, report_ref=None, signer=None, document_name=None, provider=None):
        """Dựng tài liệu từ ``report_ref``, băm SHA-256 và gửi yêu cầu ký số cho ``signer``.

        :param report_ref: xmlid / bản ghi ``ir.actions.report`` (mặc định ``_dmag_esign_report_ref()``)
        :param signer: ``dmag.dental.practitioner`` (mặc định người đang thao tác)
        :param document_name: tên tệp (không đuôi)
        :param provider: ``dmag.esign.provider`` (mặc định nhà cung cấp đầu tiên của phòng khám)
        :return: các ``dmag.esign.request`` đã tạo
        """
        Request = self.env['dmag.esign.request']
        requests = Request
        self.check_access_rights('read')
        self.check_access_rule('read')
        for record in self:
            rec_signer = signer or record._dmag_esign_signer()
            record._dmag_esign_check_signer(rec_signer)
            company = record['company_id'] if 'company_id' in record._fields and record['company_id'] else self.env.company
            rec_provider = provider or self.env['dmag.esign.provider']._dmag_get_provider(company)
            if not rec_provider:
                raise UserError(_('Phòng khám %s chưa cấu hình nhà cung cấp ký số (Cấu hình → Ký số).', company.name))
            ref = report_ref or record._dmag_esign_report_ref()
            content, fmt = record._dmag_esign_render(ref)
            digest = hashlib.sha256(content).hexdigest()
            name = document_name or record._dmag_esign_document_name()
            attachment = self.env['ir.attachment'].sudo().create({
                'name': '%s.%s' % (name, fmt),
                'raw': content,
                'mimetype': 'application/pdf' if fmt == 'pdf' else 'text/html',
                'res_model': record._name, 'res_id': record.id,
                'description': _('Bản gửi ký số – SHA-256 %s', digest),
            })
            req = Request.sudo().create({
                'company_id': company.id,
                'res_model': record._name, 'res_id': record.id,
                'document_name': name, 'document_format': fmt, 'document_hash': digest,
                'unsigned_attachment_id': attachment.id,
                'signer_id': rec_signer.id, 'provider_id': rec_provider.id,
            })
            req._log('created', _('Tạo yêu cầu ký %s (%s), SHA-256 %s.', name, fmt.upper(), digest))
            record._dmag_esign_write({'esign_request_id': req.id})
            req._dmag_send()
            requests |= req
        return requests.with_env(self.env)

    def action_esign_check_status(self):
        """Nút "Kiểm tra trạng thái ký"."""
        requests = self.sudo().mapped('esign_request_id').filtered(lambda r: r.state in PENDING_STATES)
        if not requests:
            raise UserError(_('Không có yêu cầu ký số nào đang chờ.'))
        self.check_access_rule('read')
        requests._dmag_poll()
        return True

    def action_esign_resend(self):
        requests = self.mapped('esign_request_id').filtered(lambda r: r.state in FAILED_STATES)
        if not requests:
            raise UserError(_('Không có yêu cầu ký số lỗi / hết hạn để gửi lại.'))
        requests.action_resend()
        return True

    def action_view_esign_requests(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('dmag_esign_mysign.action_dmag_esign_request')
        action['domain'] = [('res_model', '=', self._name), ('res_id', '=', self.id)]
        action['context'] = {}
        return action
