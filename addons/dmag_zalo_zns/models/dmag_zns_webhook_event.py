import hashlib
import hmac
import json
import logging
from datetime import datetime

from odoo import _, api, fields, models

from odoo.addons.dmag_dental_base.models.dmag_access import check_director

_logger = logging.getLogger(__name__)


class DmagZnsWebhookEvent(models.Model):
    """Sự kiện Zalo gửi về webhook (lưu nguyên văn để đối soát)."""
    _name = 'dmag.zns.webhook.event'
    _description = 'Sự kiện webhook Zalo'
    _order = 'id desc'
    _rec_name = 'event_name'

    company_id = fields.Many2one('res.company', string='Phòng khám', index=True, readonly=True)
    event_name = fields.Char('Sự kiện', readonly=True, index=True)
    app_id = fields.Char('App ID', readonly=True)
    timestamp = fields.Char('Timestamp Zalo', readonly=True)
    signature = fields.Char('Chữ ký', readonly=True)
    verified = fields.Selection([
        ('ok', 'Hợp lệ'),
        ('invalid', 'Sai chữ ký'),
        ('not_checked', 'Không kiểm tra'),
    ], string='Xác thực', readonly=True, default='not_checked')
    raw = fields.Text('Nội dung gốc', readonly=True)
    message_id = fields.Many2one('dmag.zns.message', string='Tin ZNS', readonly=True, index=True)
    processed = fields.Boolean('Đã xử lý', readonly=True)
    note = fields.Char('Ghi chú', readonly=True)

    def write(self, vals):
        if not self.env.su:
            check_director(self.env, _('Nhật ký webhook chỉ đọc.'))
        return super().write(vals)

    def unlink(self):
        check_director(self.env, _('Chỉ Giám đốc / Quản lý cấp cao được xóa nhật ký webhook.'))
        return super().unlink()

    @api.model
    def _dmag_compute_signature(self, app_id, raw_body, timestamp, secret):
        """Chữ ký webhook Zalo OA: sha256(appId + data + timeStamp + OAsecretKey) – header
        ``X-ZEvent-Signature: mac=<hex>`` (cần xác nhận với tài liệu Zalo hiện hành)."""
        base = '%s%s%s%s' % (app_id or '', raw_body or '', timestamp or '', secret or '')
        return hashlib.sha256(base.encode('utf-8')).hexdigest()

    @api.model
    def _dmag_receive(self, raw_body, signature=None, company_key=None):
        """Lưu và xử lý một sự kiện webhook. Trả về (event, accepted)."""
        Company = self.env['res.company'].sudo()
        try:
            data = json.loads(raw_body or '{}')
        except ValueError:
            data = {}
        app_id = str(data.get('app_id') or '')
        oa_id = str((data.get('sender') or {}).get('id') or data.get('oa_id') or '')
        company = Company.browse()
        if company_key:
            company = Company.search([('dmag_zalo_webhook_key', '=', company_key)], limit=1)
        if not company and app_id:
            company = Company.search([('dmag_zalo_app_id', '=', app_id)], limit=1)
        if not company and oa_id:
            company = Company.search([('dmag_zalo_oa_id', '=', oa_id)], limit=1)
        timestamp = str(data.get('timestamp') or '')
        verified = 'not_checked'
        if company and company.dmag_zalo_webhook_secret:
            expected = self._dmag_compute_signature(app_id, raw_body, timestamp, company.dmag_zalo_webhook_secret)
            received = (signature or '').replace('mac=', '').strip()
            verified = 'ok' if hmac.compare_digest(expected, received) else 'invalid'
        event = self.sudo().create({
            'company_id': company.id,
            'event_name': data.get('event_name') or '',
            'app_id': app_id,
            'timestamp': timestamp,
            'signature': signature,
            'verified': verified,
            'raw': raw_body,
        })
        if verified == 'invalid':
            event.note = _('Sai chữ ký – không xử lý.')
            return event, False
        event._dmag_process(data)
        return event, True

    def _dmag_process(self, data):
        self.ensure_one()
        name = data.get('event_name') or ''
        msg = data.get('message') or {}
        Message = self.env['dmag.zns.message']
        message = Message._dmag_find_from_webhook(msg.get('msg_id'), msg.get('tracking_id') or data.get('tracking_id'))
        vals = {'processed': True}
        if message:
            vals['message_id'] = message.id
            if name == 'user_received_message':
                delivered = msg.get('delivery_time')
                when = fields.Datetime.now()
                try:
                    if delivered:
                        when = datetime.utcfromtimestamp(int(delivered) / 1000.0).replace(microsecond=0)
                except (TypeError, ValueError):
                    pass
                message.sudo().write({'state': 'delivered', 'delivered_date': when})
            elif name == 'user_feedback':
                feedback = msg.get('feedbacks') or msg.get('note') or msg.get('rate') or data.get('message')
                message.sudo().write({'feedback': json.dumps(feedback, ensure_ascii=False)
                                      if not isinstance(feedback, str) else feedback})
                self._dmag_on_feedback(message, data)
        else:
            vals['note'] = _('Không khớp tin ZNS nào.')
        self.write(vals)
        return True

    def _dmag_on_feedback(self, message, data):
        """Điểm móc cho module khác (CSKH) xử lý đánh giá của khách."""
        return True
