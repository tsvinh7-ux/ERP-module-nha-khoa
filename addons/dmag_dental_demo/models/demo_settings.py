import json
from html import escape

from odoo import _, api, fields, models

from ..generator import data as D
from ..generator.generator import PARAM_INFO

COUNT_LABELS = [
    ('res.partner', 'Đối tác (bệnh nhân, labo, người dùng)'),
    ('dmag.dental.visit', 'Lượt khám'),
    ('dmag.dental.procedure', 'Thủ thuật'),
    ('dmag.treatment.plan', 'Kế hoạch điều trị'),
    ('account.move', 'Hóa đơn / bút toán'),
    ('account.payment', 'Thanh toán'),
    ('dmag.prescription', 'Đơn thuốc'),
    ('dmag.lab.order', 'Phiếu labo'),
    ('dmag.warranty.card', 'Thẻ bảo hành'),
    ('dmag.material.usage', 'Ghi nhận vật tư'),
    ('dmag.zns.message', 'Tin ZNS (giả lập)'),
    ('dmag.nps.response', 'Khảo sát NPS'),
    ('dmag.commission.line', 'Dòng hoa hồng'),
    ('dmag.loyalty.ledger', 'Bút toán điểm thành viên'),
]
ROLE_LABELS = {
    'receptionist': 'Lễ tân / thu ngân',
    'consultant': 'Tư vấn viên',
    'assistant': 'Phụ tá / điều dưỡng',
    'doctor': 'Bác sĩ (bậc 3 – implant, phẫu thuật)',
    'doctor2': 'Bác sĩ (bậc 2 – chỉnh nha, trẻ em)',
    'manager': 'Quản lý phòng khám',
    'director': 'Giám đốc / Quản lý cấp cao',
}


class DmagDemoSettings(models.TransientModel):
    _name = 'dmag.demo.settings'
    _description = 'Dữ liệu demo DMAG'

    demo_active = fields.Boolean('Đang ở chế độ demo', compute='_compute_summary')
    summary_html = fields.Html('Tóm tắt', compute='_compute_summary', sanitize=False)
    logins_html = fields.Html('Tài khoản demo', compute='_compute_summary', sanitize=False)

    @api.depends_context('uid')
    def _compute_summary(self):
        Demo = self.env['dmag.demo']
        active = Demo.is_demo_mode()
        try:
            info = json.loads(self.env['ir.config_parameter'].sudo().get_param(PARAM_INFO) or '{}')
        except ValueError:
            info = {}
        counts = Demo.get_demo_counts()
        rows = ''.join(
            '<tr><td>%s</td><td class="text-end">%s</td></tr>' % (escape(label), counts.get(model, 0))
            for model, label in COUNT_LABELS)
        warnings = ''.join('<li>%s</li>' % escape(w) for w in info.get('warnings', [])[:10])
        summary = (
            '<p><b>%s</b></p>' % escape(_('Cơ sở dữ liệu đang ở CHẾ ĐỘ DEMO: Zalo ZNS, đơn thuốc quốc gia, '
                                         'ký số MySign chạy giả lập; SePay cho phép giả lập chuyển khoản.'))
            if active else '<p>%s</p>' % escape(_('Chưa có dữ liệu demo (hoặc đã xóa).'))
        )
        if info.get('generated_at'):
            summary += '<p>%s %s (UTC) – %s s</p>' % (escape(_('Sinh lúc')), escape(info['generated_at']),
                                                     info.get('seconds', ''))
        summary += '<table class="table table-sm o_dmag_demo_counts"><tbody>%s</tbody></table>' % rows
        if warnings:
            summary += '<p>%s</p><ul>%s</ul>' % (escape(_('Phần dữ liệu tùy chọn bị bỏ qua:')), warnings)
        logins = ''.join(
            '<tr><td><code>%s</code></td><td><code>%s</code></td><td>%s</td></tr>'
            % (escape(login), escape(D.PASSWORD), escape(ROLE_LABELS.get(key, key)))
            for key, login, *_rest in D.USERS)
        logins += '<tr><td><code>%s</code></td><td><code>%s</code></td><td>%s</td></tr>' % (
            escape(D.PORTAL_LOGIN), escape(D.PASSWORD), escape(_('Bệnh nhân – cổng /my/dental')))
        logins_html = ('<table class="table table-sm"><thead><tr><th>Đăng nhập</th><th>Mật khẩu</th>'
                       '<th>Vai trò</th></tr></thead><tbody>%s</tbody></table>' % logins)
        for wizard in self:
            wizard.demo_active = active
            wizard.summary_html = summary
            wizard.logins_html = logins_html

    def action_regenerate(self):
        return self.env['dmag.demo'].action_regenerate()

    def action_purge(self):
        return self.env['dmag.demo'].action_purge()
