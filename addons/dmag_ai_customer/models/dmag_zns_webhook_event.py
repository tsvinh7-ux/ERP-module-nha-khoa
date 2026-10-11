"""AI-07 – Nhận tin khách nhắn vào Zalo OA qua webhook sẵn có của dmag_zalo_zns (/dmag/zalo/webhook).

[CẦN XÁC MINH] Dạng payload sự kiện ``user_send_text`` của Zalo OA (đang đọc: ``event_name``, ``sender.id``,
``recipient.id``, ``message.text``, ``message.msg_id``, ``timestamp``; tên hiển thị có thể nằm ở ``sender.display_name``
hoặc phải gọi API ``/v3.0/oa/user/detail``).
"""
import logging

from odoo import models

_logger = logging.getLogger(__name__)

USER_MESSAGE_EVENTS = ('user_send_text', 'user_send_image', 'user_send_sticker', 'user_send_link', 'user_send_location',
                       'user_send_file', 'user_send_audio', 'user_send_video', 'user_send_gif')


class DmagZnsWebhookEvent(models.Model):
    _inherit = 'dmag.zns.webhook.event'

    def _dmag_process(self, data):
        name = (data or {}).get('event_name') or ''
        if name not in USER_MESSAGE_EVENTS:
            return super()._dmag_process(data)
        self.ensure_one()
        company = self.company_id or self.env.company
        if not company.dmag_ai_zalo_enabled:
            self.write({'processed': True, 'note': 'Trợ lý AI Zalo đang tắt.'})
            return True
        sender = data.get('sender') or {}
        user_id = str(sender.get('id') or data.get('user_id_by_app') or '')
        msg = data.get('message') or {}
        text = msg.get('text') if name == 'user_send_text' else '[%s]' % {
            'user_send_image': 'Khách gửi ảnh', 'user_send_sticker': 'Khách gửi sticker',
            'user_send_location': 'Khách gửi vị trí', 'user_send_file': 'Khách gửi tệp',
            'user_send_audio': 'Khách gửi ghi âm', 'user_send_video': 'Khách gửi video',
        }.get(name, 'Khách gửi nội dung')
        if not user_id or not text:
            self.write({'processed': True, 'note': 'Thiếu sender.id / message.text.'})
            return True
        Conv = self.env['dmag.ai.conversation'].sudo().with_company(company)
        conv = Conv._get_or_create('zalo', external_user_id=user_id,
                                   name=sender.get('display_name') or sender.get('name') or 'Khách Zalo %s' % user_id[-4:])
        try:
            with self.env.cr.savepoint():
                conv.receive_customer_message(text, auto_reply=name == 'user_send_text',
                                             defer=company.dmag_ai_mode == 'live')
            note = 'Đã chuyển trợ lý AI (hội thoại %s).' % conv.id
        except Exception as e:  # webhook phải trả 200 nhanh – lỗi ghi lại để xử lý tay
            _logger.exception('AI-07 webhook processing failed')
            note = 'Lỗi trợ lý AI: %s' % e
        self.write({'processed': True, 'note': note[:250]})
        return True
