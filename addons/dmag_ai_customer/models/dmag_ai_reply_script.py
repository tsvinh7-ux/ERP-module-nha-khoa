"""AI-07 – "Kịch bản trả lời đã duyệt": trợ lý Zalo chỉ TỰ GỬI khi tin của khách khớp một kịch bản Giám đốc đã duyệt.

* Kịch bản = ý định / chủ đề + câu hỏi mẫu của khách + mẫu trả lời có ô dữ liệu ({gia_dich_vu}, {gio_trong}, {dia_chi}…)
  điền từ dữ liệu THẬT của Odoo + công cụ được phép dùng.
* Quyền ("tạo được – không sửa"): Quản lý trở lên tạo / sửa bản nháp; nhân viên đề xuất (từ hộp thư) thành bản nháp;
  CHỈ Giám đốc duyệt; kịch bản đã duyệt bị khóa – muốn sửa, Giám đốc "Mở lại để sửa" (ghi vết) rồi duyệt lại.
* "Huấn luyện": câu trả lời nhân viên đã duyệt / đã sửa trong hộp thư → một chạm thành kịch bản nháp hoặc ví dụ hỏi –
  đáp (few-shot) gắn vào kịch bản; Giám đốc duyệt ví dụ trước khi trợ lý dùng.
"""
import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from odoo.addons.dmag_dental_base.models.dmag_access import check_director, is_director, is_workflow

from .text_utils import fold, has_any

SCRIPT_CATEGORIES = [
    ('info', 'Thông tin phòng khám'),
    ('price', 'Giá dịch vụ'),
    ('booking', 'Đặt / đổi lịch'),
    ('policy', 'Chính sách (bảo hành, trả góp…)'),
    ('consult', 'Tư vấn chung'),
    ('safety', 'An toàn – chuyển nhân viên'),
]
SCRIPT_FLOWS = [
    ('template', 'Trả lời theo mẫu đã duyệt'),
    ('booking', 'Đặt / đổi lịch qua công cụ (lịch NHÁP chờ lễ tân xác nhận)'),
    ('handoff', 'Gửi mẫu an toàn rồi chuyển nhân viên'),
]
HANDOFF_REASONS = [
    ('medical_question', 'Câu hỏi chuyên môn'), ('human_request', 'Khách muốn gặp nhân viên'), ('other', 'Khác'),
]
# Ô dữ liệu được phép trong mẫu trả lời → công cụ cần có
PLACEHOLDERS = {
    'ten_phong_kham': ('Tên phòng khám', None),
    'hotline': ('Hotline', None),
    'ten_khach': ('Cách gọi khách (anh/chị hoặc tên)', None),
    'dia_chi': ('Địa chỉ phòng khám', 'get_clinic_info'),
    'gui_xe': ('Thông tin gửi xe', 'get_clinic_info'),
    'gio_lam_viec': ('Giờ làm việc theo Lịch làm việc phòng khám', 'get_clinic_info'),
    'ngay_nghi_sap_toi': ('Ngày nghỉ lễ / nghỉ đột xuất trong 30 ngày tới', 'get_clinic_info'),
    'thanh_toan': ('Hình thức thanh toán', 'get_clinic_info'),
    'chuan_bi': ('Chuẩn bị trước khi khám', 'get_clinic_info'),
    'gia_dich_vu': ('Giá niêm yết (dịch vụ khách hỏi, hoặc dịch vụ gắn với kịch bản)', 'search_services'),
    'gio_trong': ('Giờ còn trống gần nhất (2 ngày làm việc tới)', 'get_free_slots'),
    'bao_hanh': ('Thời hạn bảo hành theo dịch vụ (dịch vụ khách hỏi, hoặc dịch vụ gắn với kịch bản)', 'search_services'),
    'bac_si_lam_viec': ('Bác sĩ và ngày trực (Lịch nghỉ luân phiên)', 'get_clinic_info'),
    'goi_cham_soc': ('Gói chăm sóc răng miệng theo năm', 'get_clinic_info'),
}
# Nhãn nguồn dữ liệu hiển thị "Trả lời từ: …" theo ô dữ liệu đã dùng
PLACEHOLDER_SOURCES = {
    'gia_dich_vu': 'Bảng giá', 'bao_hanh': 'Bảo hành theo dịch vụ', 'gio_lam_viec': 'Lịch làm việc',
    'ngay_nghi_sap_toi': 'Lịch làm việc', 'bac_si_lam_viec': 'Lịch nghỉ luân phiên', 'gio_trong': 'Giờ trống',
    'dia_chi': 'Thông tin phòng khám', 'gui_xe': 'Thông tin phòng khám', 'thanh_toan': 'Thanh toán',
    'chuan_bi': 'Thông tin phòng khám', 'goi_cham_soc': 'Gói chăm sóc',
}
PLACEHOLDER_RE = re.compile(r'\{([a-z_]+)\}')
# Trường nội dung – khóa khi kịch bản đã duyệt
CONTENT_FIELDS = {'name', 'code', 'category', 'sample_questions', 'keywords', 'answer_template', 'allow_rephrase',
                  'flow', 'service_ids', 'tool_ids', 'quick_replies', 'handoff_reason', 'company_id', 'min_confidence',
                  'doctor_scope'}
STOPWORDS = {'a', 'ah', 'ad', 'oi', 'cho', 'em', 'minh', 'toi', 'anh', 'chi', 'la', 'thi', 'co', 'khong', 'vay', 'nhe',
             'nha', 'voi', 'duoc', 'cua', 'ben', 'phong', 'kham', 'nha khoa', 'ko', 'k', 'gi', 'nao', 'the', 'ra', 'sao',
             'can', 'hoi', 'xin', 'chao', 'va', 'o', 'u', 'luon', 'rang', 'bac', 'si', 'mot', 'nhu', 'nay', 'kia',
             'roi', 'lam', 'muon', 'oi', 'giup', 'dang', 'ha', 'hay', 'neu', 'thoi', 'cung', 'nua'}


def content_tokens(text):
    return [w for w in re.findall(r'[a-z0-9]+', fold(text)) if w not in STOPWORDS and len(w) > 1]


def similarity(text, sample):
    """Độ giống (0..1) giữa câu khách và câu hỏi mẫu: tỷ lệ từ / cặp từ của câu mẫu xuất hiện trong câu khách,
    cân bằng với độ dài câu khách (hàm thuần, xác định)."""
    a, b = content_tokens(text), content_tokens(sample)
    if not a or not b:
        return 0.0
    sa, sb = set(a), set(b)
    uni = len(sa & sb) / float(len(sb))
    bi_a = {(x, y) for x, y in zip(a, a[1:])}
    bi_b = {(x, y) for x, y in zip(b, b[1:])}
    bi = len(bi_a & bi_b) / float(len(bi_b)) if bi_b else uni
    cover = len(sa & sb) / float(len(sa))
    # câu mẫu quá ngắn (1–2 từ có nghĩa, vd. "ở đâu" ~ "đau" sau khi bỏ dấu) không đủ tin cậy
    weight = min(1.0, len(sb) / 3.0)
    return round((0.45 * uni + 0.35 * bi + 0.20 * cover) * weight, 3)


class DmagAiReplyTool(models.Model):
    _name = 'dmag.ai.reply.tool'
    _description = 'Công cụ trợ lý Zalo được phép dùng'
    _order = 'sequence, id'

    name = fields.Char('Công cụ', required=True)
    code = fields.Char('Mã công cụ', required=True)
    sequence = fields.Integer(default=10)
    description = fields.Char('Mô tả')
    side_effect = fields.Boolean('Ghi dữ liệu', help='Công cụ tạo / sửa dữ liệu (giữ chỗ lịch hẹn, chuyển nhân viên).')

    _sql_constraints = [('code_uniq', 'unique(code)', 'Mã công cụ đã tồn tại.')]


class DmagAiReplyScript(models.Model):
    _name = 'dmag.ai.reply.script'
    _description = 'Kịch bản trả lời đã duyệt (trợ lý Zalo)'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'sequence, id'

    name = fields.Char('Kịch bản / chủ đề', required=True, tracking=True)
    code = fields.Char('Mã ý định', required=True, tracking=True,
                       help='Mã ngắn không dấu, ví dụ gia_dich_vu – Claude chọn ý định trong danh sách mã này.')
    sequence = fields.Integer(default=10)
    active = fields.Boolean('Đang dùng', default=True, tracking=True)
    company_id = fields.Many2one('res.company', string='Phòng khám', required=True, index=True,
                                 default=lambda self: self.env.company)
    category = fields.Selection(SCRIPT_CATEGORIES, string='Nhóm', required=True, default='info')
    flow = fields.Selection(SCRIPT_FLOWS, string='Cách trả lời', required=True, default='template', tracking=True)
    handoff_reason = fields.Selection(HANDOFF_REASONS, string='Lý do chuyển nhân viên', default='medical_question')
    sample_questions = fields.Text('Câu hỏi mẫu của khách', required=True,
                                   help='Mỗi dòng một cách hỏi thường gặp – dùng để nhận diện ý định.')
    keywords = fields.Char('Từ khóa nhận diện',
                           help='Cách nhau bằng dấu phẩy; khớp từ khóa (không phân biệt dấu) → độ tin cậy cao.')
    answer_template = fields.Text('Mẫu trả lời đã duyệt', required=True,
                                  help='Văn bản gửi khách; ô {…} được điền bằng dữ liệu thật của Odoo lúc trả lời.')
    allow_rephrase = fields.Boolean('Cho phép AI diễn đạt lại nhẹ',
                                    help='Chỉ ở chế độ Claude: diễn đạt lại câu chữ cho tự nhiên, giữ nguyên mọi con số, '
                                         'giá, giờ, địa chỉ; nếu lệch số liệu hệ thống tự dùng nguyên mẫu.')
    min_confidence = fields.Float('Ngưỡng tin cậy riêng', help='Để trống (0) = dùng ngưỡng chung của phòng khám.')
    service_ids = fields.Many2many('product.product', string='Dịch vụ báo giá', domain=[('is_dental_service', '=', True)],
                                   help='Dịch vụ điền vào {gia_dich_vu} khi khách không nêu rõ dịch vụ.')
    tool_ids = fields.Many2many('dmag.ai.reply.tool', string='Công cụ được phép')
    doctor_scope = fields.Char('Phạm vi bác sĩ nêu tên',
                               help='Mã phạm vi hành nghề (vd. scope_ortho) – {bac_si_lam_viec} chỉ liệt kê bác sĩ có '
                                    'phạm vi này. Để trống = mọi bác sĩ.')
    quick_replies = fields.Char('Nút trả lời nhanh', help='Cách nhau bằng dấu "|", ví dụ: Đặt lịch | Địa chỉ')
    state = fields.Selection([('draft', 'Nháp – chờ Giám đốc duyệt'), ('approved', 'Đã duyệt')], string='Trạng thái',
                             default='draft', required=True, tracking=True, copy=False, index=True)
    proposed_by_id = fields.Many2one('res.users', string='Người đề xuất', readonly=True, copy=False,
                                     default=lambda self: self.env.user)
    approved_by_id = fields.Many2one('res.users', string='Giám đốc duyệt', readonly=True, copy=False, tracking=True)
    approved_at = fields.Datetime('Duyệt lúc', readonly=True, copy=False)
    source_message_id = fields.Many2one('dmag.ai.conversation.message', string='Từ tin nhắn', readonly=True, copy=False)
    origin = fields.Selection([('sample', 'Bộ kịch bản chuẩn'), ('manual', 'Quản lý soạn'),
                               ('proposal', 'Nhân viên đề xuất từ hộp thư')], string='Nguồn', default='manual',
                              readonly=True, copy=False, index=True)
    example_ids = fields.One2many('dmag.ai.reply.example', 'script_id', string='Ví dụ hỏi – đáp')
    example_count = fields.Integer(compute='_compute_counts')
    usage_count = fields.Integer('Số lần tự trả lời', readonly=True, copy=False)
    last_used_at = fields.Datetime('Dùng gần nhất', readonly=True, copy=False)
    placeholder_help = fields.Html('Ô dữ liệu dùng được', compute='_compute_placeholder_help', sanitize=False)
    preview = fields.Text('Xem trước (dữ liệu thật)', compute='_compute_preview')
    approval_banner = fields.Char('Tóm tắt duyệt', compute='_compute_approval_banner')

    @api.depends('state', 'approved_by_id', 'approved_at')
    def _compute_approval_banner(self):
        for script in self:
            when = fields.Datetime.context_timestamp(script, script.approved_at) if script.approved_at else None
            script.approval_banner = _('Giám đốc %(user)s đã duyệt lúc %(when)s – nội dung bị khóa', user=script.approved_by_id.name or '',
                                       when=when.strftime('%d/%m/%Y %H:%M') if when else '') \
                if script.state == 'approved' else False

    _sql_constraints = [('code_company_uniq', 'unique(code, company_id)', 'Mã ý định đã có trong phòng khám.')]

    @api.depends('example_ids')
    def _compute_counts(self):
        for script in self:
            script.example_count = len(script.example_ids)

    def _compute_placeholder_help(self):
        rows = ''.join('<tr><td><code>{%s}</code></td><td>%s</td><td class="text-muted">%s</td></tr>'
                       % (key, label, tool or '') for key, (label, tool) in PLACEHOLDERS.items())
        html = ('<table class="table table-sm mb-0"><thead><tr><th>Ô</th><th>Điền bằng</th><th>Công cụ cần</th>'
                '</tr></thead><tbody>%s</tbody></table>' % rows)
        for script in self:
            script.placeholder_help = html

    @api.depends('answer_template', 'service_ids', 'tool_ids')
    def _compute_preview(self):
        Reception = self.env['dmag.ai.reception']
        for script in self:
            try:
                script.preview = Reception._render_script(script, None, '')['text'] if script.answer_template else ''
            except Exception as e:  # noqa: BLE001 – xem trước không được làm hỏng form
                script.preview = _('(Chưa xem trước được: %s)', e)

    # ------------------------------------------------------------------ CRUD / khóa
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('state') == 'approved' and not is_workflow(self.env):
                check_director(self.env, _('Chỉ Giám đốc được duyệt kịch bản trả lời.'))
            if vals.get('code'):
                vals['code'] = self._clean_code(vals['code'])
        return super().create(vals_list)

    def write(self, vals):
        if not is_workflow(self.env):
            if 'state' in vals or {'approved_by_id', 'approved_at'} & set(vals):
                check_director(self.env, _('Chỉ Giám đốc được duyệt / mở lại kịch bản trả lời.'))
            locked = self.filtered(lambda s: s.state == 'approved')
            if locked and CONTENT_FIELDS & set(vals) and vals.get('state') != 'draft':
                raise UserError(_('Kịch bản "%s" đã được Giám đốc duyệt nên bị khóa. Giám đốc bấm "Mở lại để sửa" '
                                  '(trợ lý ngừng dùng kịch bản đến khi duyệt lại).', locked[0].name))
            if vals.get('code'):
                vals['code'] = self._clean_code(vals['code'])
        return super().write(vals)

    def unlink(self):
        if self.filtered(lambda s: s.state == 'approved') and not is_director(self.env):
            raise UserError(_('Kịch bản đã duyệt chỉ Giám đốc được xóa – hoặc lưu trữ (bỏ "Đang dùng").'))
        return super().unlink()

    @staticmethod
    def _clean_code(code):
        return re.sub(r'[^a-z0-9_]+', '_', fold(code)).strip('_')[:40] or 'kich_ban'

    @api.constrains('answer_template', 'tool_ids', 'flow')
    def _check_placeholders(self):
        for script in self:
            unknown = set(PLACEHOLDER_RE.findall(script.answer_template or '')) - set(PLACEHOLDERS)
            if unknown:
                raise ValidationError(_('Mẫu trả lời có ô không hỗ trợ: %(bad)s. Dùng: %(ok)s.',
                                        bad=', '.join('{%s}' % u for u in sorted(unknown)),
                                        ok=', '.join('{%s}' % k for k in PLACEHOLDERS)))

    def _missing_tools(self):
        self.ensure_one()
        allowed = set(self.tool_ids.mapped('code'))
        need = {PLACEHOLDERS[p][1] for p in PLACEHOLDER_RE.findall(self.answer_template or '')
                if p in PLACEHOLDERS and PLACEHOLDERS[p][1]}
        if self.flow == 'booking':
            need |= {'get_free_slots', 'book_appointment'}
        return sorted(need - allowed)

    # ------------------------------------------------------------------ duyệt
    def action_approve(self):
        check_director(self.env, _('Chỉ Giám đốc được duyệt kịch bản trả lời.'))
        for script in self:
            missing = script._missing_tools()
            if missing:
                raise UserError(_('Kịch bản "%(name)s" dùng ô dữ liệu / luồng cần công cụ chưa được phép: %(tools)s.',
                                  name=script.name, tools=', '.join(missing)))
            if not content_tokens(script.sample_questions) and not script.keywords:
                raise UserError(_('Kịch bản "%s" cần câu hỏi mẫu hoặc từ khóa để nhận diện.', script.name))
            script.with_context(dmag_workflow=True).write({
                'state': 'approved', 'approved_by_id': self.env.uid, 'approved_at': fields.Datetime.now()})
            script.message_post(body=_('Giám đốc %s duyệt kịch bản – trợ lý được tự trả lời theo mẫu này.',
                                       self.env.user.name))
        return True

    def action_reset_draft(self):
        check_director(self.env, _('Chỉ Giám đốc được mở lại kịch bản đã duyệt.'))
        for script in self.filtered(lambda s: s.state == 'approved'):
            script.with_context(dmag_workflow=True).write({'state': 'draft', 'approved_by_id': False,
                                                           'approved_at': False})
            script.message_post(body=_('Giám đốc %s mở lại để sửa – trợ lý ngừng dùng kịch bản đến khi duyệt lại.',
                                       self.env.user.name))
        return True

    def _mark_used(self):
        for script in self.sudo():
            script.with_context(dmag_workflow=True, tracking_disable=True).write({
                'usage_count': script.usage_count + 1, 'last_used_at': fields.Datetime.now()})

    # ------------------------------------------------------------------ nhận diện (giả lập / tại chỗ)
    def _samples(self):
        self.ensure_one()
        lines = [l.strip() for l in (self.sample_questions or '').splitlines() if l.strip()]
        lines += self.example_ids.filtered(lambda e: e.state == 'approved').mapped('question')
        return lines

    def _keywords(self):
        self.ensure_one()
        return [k.strip() for k in (self.keywords or '').split(',') if k.strip()]

    def _match_score(self, text):
        """(độ tin cậy 0..1, lý do) – từ khóa và độ giống với câu hỏi mẫu / ví dụ đã duyệt."""
        self.ensure_one()
        folded = fold(text)
        hits = [k for k in self._keywords() if has_any(folded, [k])]
        kw_score = min(0.97, 0.72 + 0.1 * (len(hits) - 1)) if hits else 0.0
        if hits:
            # từ khóa chỉ đáng tin khi phần lớn câu của khách nói về đúng chủ đề kịch bản (tránh "muốn khám" trong một
            # câu hỏi về hóa đơn công ty được coi là đặt lịch)
            tokens = set(content_tokens(text))
            vocab = set(content_tokens(' '.join(self._samples() + self._keywords() + [self.name or ''])))
            cover = len(tokens & vocab) / float(len(tokens)) if tokens else 1.0
            kw_score = round(kw_score * (0.6 + 0.4 * cover), 3)
        best, best_sample = 0.0, ''
        for sample in self._samples():
            sim = similarity(text, sample)
            if sim > best:
                best, best_sample = sim, sample
        score = max(kw_score, best)
        if hits and best >= 0.3:
            score = min(0.99, score + 0.08)
        if kw_score >= best and hits:
            reason = _('từ khóa: %s', ', '.join(hits[:3]))
        elif best_sample:
            reason = _('giống câu mẫu "%s"', best_sample[:60])
        else:
            reason = _('không có từ khóa / câu mẫu tương tự')
        return round(score, 2), reason

    @api.model
    def _approved(self, company=None):
        company = company or self.env.company
        return self.sudo().search([('state', '=', 'approved'), ('company_id', '=', company.id)])

    @api.model
    def match_local(self, text, scripts=None):
        """Xếp hạng kịch bản cho câu ``text`` – ``[(script, confidence, reason)]`` giảm dần."""
        scripts = self._approved() if scripts is None else scripts
        ranked = []
        for script in scripts:
            score, reason = script._match_score(text)
            ranked.append((script, score, reason))
        ranked.sort(key=lambda r: (-r[1], r[0].sequence, r[0].id))
        return ranked

    @api.model
    def threshold_for(self, script, company=None):
        company = company or self.env.company
        return script.min_confidence or company.dmag_ai_script_threshold or 0.6

    # ------------------------------------------------------------------ màn hình
    def action_view_usage(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'name': _('Câu trả lời theo kịch bản'),
                'res_model': 'dmag.ai.conversation.message', 'view_mode': 'tree,form',
                'domain': [('script_id', '=', self.id)], 'context': {'create': False}}

    def action_view_examples(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'name': _('Ví dụ hỏi – đáp'), 'res_model': 'dmag.ai.reply.example',
                'view_mode': 'tree,form', 'domain': [('script_id', '=', self.id)],
                'context': {'default_script_id': self.id}}

    @api.model
    def action_load_samples(self):
        """Nạp bộ kịch bản mẫu tiếng Việt (bản nháp – Giám đốc đọc, sửa, duyệt)."""
        created = self._load_samples(self.env.company)
        return {'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'title': _('Kịch bản mẫu'), 'type': 'success', 'sticky': False,
                           'message': _('Đã thêm %s kịch bản mẫu (bản nháp).', len(created)),
                           'next': {'type': 'ir.actions.act_window_close'}}}

    @api.model
    def _load_samples(self, company):
        from .reply_script_samples import SAMPLE_SCRIPTS
        Tool = self.env['dmag.ai.reply.tool'].sudo()
        Product = self.env['product.product'].sudo()
        existing = set(self.sudo().with_context(active_test=False).search(
            [('company_id', '=', company.id)]).mapped('code'))
        created = self.browse()
        for seq, sample in enumerate(SAMPLE_SCRIPTS, start=1):
            if sample['code'] in existing:
                continue
            services = Product.browse()
            for word in sample.get('services', []):
                services |= Product.search([('is_dental_service', '=', True), ('name', 'ilike', word),
                                            ('company_id', 'in', [False, company.id])], limit=2)
            vals = {k: v for k, v in sample.items() if k not in ('tools', 'services')}
            vals.update(company_id=company.id, sequence=seq * 10, origin='sample', proposed_by_id=False,
                        tool_ids=[(6, 0, Tool.search([('code', 'in', sample.get('tools', []))]).ids)],
                        service_ids=[(6, 0, services.ids)])
            created |= self.sudo().with_context(mail_create_nolog=True).create(vals)
        return created


class DmagAiReplyExample(models.Model):
    _name = 'dmag.ai.reply.example'
    _description = 'Ví dụ hỏi – đáp đã duyệt (few-shot) cho trợ lý Zalo'
    _order = 'id desc'

    script_id = fields.Many2one('dmag.ai.reply.script', string='Kịch bản', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='script_id.company_id', store=True, index=True)
    question = fields.Text('Khách hỏi', required=True)
    answer = fields.Text('Câu trả lời nhân viên đã duyệt')
    state = fields.Selection([('draft', 'Chờ Giám đốc duyệt'), ('approved', 'Đã duyệt')], default='draft',
                             required=True, string='Trạng thái', index=True)
    proposed_by_id = fields.Many2one('res.users', string='Người đề xuất', readonly=True,
                                     default=lambda self: self.env.user)
    approved_by_id = fields.Many2one('res.users', string='Giám đốc duyệt', readonly=True)
    approved_at = fields.Datetime('Duyệt lúc', readonly=True)
    source_message_id = fields.Many2one('dmag.ai.conversation.message', string='Từ tin nhắn', readonly=True)

    def write(self, vals):
        if not is_workflow(self.env):
            if 'state' in vals or {'approved_by_id', 'approved_at'} & set(vals):
                check_director(self.env, _('Chỉ Giám đốc được duyệt ví dụ hỏi – đáp.'))
            if self.filtered(lambda e: e.state == 'approved') and {'question', 'answer', 'script_id'} & set(vals):
                raise UserError(_('Ví dụ đã duyệt bị khóa – tạo ví dụ mới thay thế.'))
        return super().write(vals)

    def unlink(self):
        if self.filtered(lambda e: e.state == 'approved') and not is_director(self.env):
            raise UserError(_('Chỉ Giám đốc được xóa ví dụ đã duyệt.'))
        return super().unlink()

    def action_approve(self):
        check_director(self.env, _('Chỉ Giám đốc được duyệt ví dụ hỏi – đáp.'))
        self.filtered(lambda e: e.state == 'draft').with_context(dmag_workflow=True).write({
            'state': 'approved', 'approved_by_id': self.env.uid, 'approved_at': fields.Datetime.now()})
        for example in self:
            example.script_id.message_post(body=_('Giám đốc %(user)s duyệt ví dụ: "%(q)s"', user=self.env.user.name,
                                                  q=(example.question or '')[:120]))
        return True
