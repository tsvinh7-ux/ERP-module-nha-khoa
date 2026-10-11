"""AI-03 – Chặn đơn thuốc vi phạm quy tắc an toàn trên MỌI đường phát hành + Giám đốc duyệt vượt có ký chịu trách nhiệm.

* ``dmag.prescription.action_issue`` (form đơn thuốc, Bàn làm việc bác sĩ ``issue_prescription``, đơn thay thế, mọi
  đường máy chủ) chạy quy tắc CỐ ĐỊNH ``rx_safety.check_lines`` – có mục CHẶN → không phát hành.
* Chỉ Giám đốc (``group_dmag_director``) duyệt vượt: bắt buộc lý do bằng văn bản + xác nhận "ký bổ sung chịu trách
  nhiệm"; ghi người / thời điểm / lý do / các quy tắc bị vượt lên đơn (trường chỉ đọc + chatter) và gửi yêu cầu ký số
  qua khung ký số chung nếu đã cài ``dmag_esign_mysign`` (phụ thuộc MỀM).
* Duyệt vượt gắn với ĐÚNG tập vi phạm lúc duyệt (mã quy tắc + thuốc): bác sĩ sửa đơn làm phát sinh vi phạm khác →
  bị chặn lại, cần duyệt lần nữa.
* Bác sĩ: "Đề nghị Giám đốc duyệt vượt" → việc cần làm (activity) cho Giám đốc.
"""
import hashlib
import html

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

from odoo.addons.dmag_dental_base.models.dmag_access import DIRECTOR_GROUP, check_director, is_director

from . import rx_safety

OVERRIDE_FIELDS = {'rx_safety_override', 'rx_override_uid', 'rx_override_date', 'rx_override_reason',
                   'rx_override_rules', 'rx_override_codes', 'rx_override_requested_uid', 'rx_override_requested_at',
                   'rx_override_esign'}
MIN_REASON = 15


class DmagPrescription(models.Model):
    _inherit = 'dmag.prescription'

    rx_safety_override = fields.Boolean('Giám đốc duyệt vượt an toàn', readonly=True, copy=False, tracking=True)
    rx_override_uid = fields.Many2one('res.users', string='Giám đốc duyệt vượt', readonly=True, copy=False)
    rx_override_date = fields.Datetime('Duyệt vượt lúc', readonly=True, copy=False)
    rx_override_reason = fields.Text('Lý do duyệt vượt', readonly=True, copy=False)
    rx_override_rules = fields.Text('Quy tắc bị vượt', readonly=True, copy=False)
    rx_override_codes = fields.Char('Dấu vân tay vi phạm đã duyệt', readonly=True, copy=False,
                                    help='Mã quy tắc + thuốc tại thời điểm duyệt; đơn sửa phát sinh vi phạm khác → chặn lại.')
    rx_override_requested_uid = fields.Many2one('res.users', string='Bác sĩ đề nghị duyệt vượt', readonly=True,
                                                copy=False)
    rx_override_requested_at = fields.Datetime('Đề nghị lúc', readonly=True, copy=False)
    rx_override_esign = fields.Char('Ký số bổ sung', readonly=True, copy=False,
                                    help='Yêu cầu ký số (Viettel MySign / giả lập) cho văn bản chịu trách nhiệm duyệt vượt.')
    rx_override_banner = fields.Char('Tóm tắt duyệt vượt', compute='_compute_rx_override_banner')
    rx_safety_blocks = fields.Text('Vi phạm an toàn hiện tại', compute='_compute_rx_safety_blocks')
    rx_safety_block_count = fields.Integer('Số mục CHẶN', compute='_compute_rx_safety_blocks')

    # ------------------------------------------------------------------ quy tắc
    def _rx_safety_lines(self):
        self.ensure_one()
        return [{'drug_id': line.drug_id.id, 'days': line.days if not line.is_chronic else 0,
                 'dose_per_time': line.dose_per_time, 'times_per_day': line.times_per_day}
                for line in self.line_ids if line.drug_id]

    def _rx_safety_findings(self):
        self.ensure_one()
        return rx_safety.check_lines(self.env, self.patient_id, self._rx_safety_lines(), max_days=30,
                                     weight=self.weight)

    def _rx_safety_blocks(self):
        return [f for f in self._rx_safety_findings() if f['level'] == 'block']

    @staticmethod
    def _rx_block_signature(blocks):
        keys = sorted({'%s:%s' % (f['code'], rx_safety.norm(f['drug'])) for f in blocks})
        return hashlib.sha1('|'.join(keys).encode()).hexdigest()[:16] if keys else ''

    @staticmethod
    def _rx_block_text(blocks):
        return '\n'.join('• %s – %s: %s' % (f['title'], f['drug'], f['message']) for f in blocks)

    @api.depends('line_ids.drug_id', 'line_ids.days', 'line_ids.is_chronic', 'patient_id', 'weight')
    def _compute_rx_safety_blocks(self):
        for rx in self:
            blocks = rx._rx_safety_blocks() if rx.patient_id and rx.line_ids else []
            rx.rx_safety_blocks = rx._rx_block_text(blocks) or False
            rx.rx_safety_block_count = len(blocks)

    @api.depends('rx_safety_override', 'rx_override_uid', 'rx_override_date', 'rx_override_reason')
    def _compute_rx_override_banner(self):
        for rx in self:
            if not rx.rx_safety_override:
                rx.rx_override_banner = False
                continue
            when = fields.Datetime.context_timestamp(rx, rx.rx_override_date) if rx.rx_override_date else None
            rx.rx_override_banner = _('Giám đốc %(user)s duyệt vượt an toàn lúc %(when)s – lý do: %(reason)s',
                                      user=rx.rx_override_uid.name or '',
                                      when=when.strftime('%d/%m/%Y %H:%M') if when else '',
                                      reason=rx.rx_override_reason or '')

    def _rx_override_valid(self, blocks=None):
        """Duyệt vượt còn hiệu lực cho đúng tập vi phạm hiện tại."""
        self.ensure_one()
        blocks = self._rx_safety_blocks() if blocks is None else blocks
        return bool(blocks and self.rx_safety_override and self.rx_override_codes == self._rx_block_signature(blocks))

    # ------------------------------------------------------------------ ghi / khóa trường duyệt vượt
    def write(self, vals):
        if OVERRIDE_FIELDS & set(vals) and not self.env.context.get('dmag_rx_override_write'):
            raise AccessError(_('Thông tin duyệt vượt an toàn đơn thuốc chỉ ghi qua nút "Duyệt vượt & ký chịu trách '
                                'nhiệm" của Giám đốc.'))
        return super().write(vals)

    def _rx_override_write(self, vals):
        return self.sudo().with_context(dmag_rx_override_write=True, dmag_workflow=True).write(vals)

    # ------------------------------------------------------------------ phát hành
    def action_issue(self):
        """Chặn phát hành trên MỌI đường khi có mục CHẶN chưa được Giám đốc duyệt vượt (đúng tập vi phạm)."""
        for rx in self:
            if rx.state != 'draft':
                continue
            blocks = rx._rx_safety_blocks()
            if not blocks:
                continue
            if rx._rx_override_valid(blocks):
                rx.message_post(body=_('Phát hành theo duyệt vượt an toàn của Giám đốc %(user)s (%(date)s).',
                                       user=rx.rx_override_uid.name,
                                       date=fields.Datetime.to_string(rx.rx_override_date)))
                continue
            hint = _('Bác sĩ sửa đơn, hoặc bấm "Đề nghị Giám đốc duyệt vượt".')
            if rx.rx_safety_override:
                hint = _('Đơn đã thay đổi sau khi Giám đốc duyệt vượt – cần duyệt lại. ') + hint
            raise UserError(_('Không phát hành được đơn thuốc – vi phạm quy tắc an toàn:\n%(rules)s\n%(hint)s',
                              rules='\n'.join('• %s: %s' % (f['title'], f['message']) for f in blocks), hint=hint))
        return super().action_issue()

    # ------------------------------------------------------------------ đề nghị / duyệt vượt
    def _director_users(self):
        group = self.env.ref(DIRECTOR_GROUP, raise_if_not_found=False)
        if not group:
            return self.env['res.users']
        root = self.env.ref('base.user_root')
        users = group.sudo().users.filtered(lambda u: not u.share and u != root and self.company_id in u.company_ids)
        # ưu tiên tài khoản Giám đốc thật (không phải quản trị hệ thống)
        named = users.filtered(lambda u: not u.has_group('base.group_system'))
        return named or users

    def action_request_override(self, note=''):
        """Bác sĩ đề nghị Giám đốc duyệt vượt: tạo việc cần làm cho Giám đốc + ghi chatter."""
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_('Chỉ đề nghị duyệt vượt cho đơn nháp.'))
        blocks = self._rx_safety_blocks()
        if not blocks:
            raise UserError(_('Đơn không có mục CHẶN nào – không cần duyệt vượt.'))
        self.check_access_rights('read')
        self.check_access_rule('read')
        rules = self._rx_block_text(blocks)
        directors = self._director_users()
        for user in directors:
            self.sudo().activity_schedule(
                'mail.mail_activity_data_todo', user_id=user.id,
                summary=_('Đề nghị duyệt vượt an toàn đơn thuốc – %s', self.patient_id.name),
                note=_('<p>BS %(doc)s đề nghị duyệt vượt.</p><p>%(note)s</p><pre>%(rules)s</pre>',
                       doc=html.escape(self.env.user.name), note=html.escape(note or ''), rules=html.escape(rules)))
        self._rx_override_write({'rx_override_requested_uid': self.env.uid,
                                 'rx_override_requested_at': fields.Datetime.now()})
        self.message_post(body=_('BS %(user)s đề nghị Giám đốc duyệt vượt quy tắc an toàn:\n%(rules)s%(note)s',
                                 user=self.env.user.name, rules=rules, note=('\n' + _('Ghi chú: %s', note)) if note else ''))
        return {'requested': len(directors), 'directors': directors.mapped('name')}

    def action_director_override(self, reason, confirm=True, issue=False):
        """Giám đốc duyệt vượt + ký bổ sung chịu trách nhiệm (lý do bắt buộc). ``issue`` = phát hành ngay."""
        self.ensure_one()
        check_director(self.env, _('Chỉ Giám đốc được duyệt vượt quy tắc an toàn đơn thuốc.'))
        if self.state != 'draft':
            raise UserError(_('Chỉ duyệt vượt cho đơn nháp.'))
        reason = (reason or '').strip()
        if len(reason) < MIN_REASON:
            raise UserError(_('Ghi rõ lý do duyệt vượt (tối thiểu %s ký tự) – lý do được lưu vào hồ sơ đơn thuốc.',
                              MIN_REASON))
        if not confirm:
            raise UserError(_('Cần xác nhận "ký bổ sung chịu trách nhiệm" trước khi duyệt vượt.'))
        blocks = self._rx_safety_blocks()
        if not blocks:
            raise UserError(_('Đơn không có mục CHẶN nào – không cần duyệt vượt.'))
        rules = self._rx_block_text(blocks)
        now = fields.Datetime.now()
        self._rx_override_write({
            'rx_safety_override': True, 'rx_override_uid': self.env.uid, 'rx_override_date': now,
            'rx_override_reason': reason, 'rx_override_rules': rules,
            'rx_override_codes': self._rx_block_signature(blocks),
        })
        self.message_post(body=_('GIÁM ĐỐC DUYỆT VƯỢT QUY TẮC AN TOÀN ĐƠN THUỐC – ký bổ sung chịu trách nhiệm.\n'
                                 'Người duyệt: %(user)s – lúc %(date)s.\nLý do: %(reason)s\nQuy tắc bị vượt:\n%(rules)s',
                                 user=self.env.user.name, date=fields.Datetime.to_string(now), reason=reason,
                                 rules=rules))
        self.activity_ids.filtered(lambda a: (a.summary or '').startswith(_('Đề nghị duyệt vượt'))).sudo() \
            .action_feedback(feedback=_('Giám đốc %(user)s đã duyệt vượt: %(reason)s', user=self.env.user.name,
                                        reason=reason))
        esign = self._rx_override_esign(reason, rules, now)
        result = {'overridden': True, 'esign': esign, 'issued': False}
        if issue:
            self.action_issue()
            result.update(issued=True, code=self.name, state=self.state)
        return result

    def _rx_override_esign(self, reason, rules, when):
        """Gửi văn bản "ký bổ sung chịu trách nhiệm" tới khung ký số (dmag_esign_mysign) nếu đã cài – phụ thuộc mềm."""
        self.ensure_one()
        if 'dmag.esign.request' not in self.env or 'dmag.esign.provider' not in self.env:
            self._rx_override_write({'rx_override_esign': _('Chưa cài ký số – ghi nhận xác nhận trong hệ thống')})
            return {'state': 'none', 'label': _('Chưa cài module ký số – đã ghi nhận xác nhận trong hệ thống.')}
        provider = self.env['dmag.esign.provider'].sudo()._dmag_get_provider(self.company_id)
        signer = self.env['dmag.dental.practitioner'].sudo().with_context(active_test=False).search([
            ('user_id', '=', self.env.uid), ('company_id', '=', self.company_id.id)], limit=1)
        if not provider or not signer:
            why = _('phòng khám chưa cấu hình nhà cung cấp ký số') if not provider else \
                _('Giám đốc chưa có hồ sơ ký số (hồ sơ nhân sự lâm sàng gắn tài khoản)')
            self._rx_override_write({'rx_override_esign': _('Chưa ký số: %s', why)})
            self.message_post(body=_('Chưa gửi được ký số cho văn bản duyệt vượt: %s. Xác nhận đã ghi nhận trong '
                                     'hệ thống.', why))
            return {'state': 'none', 'label': _('Chưa ký số: %s', why)}
        content = self._rx_override_document(reason, rules, when).encode()
        digest = hashlib.sha256(content).hexdigest()
        name = _('Duyet vuot an toan don thuoc %s', self.id)
        attachment = self.env['ir.attachment'].sudo().create({
            'name': '%s.html' % name, 'raw': content, 'mimetype': 'text/html',
            'res_model': self._name, 'res_id': self.id,
            'description': _('Văn bản ký bổ sung chịu trách nhiệm – SHA-256 %s', digest),
        })
        Request = self.env['dmag.esign.request'].sudo()
        req = Request.create({
            'company_id': self.company_id.id, 'res_model': self._name, 'res_id': self.id,
            'document_name': name, 'document_format': 'html', 'document_hash': digest,
            'unsigned_attachment_id': attachment.id, 'signer_id': signer.id, 'provider_id': provider.id,
        })
        req._log('created', _('Ký bổ sung chịu trách nhiệm duyệt vượt an toàn đơn thuốc (Giám đốc %s).',
                              self.env.user.name))
        try:
            req._dmag_send()
        except Exception as exc:  # noqa: BLE001 – lỗi ký số không làm mất bản ghi duyệt vượt
            req.write({'state': 'error', 'error_message': str(exc)[:500]})
        label = '%s – %s' % (req.name, dict(req._fields['state'].selection).get(req.state))
        self._rx_override_write({'rx_override_esign': label})
        self.message_post(body=_('Yêu cầu ký số văn bản duyệt vượt: %(label)s (nhà cung cấp %(provider)s, SHA-256 %(hash)s).',
                                 label=label, provider=provider.name, hash=digest))
        return {'state': req.state, 'label': label, 'request_id': req.id}

    def _rx_override_document(self, reason, rules, when):
        self.ensure_one()
        lines = ''.join('<li>%s – %s %s</li>' % (html.escape(l.drug_id.name or ''), l.days, html.escape(_('ngày')))
                        for l in self.line_ids)
        return ('<!doctype html><html><head><meta charset="utf-8"><title>%(title)s</title></head><body>'
                '<h2>%(title)s</h2><p>%(clinic)s</p>'
                '<p>Đơn thuốc nháp #%(id)s – bệnh nhân %(patient)s – bác sĩ kê đơn %(doctor)s</p>'
                '<ul>%(lines)s</ul><h3>Quy tắc an toàn bị vượt</h3><pre>%(rules)s</pre>'
                '<h3>Lý do</h3><p>%(reason)s</p>'
                '<p>Tôi, %(director)s, Giám đốc, duyệt vượt và ký bổ sung chịu trách nhiệm về quyết định này lúc '
                '%(when)s (UTC).</p></body></html>') % {
            'title': html.escape(_('Văn bản duyệt vượt quy tắc an toàn đơn thuốc')),
            'clinic': html.escape(self.company_id.name or ''), 'id': self.id,
            'patient': html.escape(self.patient_id.name or ''), 'doctor': html.escape(self.doctor_id.name or ''),
            'lines': lines, 'rules': html.escape(rules), 'reason': html.escape(reason),
            'director': html.escape(self.env.user.name), 'when': fields.Datetime.to_string(when)}

    def get_rx_override_info(self):
        self.ensure_one()
        blocks = self._rx_safety_blocks() if self.state == 'draft' else []
        return {
            'id': self.id, 'blocks': blocks, 'can_override': is_director(self.env),
            'override': self._rx_override_dict(),
            'valid': self._rx_override_valid(blocks) if blocks else False,
            'requested': bool(self.rx_override_requested_at),
            'requested_by': self.rx_override_requested_uid.name or '',
        }

    def _rx_override_dict(self):
        self.ensure_one()
        if not self.rx_safety_override:
            return False
        return {'user': self.rx_override_uid.name, 'date': fields.Datetime.to_string(self.rx_override_date),
                'reason': self.rx_override_reason or '', 'rules': self.rx_override_rules or '',
                'esign': self.rx_override_esign or ''}

    def _workspace_dict(self):
        res = super()._workspace_dict()
        res['rx_override'] = self._rx_override_dict()
        res['rx_override_requested'] = bool(self.rx_override_requested_at)
        return res

    def action_open_override_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': _('Duyệt vượt & ký chịu trách nhiệm'),
            'res_model': 'dmag.rx.override.wizard', 'view_mode': 'form', 'target': 'new',
            'context': {'default_prescription_id': self.id},
        }

    def action_request_override_button(self):
        self.action_request_override()
        return True


class DmagRxOverrideWizard(models.TransientModel):
    """Hộp thoại (form đơn thuốc) cho Giám đốc: quy tắc bị vượt + lý do + xác nhận ký chịu trách nhiệm."""
    _name = 'dmag.rx.override.wizard'
    _description = 'Duyệt vượt an toàn đơn thuốc'

    prescription_id = fields.Many2one('dmag.prescription', required=True, readonly=True)
    rules = fields.Text('Quy tắc bị vượt', compute='_compute_rules')
    reason = fields.Text('Lý do duyệt vượt', required=True)
    confirm = fields.Boolean('Tôi ký bổ sung và chịu trách nhiệm về quyết định này')
    issue_now = fields.Boolean('Phát hành đơn ngay sau khi duyệt', default=True)

    @api.depends('prescription_id')
    def _compute_rules(self):
        for wiz in self:
            rx = wiz.prescription_id
            wiz.rules = rx._rx_block_text(rx._rx_safety_blocks()) if rx else ''

    def action_confirm(self):
        self.ensure_one()
        self.prescription_id.action_director_override(self.reason, confirm=self.confirm, issue=self.issue_now)
        return {'type': 'ir.actions.act_window_close'}
