"""AI-07 – "Kho tri thức trợ lý" và chế độ "Tự động – chỉ trả lời từ dữ liệu đã nạp".

Quyết định của chủ phòng khám (11/10/2026): *"thực ra là muốn thay hoàn toàn nhưng có chuẩn trả lời những cái có trong
database được nạp, còn ngoài mà không có thì phải thông báo tới người phụ trách như lễ tân"*.

* ``dmag.ai.knowledge`` – mục tri thức ĐÃ DUYỆT (chủ đề, các cách hỏi, nội dung, thẻ, nguồn, hiệu lực). Quản lý soạn,
  Giám đốc duyệt, đã duyệt bị khóa. Bộ nạp: kịch bản đã duyệt, dữ liệu gốc Odoo (bảng giá + bảo hành theo dịch vụ, Lịch
  làm việc, Lịch nghỉ luân phiên / ngày trực bác sĩ, địa chỉ, gửi xe, thanh toán, gói chăm sóc), tài liệu tải lên
  (văn bản / Markdown / PDF – tách đoạn), hỏi – đáp nhân viên trả lời trong hộp thư ("Nạp vào kho tri thức").
* Tìm kiếm tại chỗ kiểu BM25, không phân biệt dấu tiếng Việt, có từ đồng nghĩa nha khoa.
* ``dmag.ai.kb.gap`` – "Câu hỏi ngoài dữ liệu": trợ lý không có dữ liệu → gửi khách tin giữ chỗ, báo lễ tân ĐANG TRỰC
  (Lịch nghỉ luân phiên), quá N phút chưa xử lý → báo Quản lý; nhân viên trả lời → một chạm nạp vào kho (nháp → Giám
  đốc duyệt).
* ``dmag.ai.duty.line`` – danh sách lễ tân phụ trách trả lời khách theo phòng khám / kênh.
"""
import base64
import io
import logging
import math
import re
from collections import Counter
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.dmag_dental_base.models.dmag_access import check_director, is_director, is_manager, is_workflow

from .text_utils import fold, money, warranty_text

_logger = logging.getLogger(__name__)

KB_CATEGORIES = [
    ('price', 'Bảng giá & bảo hành'),
    ('schedule', 'Lịch làm việc'),
    ('doctor', 'Bác sĩ & ngày trực'),
    ('clinic', 'Thông tin phòng khám'),
    ('policy', 'Chính sách'),
    ('care_plan', 'Gói chăm sóc'),
    ('script', 'Kịch bản đã duyệt'),
    ('document', 'Tài liệu'),
    ('faq', 'Hỏi – đáp'),
]
SOURCE_TYPES = [
    ('manual', 'Nhập tay'),
    ('script', 'Kịch bản trả lời đã duyệt'),
    ('pricelist', 'Bảng giá (Odoo)'),
    ('schedule', 'Lịch làm việc (Odoo)'),
    ('rotation', 'Lịch nghỉ luân phiên (Odoo)'),
    ('clinic', 'Thông tin phòng khám (Odoo)'),
    ('care_plan', 'Gói chăm sóc (Odoo)'),
    ('document', 'Tài liệu tải lên'),
    ('inbox', 'Nhân viên trả lời trong hộp thư'),
]
# Bộ nạp dữ liệu gốc Odoo – mục tự quản lý, nạp lại thay thế
MASTER_SOURCES = ('pricelist', 'schedule', 'rotation', 'clinic', 'care_plan')
SOURCE_LABELS = {'pricelist': 'Bảng giá', 'schedule': 'Lịch làm việc', 'rotation': 'Lịch nghỉ luân phiên',
                 'clinic': 'Thông tin phòng khám', 'care_plan': 'Gói chăm sóc', 'script': 'Kịch bản',
                 'document': 'Tài liệu', 'inbox': 'Hỏi – đáp từ hộp thư', 'manual': 'Nhập tay'}
LOCKED_FIELDS = {'name', 'category', 'question_variants', 'content', 'tags', 'valid_from', 'valid_to', 'company_id'}

KB_STOPWORDS = {
    'a', 'ah', 'ad', 'oi', 'cho', 'em', 'minh', 'toi', 'anh', 'chi', 'la', 'thi', 'co', 'khong', 'vay', 'nhe', 'nha',
    'voi', 'duoc', 'cua', 'ben', 'ko', 'k', 'gi', 'nao', 'the', 'ra', 'sao', 'can', 'hoi', 'xin', 'chao', 'va', 'o',
    'u', 'luon', 'mot', 'nhu', 'nay', 'kia', 'roi', 'lam', 'muon', 'giup', 'dang', 'ha', 'hay', 'neu', 'thoi', 'cung',
    'nua', 'phong', 'kham', 'khoa', 'rang', 'a', 'da', 'vang', 'de', 'den', 'tu', 'trong', 'ngoai', 'nhieu', 'it',
    'con', 'cac', 'nhung', 'moi', 'khi', 'thu', 'ban', 'shop', 'dc', 've', 'len', 'xuong', 'tai', 'sau', 'truoc',
    'vao', 'ai', 'phai', 'biet', 'xem', 'bi', 'qua', 'lai', 'nhat', 'hon', 'rat', 'cai', 'chiec', 'theo', 'cung',
}
# Từ đồng nghĩa (đã bỏ dấu) → mở rộng truy vấn
SYNONYMS = {
    'trong rang': 'implant cay ghep', 'cay ghep': 'implant', 'nieng': 'chinh nha', 'chinh nha': 'nieng',
    'lay cao': 'cao voi', 'cao rang': 'cao voi', 'voi rang': 'cao voi', 'boc su': 'mao su', 'rang su': 'mao su',
    'han rang': 'tram', 'tram rang': 'tram', 'lay tuy': 'tuy noi nha', 'chua tuy': 'tuy noi nha',
    'mo cua': 'gio lam viec', 'may gio': 'gio lam viec', 'dong cua': 'gio lam viec', 'cuoi tuan': 'chu nhat thu 7',
    'o to': 'oto xe gui', 'dau xe': 'gui xe', 'do xe': 'gui xe', 'bai xe': 'gui xe', 'tra gop': 'thanh toan gop',
    'quet the': 'thanh toan the', 'chuyen khoan': 'thanh toan', 'hoa don do': 'hoa don vat', 'vat': 'hoa don',
    'trang rang': 'tay trang', 'rang khon': 'nho rang khon', 'tre em': 'be tre', 'cho be': 'tre em',
    'bac si': 'bs', 'lich truc': 'ngay truc lam viec', 'nghi ngay': 'nghi luan phien', 'goi nam': 'goi cham soc',
}
STRONG_MIN_IDF = 0.9
ACCEPT_COVERAGE = 0.6
ACCEPT_SCORE = 0.32


def kb_tokens(text):
    return [w for w in re.findall(r'[a-z0-9]+', fold(text)) if w not in KB_STOPWORDS and (len(w) > 1 or w.isdigit())]


def expand_query(text):
    folded = fold(text)
    extra = []
    for phrase, add in SYNONYMS.items():
        if re.search(r'(?<![a-z0-9])' + re.escape(phrase) + r'(?![a-z0-9])', folded):
            extra.append(add)
    return kb_tokens(text), kb_tokens(' '.join(extra))


class KnowledgeIndex:
    """Chỉ mục BM25 thuần Python trên các mục tri thức (trường có trọng số: chủ đề ×3, cách hỏi ×2, thẻ ×2,
    nội dung ×1)."""

    K1, B = 1.2, 0.75

    def __init__(self, docs):
        """``docs``: [(id, {'name', 'questions', 'tags', 'content'})]."""
        self.docs = []
        df = Counter()
        for doc_id, fields_ in docs:
            tf = Counter()
            for key, weight in (('name', 3), ('questions', 2), ('tags', 2), ('content', 1)):
                for tok in kb_tokens(fields_.get(key) or ''):
                    tf[tok] += weight
            bigrams = set()
            for key in ('name', 'questions', 'tags', 'content'):
                toks = kb_tokens(fields_.get(key) or '')
                bigrams |= set(zip(toks, toks[1:]))
            length = sum(tf.values()) or 1
            self.docs.append((doc_id, tf, bigrams, length))
            df.update(tf.keys())
        n = len(self.docs) or 1
        self.n = n
        self.avg = (sum(d[3] for d in self.docs) / n) if self.docs else 1.0
        self.idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}

    def _idf(self, tok):
        return self.idf.get(tok, math.log(1 + (self.n + 0.5) / 0.5))

    def search(self, text, limit=5):
        """[(id, điểm 0..1, độ phủ 0..1, từ khớp)] giảm dần."""
        query, extra = expand_query(text)
        q_unique = list(dict.fromkeys(query))
        if not q_unique and not extra:
            return []
        q_bigrams = set(zip(query, query[1:]))
        weights = {t: 1.0 for t in q_unique}
        for t in extra:
            weights.setdefault(t, 0.6)
        max_score = sum(self._idf(t) * (self.K1 + 1) * w for t, w in weights.items()) or 1.0
        results = []
        for doc_id, tf, bigrams, length in self.docs:
            score, matched = 0.0, []
            for tok, w in weights.items():
                f = tf.get(tok)
                if not f:
                    continue
                norm = f * (self.K1 + 1) / (f + self.K1 * (1 - self.B + self.B * length / self.avg))
                score += self._idf(tok) * norm * w
                matched.append(tok)
            if not matched:
                continue
            score += 0.15 * max_score * len(q_bigrams & bigrams) / max(1, len(q_bigrams))
            covered = [t for t in q_unique if t in tf]
            # độ phủ: phần từ có nghĩa của câu hỏi có trong mục (từ đồng nghĩa khớp bù cho một từ gốc)
            syn_hit = any(t in tf for t in extra)
            coverage = min(1.0, (len(covered) + (1 if syn_hit and len(covered) < len(q_unique) else 0))
                           / float(len(q_unique))) if q_unique else (1.0 if syn_hit else 0.0)
            strong = any(self._idf(t) >= STRONG_MIN_IDF for t in matched)
            results.append((doc_id, round(min(1.0, score / max_score), 3), round(coverage, 2), matched, strong))
        results.sort(key=lambda r: (-(r[1] * 0.6 + r[2] * 0.4), r[0]))
        return results[:limit]


def split_chunks(text, size=700):
    """Tách tài liệu thành đoạn ~``size`` ký tự theo tiêu đề / đoạn văn (giữ tiêu đề gần nhất làm chủ đề)."""
    text = (text or '').replace('\r\n', '\n')
    chunks, title, buf = [], '', []

    def flush():
        body = '\n'.join(buf).strip()
        if body:
            chunks.append((title, body))
        buf.clear()

    for line in text.split('\n'):
        stripped = line.strip()
        heading = re.match(r'^(#{1,6})\s+(.*)$', stripped) or (
            re.match(r'^([A-ZĐ0-9IVX]+[.)])\s+(.{3,80})$', stripped))
        if heading:
            flush()
            title = heading.group(2).strip(' #*')
            continue
        if not stripped:
            if sum(len(b) for b in buf) >= size * 0.6:
                flush()
            elif buf:
                buf.append('')
            continue
        buf.append(stripped)
        if sum(len(b) for b in buf) >= size:
            flush()
    flush()
    return chunks


class DmagAiKnowledge(models.Model):
    _name = 'dmag.ai.knowledge'
    _description = 'Kho tri thức trợ lý (dữ liệu đã nạp)'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'category, sequence, id'

    name = fields.Char('Chủ đề', required=True, tracking=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', string='Phòng khám', required=True, index=True,
                                 default=lambda self: self.env.company)
    category = fields.Selection(KB_CATEGORIES, string='Nhóm', required=True, default='faq')
    source_type = fields.Selection(SOURCE_TYPES, string='Nguồn', required=True, default='manual', index=True)
    source_ref = fields.Char('Mã nguồn', index=True, help='Bản ghi gốc (vd. product.product,12) – bộ nạp dùng để cập nhật.')
    auto_managed = fields.Boolean('Tự cập nhật từ dữ liệu gốc', readonly=True,
                                  help='Mục do bộ nạp tạo từ dữ liệu gốc Odoo; "Nạp lại" cập nhật theo dữ liệu mới nhất.')
    question_variants = fields.Text('Các cách khách hỏi', help='Mỗi dòng một cách hỏi.')
    content = fields.Text('Nội dung được phép trả lời', required=True, tracking=True)
    tags = fields.Char('Thẻ', help='Từ khóa, cách nhau bằng dấu phẩy.')
    document_id = fields.Many2one('dmag.ai.knowledge.document', string='Tài liệu nguồn', ondelete='cascade', index=True)
    script_id = fields.Many2one('dmag.ai.reply.script', string='Kịch bản', ondelete='cascade', index=True)
    valid_from = fields.Date('Hiệu lực từ')
    valid_to = fields.Date('Hiệu lực đến')
    state = fields.Selection([('draft', 'Nháp – chờ Giám đốc duyệt'), ('approved', 'Đã duyệt')], string='Trạng thái',
                             default='draft', required=True, tracking=True, index=True, copy=False)
    proposed_by_id = fields.Many2one('res.users', string='Người soạn / đề xuất', readonly=True,
                                     default=lambda self: self.env.user)
    approved_by_id = fields.Many2one('res.users', string='Người duyệt', readonly=True, copy=False)
    approved_at = fields.Datetime('Duyệt lúc', readonly=True, copy=False)
    approval_note = fields.Char('Ghi chú duyệt', readonly=True)
    refreshed_at = fields.Datetime('Nạp lúc', readonly=True)
    usage_count = fields.Integer('Số lần dùng', readonly=True, copy=False)
    last_used_at = fields.Datetime('Dùng gần nhất', readonly=True, copy=False)
    gap_id = fields.Many2one('dmag.ai.kb.gap', string='Từ câu hỏi ngoài dữ liệu', readonly=True, copy=False)

    _sql_constraints = [('source_ref_uniq', 'unique(company_id, source_type, source_ref)',
                         'Mục tri thức cho bản ghi nguồn này đã có.')]

    # ------------------------------------------------------------------ khóa
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('state') == 'approved' and not is_workflow(self.env):
                check_director(self.env, _('Chỉ Giám đốc được duyệt tri thức cho trợ lý.'))
        return super().create(vals_list)

    def write(self, vals):
        if not is_workflow(self.env):
            if 'state' in vals or {'approved_by_id', 'approved_at'} & set(vals):
                check_director(self.env, _('Chỉ Giám đốc được duyệt / mở lại tri thức cho trợ lý.'))
            locked = self.filtered(lambda k: k.state == 'approved')
            if locked and LOCKED_FIELDS & set(vals) and vals.get('state') != 'draft':
                raise UserError(_('Mục "%s" đã được Giám đốc duyệt nên bị khóa – Giám đốc "Mở lại để sửa".',
                                  locked[0].name))
        return super().write(vals)

    def unlink(self):
        if not is_workflow(self.env) and self.filtered(lambda k: k.state == 'approved') and not is_director(self.env):
            raise UserError(_('Chỉ Giám đốc được xóa tri thức đã duyệt – hoặc lưu trữ.'))
        return super().unlink()

    def action_approve(self):
        check_director(self.env, _('Chỉ Giám đốc được duyệt tri thức cho trợ lý.'))
        for entry in self.filtered(lambda k: k.state == 'draft'):
            entry.with_context(dmag_workflow=True).write({
                'state': 'approved', 'approved_by_id': self.env.uid, 'approved_at': fields.Datetime.now()})
            entry.message_post(body=_('Giám đốc %s duyệt – trợ lý được dùng nội dung này để trả lời khách.',
                                      self.env.user.name))
            entry.activity_ids.action_feedback(feedback=_('Đã duyệt'))
            if entry.gap_id:
                entry.gap_id.sudo().write({'state': 'learned'})
        return True

    def action_reset_draft(self):
        check_director(self.env, _('Chỉ Giám đốc được mở lại tri thức đã duyệt.'))
        self.filtered(lambda k: k.state == 'approved').with_context(dmag_workflow=True).write({
            'state': 'draft', 'approved_by_id': False, 'approved_at': False})
        return True

    # ------------------------------------------------------------------ nội dung "sống"
    def _live_content(self):
        """Nội dung tại thời điểm trả lời: mục dữ liệu gốc dựng lại từ bản ghi gốc (giá / lịch mới nhất)."""
        self.ensure_one()
        if not self.auto_managed or not self.source_ref:
            return self.content
        try:
            model, rid = self.source_ref.split(',')
            record = self.env[model].sudo().browse(int(rid)).exists()
        except (ValueError, KeyError):
            record = None
        builder = getattr(self, '_build_%s' % self.source_type, None)
        if record is not None and record and builder and self.source_type == 'pricelist':
            return builder(record)['content']
        return self.content

    def _source_label(self):
        self.ensure_one()
        if self.source_type == 'script' and self.script_id:
            return _("Kịch bản '%s'", self.script_id.name)
        if self.source_type == 'document' and self.document_id:
            return _("Tài liệu '%s'", self.document_id.name)
        if self.source_type in ('inbox', 'manual'):
            return _("Hỏi – đáp '%s'", self.name)
        return SOURCE_LABELS.get(self.source_type, self.name)

    def _kb_card(self):
        self.ensure_one()
        return {'id': self.id, 'name': self.name, 'state': self.state,
                'state_label': dict(self._fields['state'].selection)[self.state]}

    def _mark_used(self):
        for entry in self.sudo():
            entry.with_context(dmag_workflow=True, tracking_disable=True).write({
                'usage_count': entry.usage_count + 1, 'last_used_at': fields.Datetime.now()})

    # ------------------------------------------------------------------ tìm kiếm
    @api.model
    def _usable(self, company):
        today = fields.Date.context_today(self)
        return self.sudo().search([
            ('company_id', '=', company.id), ('state', '=', 'approved'),
            '|', ('valid_from', '=', False), ('valid_from', '<=', today),
            '|', ('valid_to', '=', False), ('valid_to', '>=', today)])

    @api.model
    def search_knowledge(self, text, company=None, limit=5, entries=None):
        """Tìm mục tri thức ĐÃ DUYỆT, còn hiệu lực. Trả [{'id', 'name', 'content', 'score', 'coverage', 'grounded',
        'source_label', 'category', 'source_type', 'script_id'}] – ``grounded`` = đủ tin cậy để trả lời."""
        company = company or self.env.company
        entries = entries if entries is not None else self._usable(company)
        if not entries:
            return []
        index = KnowledgeIndex([(e.id, {'name': e.name, 'questions': e.question_variants or '', 'tags': e.tags or '',
                                        'content': e.content or ''}) for e in entries])
        by_id = {e.id: e for e in entries}
        out = []
        for doc_id, score, coverage, matched, strong in index.search(text, limit):
            entry = by_id[doc_id]
            out.append({
                'id': entry.id, 'name': entry.name, 'content': entry._live_content(), 'score': score,
                'coverage': coverage, 'matched': matched, 'grounded': bool(strong and coverage >= ACCEPT_COVERAGE
                                                                           and score >= ACCEPT_SCORE),
                'source_label': entry._source_label(), 'category': entry.category, 'source_type': entry.source_type,
                'script_id': entry.script_id.id,
            })
        return out

    # ------------------------------------------------------------------ bộ nạp
    @api.model
    def _upsert(self, company, source_type, source_ref, vals, approve=True):
        """Tạo / cập nhật mục do bộ nạp quản lý (không đụng mục nhập tay)."""
        vals = dict(vals, company_id=company.id, source_type=source_type, source_ref=source_ref, auto_managed=True,
                    refreshed_at=fields.Datetime.now())
        Entry = self.sudo().with_context(dmag_workflow=True, mail_create_nolog=True, tracking_disable=True)
        entry = Entry.with_context(active_test=False).search([('company_id', '=', company.id),
                                                             ('source_type', '=', source_type),
                                                             ('source_ref', '=', source_ref)], limit=1)
        if approve:
            vals.update(state='approved', approval_note=_('Dữ liệu gốc của Odoo – tự cập nhật khi dữ liệu gốc đổi'))
            if not entry or entry.state != 'approved':
                vals.update(approved_at=fields.Datetime.now(), approved_by_id=self.env.uid)
        if entry:
            vals['active'] = True
            entry.write(vals)
            return entry
        return Entry.create(vals)

    @api.model
    def _build_pricelist(self, product):
        price = self.env['dmag.ai.reception']._service_price(product)
        content = _('Giá niêm yết %(name)s: %(price)s (thời gian khoảng %(dur)s phút); %(wty)s. Chi phí chính xác bác sĩ '
                    'báo sau khi khám.', name=product.name, price=money(price), dur=product.dental_duration or 30,
                    wty=warranty_text(product.warranty_months))
        words = product.name
        return {'name': _('Giá %s', product.name), 'category': 'price', 'content': content,
                'question_variants': '\n'.join([_('%s giá bao nhiêu', words), _('chi phí %s', words),
                                                _('%s bảo hành bao lâu', words)]),
                'tags': ', '.join(filter(None, [product.dental_category or '', 'giá', 'bảng giá', 'bảo hành']))}

    @api.model
    def load_master_data(self, company=None):
        """Nạp / cập nhật dữ liệu gốc Odoo vào kho tri thức (bảng giá + bảo hành, giờ làm việc, ngày nghỉ, bác sĩ & ngày
        trực, địa chỉ, gửi xe, thanh toán, chuẩn bị, gói chăm sóc). Mục không còn nguồn được lưu trữ."""
        company = company or self.env.company
        Reception = self.env['dmag.ai.reception'].sudo().with_company(company)
        keep = self.browse()
        # 1. Bảng giá + bảo hành theo dịch vụ
        for product in Reception._services():
            keep |= self._upsert(company, 'pricelist', 'product.product,%s' % product.id, self._build_pricelist(product))
        warranty = [p for p in Reception._services() if p.warranty_months]
        if warranty:
            keep |= self._upsert(company, 'pricelist', 'warranty,all', {
                'name': _('Bảo hành theo dịch vụ'), 'category': 'price',
                'content': _('Thời hạn bảo hành (ghi trên thẻ bảo hành điện tử): %s.',
                             '; '.join('%s – %s' % (p.name, warranty_text(p.warranty_months)) for p in warranty)),
                'question_variants': _('bảo hành bao lâu\nrăng sứ bảo hành mấy năm\nimplant có bảo hành không'),
                'tags': _('bảo hành, thẻ bảo hành')})
        # 2. Lịch làm việc + ngày nghỉ
        schedule = self.env['dmag.clinic.schedule'].sudo()._get_for_company(company)
        info = schedule._info()
        hours = info.weekly_text()
        keep |= self._upsert(company, 'schedule', 'clinic.schedule,%s' % schedule.id, {
            'name': _('Giờ làm việc'), 'category': 'schedule',
            'content': _('Giờ làm việc của phòng khám: %(hours)s.%(note)s', hours=hours,
                         note=(' ' + schedule.note) if schedule.note else ''),
            'question_variants': _('phòng khám mở cửa mấy giờ\nchủ nhật có làm việc không\nmấy giờ đóng cửa\n'
                                   'cuối tuần có mở cửa không\ngiờ làm việc'),
            'tags': _('giờ làm việc, mở cửa, đóng cửa, chủ nhật, cuối tuần')})
        today = fields.Date.context_today(self)
        upcoming = [(a, b, n) for a, b, n in info.closures if b >= today and a <= today + timedelta(days=90)]
        keep |= self._upsert(company, 'schedule', 'clinic.closure,upcoming', {
            'name': _('Ngày nghỉ lễ sắp tới'), 'category': 'schedule',
            'content': (_('Phòng khám nghỉ: %s.', '; '.join(
                '%s%s %s' % (a.strftime('%d/%m/%Y'), ('–' + b.strftime('%d/%m/%Y')) if b != a else '',
                             n.replace('[CẦN XÁC MINH]', '').strip()) for a, b, n in upcoming))
                        if upcoming else _('Trong 90 ngày tới phòng khám không có ngày nghỉ lễ / nghỉ đột xuất.')),
            'question_variants': _('lễ có nghỉ không\nngày lễ phòng khám có làm không\ntết nghỉ ngày nào'),
            'tags': _('nghỉ lễ, ngày lễ, tết')})
        # 3. Bác sĩ & ngày trực (Lịch nghỉ luân phiên)
        doctors = self.env['dmag.dental.practitioner'].sudo().search([('role', '=', 'doctor'),
                                                                     ('company_id', '=', company.id)])
        for doc in doctors:
            scopes = ', '.join(doc.scope_ids.mapped('name'))
            keep |= self._upsert(company, 'rotation', 'dmag.dental.practitioner,%s' % doc.id, {
                'name': _('Lịch làm việc %s %s', doc.title or 'BS', doc.name), 'category': 'doctor',
                'content': _('%(title)s %(name)s %(duty)s.%(scope)s', title=doc.title or 'BS', name=doc.name,
                             duty=doc.duty_text(info), scope=(_(' Chuyên môn: %s.', scopes) if scopes else '')),
                'question_variants': _('bác sĩ %(n)s làm ngày nào\nbác sĩ %(g)s có làm chủ nhật không\n'
                                       'lịch trực bác sĩ %(g)s', n=doc.name, g=doc.name.split()[-1]),
                'tags': _('bác sĩ, lịch trực, ngày làm việc, %s', doc.name)})
        # 4. Thông tin phòng khám
        clinic = Reception.tool_get_clinic_info('all')
        for key, name, questions, tags in (
                ('address', _('Địa chỉ phòng khám'), _('phòng khám ở đâu\ncho xin địa chỉ\nđường nào'),
                 _('địa chỉ, ở đâu, chỉ đường')),
                ('parking', _('Gửi xe'), _('có chỗ đậu ô tô không\ngửi xe máy ở đâu'), _('gửi xe, đỗ xe, ô tô, xe máy')),
                ('payment', _('Thanh toán & trả góp'), _('có trả góp không\ncó quẹt thẻ được không\nchuyển khoản được không'),
                 _('thanh toán, trả góp, thẻ, chuyển khoản')),
                ('preparation', _('Chuẩn bị trước khi khám'), _('đi khám cần mang gì\ncó cần nhịn ăn không'),
                 _('chuẩn bị, mang theo, giấy tờ')),
                ('hotline', _('Hotline'), _('số điện thoại phòng khám\nhotline'), _('hotline, số điện thoại, gọi'))):
            value = clinic.get(key)
            if not value:
                continue
            content = '%s: %s' % (name, value)
            if key == 'address' and clinic.get('hotline'):
                content += _('. Hotline: %s', clinic['hotline'])
            keep |= self._upsert(company, 'clinic', 'res.company,%s,%s' % (company.id, key), {
                'name': name, 'category': 'policy' if key == 'payment' else 'clinic', 'content': content,
                'question_variants': questions, 'tags': tags})
        # 5. Gói chăm sóc
        if 'dmag.care.plan' in self.env:
            for plan in self.env['dmag.care.plan'].sudo().search([('company_id', 'in', [False, company.id])]):
                items = ', '.join('%g× %s' % (l.quantity, l.product_id.name) for l in plan.line_ids)
                keep |= self._upsert(company, 'care_plan', 'dmag.care.plan,%s' % plan.id, {
                    'name': _('Gói chăm sóc %s', plan.name), 'category': 'care_plan',
                    'content': _('%(name)s: %(price)s cho %(months)s tháng%(items)s.%(desc)s', name=plan.name,
                                 price=money(plan.price), months=plan.duration_months,
                                 items=(_(' – gồm %s', items) if items else ''),
                                 desc=(' ' + plan.description) if plan.description else ''),
                    'question_variants': _('gói chăm sóc theo năm\ngói khám định kỳ\ngói %s gồm gì', plan.name),
                    'tags': _('gói chăm sóc, gói năm, thành viên')})
        # mục dữ liệu gốc không còn nguồn → lưu trữ
        stale = self.sudo().search([('company_id', '=', company.id), ('source_type', 'in', MASTER_SOURCES),
                                    ('id', 'not in', keep.ids)])
        stale.with_context(dmag_workflow=True).write({'active': False})
        return keep

    @api.model
    def load_scripts(self, company=None):
        """Kịch bản đã duyệt → mục tri thức (đã duyệt sẵn vì kịch bản đã được Giám đốc duyệt)."""
        company = company or self.env.company
        keep = self.browse()
        scripts = self.env['dmag.ai.reply.script'].sudo().search([('company_id', '=', company.id),
                                                                 ('state', '=', 'approved')])
        for script in scripts:
            template = re.sub(r'\{[a-z_]+\}', '…', script.answer_template or '')
            entry = self._upsert(company, 'script', 'dmag.ai.reply.script,%s' % script.id, {
                'name': script.name, 'category': 'script', 'script_id': script.id, 'content': template,
                'question_variants': script.sample_questions, 'tags': script.keywords or ''})
            entry.sudo().with_context(dmag_workflow=True).write({'approval_note': _(
                'Kịch bản do Giám đốc %s duyệt', script.approved_by_id.name or '')})
            keep |= entry
        stale = self.sudo().search([('company_id', '=', company.id), ('source_type', '=', 'script'),
                                    ('id', 'not in', keep.ids)])
        stale.with_context(dmag_workflow=True).write({'active': False})
        return keep

    @api.model
    def action_refresh_all(self):
        """Nút "Nạp lại dữ liệu": dữ liệu gốc Odoo + kịch bản đã duyệt (Quản lý trở lên)."""
        if not is_manager(self.env):
            raise UserError(_('Chỉ Quản lý trở lên được nạp lại dữ liệu cho trợ lý.'))
        company = self.env.company
        master = self.load_master_data(company)
        scripts = self.load_scripts(company)
        company.sudo().dmag_ai_kb_refreshed_at = fields.Datetime.now()
        return {'master': len(master), 'scripts': len(scripts)}

    @api.model
    def _cron_refresh(self):
        for company in self.env['res.company'].sudo().search([]):
            self.with_company(company).sudo().load_master_data(company)
            self.with_company(company).sudo().load_scripts(company)
            company.dmag_ai_kb_refreshed_at = fields.Datetime.now()
        return True

    # ------------------------------------------------------------------ màn hình "Dữ liệu đã nạp"
    @api.model
    def get_kb_overview(self):
        company = self.env.company
        Entry = self.sudo()
        groups = []
        for code, label in SOURCE_TYPES:
            domain = [('company_id', '=', company.id), ('source_type', '=', code)]
            approved = Entry.search_count(domain + [('state', '=', 'approved')])
            draft = Entry.search_count(domain + [('state', '=', 'draft')])
            last = Entry.search(domain, order='refreshed_at desc, write_date desc', limit=1)
            if code == 'document':
                docs = self.env['dmag.ai.knowledge.document'].sudo().search([('company_id', '=', company.id)])
                extra = _('%s tài liệu', len(docs))
            else:
                extra = ''
            groups.append({'code': code, 'label': label, 'approved': approved, 'draft': draft, 'extra': extra,
                           'last': fields.Datetime.to_string(last.refreshed_at or last.write_date) if last else ''})
        drafts = Entry.search([('company_id', '=', company.id), ('state', '=', 'draft')], limit=12,
                              order='create_date desc')
        gaps = self.env['dmag.ai.kb.gap'].sudo().search([('company_id', '=', company.id)], limit=8,
                                                         order='create_date desc')
        top = Entry.search([('company_id', '=', company.id), ('usage_count', '>', 0)], order='usage_count desc',
                           limit=6)
        docs = self.env['dmag.ai.knowledge.document'].sudo().search([('company_id', '=', company.id)], limit=6)
        return {
            'groups': groups,
            'total_approved': Entry.search_count([('company_id', '=', company.id), ('state', '=', 'approved')]),
            'total_draft': Entry.search_count([('company_id', '=', company.id), ('state', '=', 'draft')]),
            'refreshed_at': fields.Datetime.to_string(company.dmag_ai_kb_refreshed_at)
            if company.dmag_ai_kb_refreshed_at else '',
            'reply_mode': company.dmag_ai_zalo_reply_mode,
            'drafts': [{'id': d.id, 'name': d.name, 'content': (d.content or '')[:220],
                        'source': SOURCE_LABELS.get(d.source_type, ''),
                        'proposed_by': d.proposed_by_id.name or '', 'category': dict(KB_CATEGORIES).get(d.category)}
                       for d in drafts],
            'gaps': [g._card() for g in gaps],
            'top': [{'id': e.id, 'name': e.name, 'count': e.usage_count, 'source': e._source_label()} for e in top],
            'documents': [{'id': d.id, 'name': d.name, 'chunks': len(d.chunk_ids), 'state': d.state,
                           'filename': d.filename or ''} for d in docs],
            'can_manage': is_manager(self.env), 'is_director': is_director(self.env),
        }

    @api.model
    def try_question(self, text):
        """Ô "Thử hỏi trợ lý" trên màn hình Dữ liệu đã nạp: kết quả tìm kiếm + kết luận có / ngoài dữ liệu."""
        hits = self.search_knowledge(text, limit=5)
        script_hits = self.env['dmag.ai.reply.script'].match_local(text)[:1]
        return {
            'hits': [dict(h, content=h['content'][:300]) for h in hits],
            'grounded': bool(hits and hits[0]['grounded']),
            'script': {'name': script_hits[0][0].name, 'confidence': round(script_hits[0][1] * 100)}
            if script_hits and script_hits[0][1] >= 0.6 else False,
        }


class DmagAiKnowledgeDocument(models.Model):
    _name = 'dmag.ai.knowledge.document'
    _description = 'Tài liệu nạp cho trợ lý'
    _inherit = ['mail.thread']
    _order = 'id desc'

    name = fields.Char('Tên tài liệu', required=True, tracking=True)
    company_id = fields.Many2one('res.company', string='Phòng khám', required=True, index=True,
                                 default=lambda self: self.env.company)
    datas = fields.Binary('Tệp (TXT / Markdown / PDF)', attachment=True)
    filename = fields.Char('Tên tệp')
    text = fields.Text('Văn bản trích xuất')
    chunk_ids = fields.One2many('dmag.ai.knowledge', 'document_id', string='Các đoạn đã tách')
    chunk_count = fields.Integer(compute='_compute_chunk_count')
    state = fields.Selection([('draft', 'Chờ Giám đốc duyệt'), ('approved', 'Đã duyệt')], default='draft',
                             required=True, tracking=True, string='Trạng thái')
    valid_to = fields.Date('Hiệu lực đến')

    @api.depends('chunk_ids')
    def _compute_chunk_count(self):
        for doc in self:
            doc.chunk_count = len(doc.chunk_ids)

    @api.model
    def _extract_text(self, raw, filename):
        name = (filename or '').lower()
        if name.endswith('.pdf') or raw[:4] == b'%PDF':
            try:
                from PyPDF2 import PdfReader
            except ImportError:  # pragma: no cover
                raise UserError(_('Máy chủ thiếu thư viện đọc PDF (PyPDF2).'))
            reader = PdfReader(io.BytesIO(raw))
            return '\n\n'.join((page.extract_text() or '') for page in reader.pages)
        for enc in ('utf-8-sig', 'utf-16', 'cp1258', 'latin-1'):
            try:
                return raw.decode(enc)
            except UnicodeDecodeError:
                continue
        return ''

    def action_extract(self):
        """Trích văn bản + tách đoạn → các mục tri thức NHÁP (Giám đốc duyệt tài liệu = duyệt mọi đoạn)."""
        if not is_manager(self.env):
            raise UserError(_('Chỉ Quản lý trở lên được nạp tài liệu cho trợ lý.'))
        Entry = self.env['dmag.ai.knowledge'].sudo().with_context(dmag_workflow=True, mail_create_nolog=True)
        for doc in self:
            if doc.datas:
                doc.text = self._extract_text(base64.b64decode(doc.datas), doc.filename)
            if not (doc.text or '').strip():
                raise UserError(_('Không trích được văn bản từ "%s" (PDF dạng ảnh cần nhận dạng chữ trước).', doc.name))
            doc.chunk_ids.with_context(dmag_workflow=True).unlink()
            for i, (title, body) in enumerate(split_chunks(doc.text), start=1):
                Entry.create({
                    'name': title or _('%(doc)s – đoạn %(n)s', doc=doc.name, n=i), 'category': 'document',
                    'source_type': 'document', 'source_ref': 'doc,%s,%s' % (doc.id, i), 'document_id': doc.id,
                    'company_id': doc.company_id.id, 'content': body, 'question_variants': title or '',
                    'valid_to': doc.valid_to, 'sequence': i, 'state': 'draft', 'proposed_by_id': self.env.uid,
                    'refreshed_at': fields.Datetime.now()})
            doc.with_context(dmag_workflow=True).state = 'draft'
            doc.message_post(body=_('Đã tách %s đoạn – chờ Giám đốc duyệt.', len(doc.chunk_ids)))
        return True

    def action_approve(self):
        check_director(self.env, _('Chỉ Giám đốc được duyệt tài liệu cho trợ lý.'))
        for doc in self:
            doc.chunk_ids.filtered(lambda c: c.state == 'draft').action_approve()
            doc.state = 'approved'
            doc.message_post(body=_('Giám đốc %s duyệt tài liệu (%s đoạn).', self.env.user.name, len(doc.chunk_ids)))
        return True

    def action_view_chunks(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'name': _('Các đoạn của %s', self.name), 'res_model': 'dmag.ai.knowledge',
                'view_mode': 'tree,form', 'domain': [('document_id', '=', self.id)]}


GAP_REASONS = [
    ('no_data', 'Không có trong dữ liệu đã nạp'),
    ('unverified', 'Câu trả lời có số liệu không có trong nguồn – đã chặn'),
    ('medical', 'Câu hỏi chuyên môn – cần bác sĩ'),
    ('ai_error', 'Trợ lý lỗi'),
]


class DmagAiKbGap(models.Model):
    _name = 'dmag.ai.kb.gap'
    _description = 'Câu hỏi ngoài dữ liệu đã nạp'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'state_sequence, create_date desc, id desc'

    name = fields.Char('Câu hỏi', required=True)
    company_id = fields.Many2one('res.company', required=True, index=True, default=lambda self: self.env.company)
    conversation_id = fields.Many2one('dmag.ai.conversation', string='Hội thoại', ondelete='cascade', index=True)
    channel = fields.Selection(related='conversation_id.channel', store=True)
    question_message_id = fields.Many2one('dmag.ai.conversation.message', string='Tin của khách')
    question = fields.Text('Khách hỏi', required=True)
    reason = fields.Selection(GAP_REASONS, string='Lý do', default='no_data', required=True)
    reason_note = fields.Char('Chi tiết')
    state = fields.Selection([('open', 'Chờ nhân viên trả lời'), ('answered', 'Đã trả lời'),
                              ('learned', 'Đã nạp vào kho tri thức'), ('dismissed', 'Bỏ qua')],
                             string='Trạng thái', default='open', required=True, tracking=True, index=True)
    state_sequence = fields.Integer(compute='_compute_state_sequence', store=True)
    assigned_user_id = fields.Many2one('res.users', string='Lễ tân phụ trách', tracking=True)
    assign_note = fields.Char('Cách chọn người phụ trách')
    notified_at = fields.Datetime('Đã báo lúc')
    escalated_at = fields.Datetime('Đã báo Quản lý lúc')
    escalated_user_id = fields.Many2one('res.users', string='Quản lý được báo')
    answer = fields.Text('Câu trả lời của nhân viên')
    answered_by_id = fields.Many2one('res.users', string='Người trả lời')
    answered_at = fields.Datetime('Trả lời lúc')
    knowledge_id = fields.Many2one('dmag.ai.knowledge', string='Mục tri thức', readonly=True)

    @api.depends('state')
    def _compute_state_sequence(self):
        order = {'open': 0, 'answered': 1, 'learned': 2, 'dismissed': 3}
        for gap in self:
            gap.state_sequence = order.get(gap.state, 9)

    # ------------------------------------------------------------------ người phụ trách
    @api.model
    def _responsible(self, company, channel=None, day=None):
        """(người dùng, ghi chú) – lễ tân ĐANG TRỰC hôm nay trong danh sách phụ trách của kênh (Lịch nghỉ luân phiên),
        ít câu chờ nhất; không ai trực → người đầu danh sách; chưa khai danh sách → lễ tân đang trực theo lịch luân
        phiên → nhân viên CSKH mặc định."""
        day = day or fields.Date.context_today(self)
        Rotation = self.env['dmag.staff.rotation'].sudo()
        lines = company.dmag_ai_duty_line_ids.filtered(lambda l: l.channel in ('all', channel or 'all')
                                                       and l.user_id.active).sorted('sequence')
        users = lines.mapped('user_id')
        info = self.env['dmag.clinic.schedule'].sudo().get_info(company)
        note = ''
        if users:
            on_duty = users.filtered(lambda u: not info.roster or info.roster.user_on_duty(u.id, day))
            if on_duty:
                load = {u.id: self.sudo().search_count([('assigned_user_id', '=', u.id), ('state', '=', 'open')])
                        for u in on_duty}
                user = min(on_duty, key=lambda u: (load[u.id], list(users.ids).index(u.id)))
                off = users - on_duty
                note = _('Lễ tân đang trực hôm nay') + (_(' (%s nghỉ)', ', '.join(off.mapped('name'))) if off else '')
                return user, note
            return users[0], _('Không ai trong danh sách trực hôm nay – báo người đầu danh sách và Quản lý')
        roster_users = Rotation.on_duty_users(day, 'receptionist', company)
        if roster_users:
            return roster_users[0], _('Lễ tân đang trực theo Lịch nghỉ luân phiên')
        rule = self.env['dmag.journey.rule'].sudo()
        return rule._dmag_responsible_user('cskh', None, company), _('Nhân viên CSKH mặc định')

    @api.model
    def _escalation_user(self, company):
        if company.dmag_ai_escalation_user_id:
            return company.dmag_ai_escalation_user_id
        group = self.env.ref('dmag_dental_base.group_dmag_manager', raise_if_not_found=False)
        director = self.env.ref('dmag_dental_base.group_dmag_director', raise_if_not_found=False)
        root = self.env.ref('base.user_root')
        directors = director.users if director else self.env['res.users']
        users = group.users.filtered(lambda u: company in u.company_ids and not u.share and u != root
                                     and u not in directors) if group else self.env['res.users']
        return users[:1] or (director.users.filtered(lambda u: company in u.company_ids and u != root)[:1]
                             if director else self.env['res.users'])

    def _bus_notify(self, user, title, message, sticky=True):
        if user and user.partner_id:
            self.env['bus.bus']._sendone(user.partner_id, 'simple_notification', {
                'title': title, 'message': message, 'sticky': sticky, 'type': 'warning'})

    def _assign_and_notify(self):
        for gap in self.sudo():
            company = gap.company_id
            user, note = self._responsible(company, gap.channel)
            gap.write({'assigned_user_id': user.id if user else False, 'assign_note': note,
                       'notified_at': fields.Datetime.now()})
            if not user:
                continue
            conv = gap.conversation_id
            summary = _('Câu hỏi ngoài dữ liệu đã nạp – khách %(name)s hỏi: "%(q)s". Trả lời khách trong Hộp thư trợ lý '
                        'rồi bấm "Nạp vào kho tri thức".', name=conv.name if conv else '-', q=(gap.question or '')[:200])
            target = conv or gap
            target.activity_schedule('dmag_dental_journey.activity_type_cskh_call',
                                     date_deadline=fields.Date.context_today(self),
                                     summary=_('Câu hỏi ngoài dữ liệu: %s', (gap.question or '')[:60]),
                                     note=summary, user_id=user.id)
            gap._bus_notify(user, _('Trợ lý Zalo cần bạn trả lời'), summary)
            gap.message_post(body=_('Đã báo %(user)s (%(note)s).', user=user.name, note=note))
            if _('Không ai') in (note or ''):
                gap._escalate()

    def _escalate(self):
        for gap in self.sudo().filtered(lambda g: not g.escalated_at):
            manager = self._escalation_user(gap.company_id)
            if not manager:
                continue
            minutes = gap.company_id.dmag_ai_escalation_minutes or 15
            text = _('Câu hỏi ngoài dữ liệu chưa được trả lời sau %(m)s phút (lễ tân %(user)s) – khách hỏi: "%(q)s".',
                     m=minutes, user=gap.assigned_user_id.name or '-', q=(gap.question or '')[:200])
            target = gap.conversation_id or gap
            target.activity_schedule('dmag_dental_journey.activity_type_complaint',
                                     date_deadline=fields.Date.context_today(self),
                                     summary=_('QUÁ HẠN – câu hỏi ngoài dữ liệu'), note=text, user_id=manager.id)
            gap._bus_notify(manager, _('Câu hỏi khách chờ quá hạn'), text)
            gap.write({'escalated_at': fields.Datetime.now(), 'escalated_user_id': manager.id})
            gap.message_post(body=_('Báo Quản lý %s (quá hạn xử lý).', manager.name))

    @api.model
    def _cron_escalate(self):
        """Quá N phút (cấu hình theo phòng khám) lễ tân chưa trả lời → báo Quản lý."""
        now = fields.Datetime.now()
        for gap in self.sudo().search([('state', '=', 'open'), ('escalated_at', '=', False),
                                       ('notified_at', '!=', False)]):
            minutes = gap.company_id.dmag_ai_escalation_minutes or 15
            if gap.notified_at <= now - timedelta(minutes=minutes):
                gap._escalate()
        return True

    # ------------------------------------------------------------------ khép vòng: nạp vào kho tri thức
    def _mark_answered(self, answer, message=None):
        for gap in self.sudo().filtered(lambda g: g.state == 'open'):
            gap.write({'state': 'answered', 'answer': answer, 'answered_by_id': self.env.uid,
                       'answered_at': fields.Datetime.now()})
            activities = (gap.conversation_id or gap).activity_ids.filtered(
                lambda a: a.summary and _('ngoài dữ liệu') in a.summary)
            activities.action_feedback(feedback=_('Đã trả lời khách'))

    def action_learn(self, answer=None):
        """Một chạm "Nạp vào kho tri thức": câu hỏi + câu trả lời của nhân viên → mục tri thức NHÁP, giao Giám đốc duyệt."""
        self.ensure_one()
        answer = (answer or self.answer or '').strip()
        if not answer:
            raise UserError(_('Cần câu trả lời của nhân viên trước khi nạp vào kho tri thức.'))
        if self.knowledge_id:
            return self.knowledge_id._kb_card()
        words = [w for w in re.findall(r'\w+', self.question or '')][:9]
        entry = self.env['dmag.ai.knowledge'].sudo().create({
            'name': ' '.join(words)[:80] or _('Hỏi – đáp'), 'category': 'faq', 'source_type': 'inbox',
            'company_id': self.company_id.id, 'question_variants': self.question, 'content': answer,
            'state': 'draft', 'proposed_by_id': self.env.uid, 'gap_id': self.id})
        self.sudo().write({'knowledge_id': entry.id, 'answer': answer})
        director = self.env.ref('dmag_dental_base.group_dmag_director', raise_if_not_found=False)
        root = self.env.ref('base.user_root')
        users = director.users.filtered(lambda u: self.company_id in u.company_ids and not u.share and u != root
                                        and u.id != self.env.ref('base.user_admin').id) if director else []
        for user in (users or director.users.filtered(lambda u: u != root))[:1]:
            entry.activity_schedule('mail.mail_activity_data_todo', summary=_('Duyệt tri thức mới: %s', entry.name),
                                    user_id=user.id, note=_('%s nạp từ hộp thư trợ lý Zalo.', self.env.user.name))
        entry.message_post(body=_('%(user)s nạp từ câu hỏi ngoài dữ liệu của khách – chờ Giám đốc duyệt.',
                                  user=self.env.user.name))
        return entry._kb_card()

    def action_dismiss(self):
        self.sudo().write({'state': 'dismissed'})
        return True

    def _card(self):
        self.ensure_one()
        now = fields.Datetime.now()
        minutes = self.company_id.dmag_ai_escalation_minutes or 15
        due = self.notified_at + timedelta(minutes=minutes) if self.notified_at else None
        return {
            'id': self.id, 'question': self.question, 'state': self.state,
            'state_label': dict(self._fields['state'].selection)[self.state],
            'reason': dict(GAP_REASONS).get(self.reason, ''), 'reason_note': self.reason_note or '',
            'assigned': self.assigned_user_id.name or '', 'assign_note': self.assign_note or '',
            'notified_at': fields.Datetime.to_string(self.notified_at) if self.notified_at else '',
            'escalated': bool(self.escalated_at), 'escalated_to': self.escalated_user_id.name or '',
            'overdue': bool(self.state == 'open' and due and due <= now), 'escalation_minutes': minutes,
            'answer': self.answer or '', 'answered_by': self.answered_by_id.name or '',
            'conversation_id': self.conversation_id.id, 'conversation': self.conversation_id.name or '',
            'knowledge': self.knowledge_id._kb_card() if self.knowledge_id else False,
        }

    @api.model
    def get_open_count(self):
        domain = [('company_id', 'in', self.env.companies.ids), ('state', '=', 'open')]
        mine = self.search_count(domain + [('assigned_user_id', '=', self.env.uid)])
        return {'open': self.search_count(domain), 'mine': mine}


class DmagAiDutyLine(models.Model):
    _name = 'dmag.ai.duty.line'
    _description = 'Lễ tân phụ trách trả lời khách (trợ lý Zalo)'
    _order = 'sequence, id'

    company_id = fields.Many2one('res.company', required=True, ondelete='cascade', index=True,
                                 default=lambda self: self.env.company)
    sequence = fields.Integer(default=10)
    channel = fields.Selection([('all', 'Mọi kênh'), ('zalo', 'Zalo OA'), ('simulator', 'Mô phỏng Zalo'),
                                ('portal', 'Cổng bệnh nhân'), ('web', 'Website')], string='Kênh', default='all',
                               required=True)
    user_id = fields.Many2one('res.users', string='Lễ tân', required=True, domain=[('share', '=', False)])
    on_duty_today = fields.Boolean('Trực hôm nay', compute='_compute_on_duty_today')

    def _compute_on_duty_today(self):
        today = fields.Date.context_today(self)
        for line in self:
            info = self.env['dmag.clinic.schedule'].sudo().get_info(line.company_id)
            line.on_duty_today = info.is_open_day(today) and (not info.roster
                                                               or info.roster.user_on_duty(line.user_id.id, today))
