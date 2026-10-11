"""AI-15 – Phát hiện bất thường bằng THỐNG KÊ TẠI CHỖ (không gửi dữ liệu ra ngoài, không cần LLM).

Bộ phát hiện (mỗi bộ chạy độc lập, module nguồn chưa cài thì bỏ qua):
* ``discount_staff``  – giảm giá theo bác sĩ so với phần còn lại của phòng khám (kiểm định z trên % giảm / thủ thuật);
* ``discount_service`` – thủ thuật giảm giá vượt ngưỡng Tukey (Q3 + 1,5 × IQR) của chính dịch vụ, hoặc vượt hạn mức;
* ``commission_spike`` – hoa hồng tuần của một người hưởng vượt xa lịch sử của chính họ (z bền vững median/MAD);
* ``locked_edits`` – hủy / hoàn / vô hiệu chứng từ đã có hiệu lực theo người thao tác (so với đồng nghiệp);
* ``refund`` – hóa đơn điều chỉnh giảm / hoàn tiền;
* ``cash_diff`` – chênh lệch quỹ tiền mặt lặp lại theo người kiểm đếm;
* ``open_balance`` – công nợ phải thu tăng nhanh so với 4 tuần trước;
* ``stock_usage`` – vật tư dùng vượt định mức (BOM) theo vật tư và theo bác sĩ.
Mỗi phát hiện thành một bản ghi ``dmag.ai.anomaly`` có mức độ, điểm thống kê, chứng từ ("Xem chứng từ") và luồng
xử lý: Quản lý giải trình → Giám đốc đóng (hoặc bác bỏ). Có thể nhờ AI viết lời giải thích (tùy chọn).
"""
import json
import math
from collections import defaultdict
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

from odoo.addons.dmag_dental_base.models.dmag_access import check_director, is_director, is_manager

from . import forecast_math as fm
from .ai_common import vnd
from .ai_forecast import log_local

KINDS = [
    ('discount_staff', 'Giảm giá bất thường theo nhân sự'),
    ('discount_service', 'Giảm giá vượt chuẩn dịch vụ'),
    ('commission_spike', 'Hoa hồng tăng đột biến'),
    ('locked_edits', 'Hủy / sửa chứng từ đã khóa'),
    ('refund', 'Hoàn tiền / hóa đơn điều chỉnh giảm'),
    ('cash_diff', 'Chênh lệch quỹ tiền mặt'),
    ('open_balance', 'Công nợ tăng nhanh'),
    ('stock_usage', 'Vật tư vượt định mức'),
]
SEVERITY = [('low', 'Thấp'), ('medium', 'Trung bình'), ('high', 'Cao')]
STATES = [('new', 'Mới phát hiện'), ('review', 'Quản lý đã giải trình'), ('closed', 'Giám đốc đã đóng'),
          ('dismissed', 'Không phải bất thường')]


class DmagAiAnomaly(models.Model):
    _name = 'dmag.ai.anomaly'
    _description = 'Cảnh báo bất thường (AI-15)'
    _inherit = ['mail.thread']
    _order = 'state_rank, severity_rank desc, date desc, id desc'

    name = fields.Char('Cảnh báo', required=True)
    kind = fields.Selection(KINDS, string='Loại', required=True, index=True)
    severity = fields.Selection(SEVERITY, string='Mức độ', required=True, default='medium', tracking=True)
    severity_rank = fields.Integer(compute='_compute_ranks', store=True)
    state_rank = fields.Integer(compute='_compute_ranks', store=True)
    score = fields.Float('Điểm thống kê', digits=(10, 2), help='Điểm z (số độ lệch chuẩn) hoặc bội số so với chuẩn.')
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company, index=True)
    date = fields.Date('Ngày phát hiện', required=True, default=fields.Date.context_today)
    period_from = fields.Date('Dữ liệu từ')
    period_to = fields.Date('Dữ liệu đến')
    user_id = fields.Many2one('res.users', string='Nhân sự liên quan')
    practitioner_id = fields.Many2one('dmag.dental.practitioner', string='Bác sĩ liên quan')
    subject = fields.Char('Đối tượng', help='Nhân sự / dịch vụ / vật tư / người hưởng liên quan.')
    amount = fields.Float('Số tiền liên quan', digits=(16, 0))
    observed = fields.Char('Quan sát')
    norm = fields.Char('Chuẩn so sánh')
    explanation = fields.Text('Diễn giải (thống kê)')
    evidence_json = fields.Text('Số liệu thống kê (JSON)')
    res_model = fields.Char('Mô hình chứng từ')
    res_ids_json = fields.Text('Chứng từ (id)')
    doc_count = fields.Integer('Số chứng từ', compute='_compute_doc_count')
    fingerprint = fields.Char(index=True, copy=False)
    state = fields.Selection(STATES, default='new', required=True, string='Trạng thái', tracking=True, index=True)
    manager_note = fields.Text('Giải trình của Quản lý', tracking=True)
    reviewed_by_id = fields.Many2one('res.users', string='Người giải trình', readonly=True)
    director_note = fields.Text('Kết luận của Giám đốc', tracking=True)
    closed_by_id = fields.Many2one('res.users', string='Giám đốc đóng', readonly=True)
    ai_narrative = fields.Text('AI giải thích', readonly=True)

    _sql_constraints = [('fingerprint_uniq', 'unique(company_id, fingerprint)', 'Cảnh báo đã tồn tại.')]

    @api.depends('severity', 'state')
    def _compute_ranks(self):
        for rec in self:
            rec.severity_rank = {'low': 1, 'medium': 2, 'high': 3}.get(rec.severity, 0)
            rec.state_rank = {'new': 0, 'review': 1, 'closed': 2, 'dismissed': 3}.get(rec.state, 0)

    def _compute_doc_count(self):
        for rec in self:
            rec.doc_count = len(json.loads(rec.res_ids_json or '[]'))

    # ------------------------------------------------------------------ workflow
    def action_view_documents(self):
        self.ensure_one()
        ids = json.loads(self.res_ids_json or '[]')
        if not self.res_model or self.res_model not in self.env:
            raise UserError(_('Cảnh báo này không gắn chứng từ cụ thể.'))
        return {'type': 'ir.actions.act_window', 'name': _('Chứng từ: %s', self.name), 'res_model': self.res_model,
                'domain': [('id', 'in', ids)], 'views': [[False, 'list'], [False, 'form']], 'target': 'current',
                'context': {'create': False}}

    def action_review(self):
        if not is_manager(self.env):
            raise AccessError(_('Chỉ Quản lý / Giám đốc được giải trình cảnh báo.'))
        for rec in self:
            if not (rec.manager_note or '').strip():
                raise UserError(_('Ghi giải trình (nguyên nhân, đã xử lý gì) trước khi chuyển Giám đốc.'))
            rec.write({'state': 'review', 'reviewed_by_id': self.env.user.id})

    def action_close(self):
        check_director(self.env, _('Chỉ Giám đốc được đóng cảnh báo bất thường.'))
        for rec in self:
            if not (rec.director_note or '').strip():
                raise UserError(_('Ghi kết luận của Giám đốc trước khi đóng cảnh báo.'))
            rec.write({'state': 'closed', 'closed_by_id': self.env.user.id})

    def action_dismiss(self):
        check_director(self.env, _('Chỉ Giám đốc được bác bỏ cảnh báo.'))
        self.write({'state': 'dismissed', 'closed_by_id': self.env.user.id})

    def action_reopen(self):
        check_director(self.env)
        self.write({'state': 'new', 'closed_by_id': False})

    def unlink(self):
        if not is_director(self.env):
            raise AccessError(_('Không xóa cảnh báo bất thường – Giám đốc có thể đóng hoặc bác bỏ.'))
        return super().unlink()

    # ------------------------------------------------------------------ AI giải thích (tùy chọn)
    def action_ai_narrative(self):
        self.ensure_one()
        evidence = json.loads(self.evidence_json or '{}')
        payload = {'loại': dict(KINDS)[self.kind], 'mức_độ': dict(SEVERITY)[self.severity], 'điểm': self.score,
                   'quan_sát': self.observed, 'chuẩn': self.norm, 'diễn_giải_thống_kê': self.explanation,
                   'số_liệu': evidence}
        system = ('Bạn giúp Quản lý phòng khám nha khoa hiểu một cảnh báo bất thường do thống kê phát hiện. Giải thích '
                  'bằng tiếng Việt dễ hiểu (≤ 120 từ): điều gì bất thường, các khả năng (kể cả khả năng hợp lý, '
                  'không quy kết gian lận), và 2–3 bước kiểm tra cụ thể. Chỉ dùng số liệu được cung cấp.')
        res = self.env['dmag.ai'].run('AI-15', system, json.dumps(payload, ensure_ascii=False, default=str),
                                      record=self, simulate=lambda: {'text': self._simulate_narrative()},
                                      max_tokens=1500)
        self.sudo().ai_narrative = res['text']
        self.message_post(body=_('AI giải thích (%s): %s', 'giả lập' if res['simulated'] else 'Claude', res['text']))
        return True

    def _simulate_narrative(self):
        checks = {
            'discount_staff': 'đối chiếu từng ca giảm giá với phiếu duyệt / chương trình khuyến mãi; hỏi lý do với '
                              'nhân sự; xem khách được giảm có phải người quen / khách VIP không',
            'discount_service': 'mở các thủ thuật giảm cao, kiểm tra người duyệt và lý do ghi trên kế hoạch điều trị',
            'commission_spike': 'kiểm tra các dòng hoa hồng lớn có đúng ca đã thu đủ tiền; đối chiếu quy tắc áp dụng',
            'locked_edits': 'xem chatter từng chứng từ bị hủy / hoàn, lý do ghi nhận, ai duyệt',
            'refund': 'kiểm tra biên bản hoàn tiền, chữ ký khách, hình thức hoàn (tiền mặt / chuyển khoản)',
            'cash_diff': 'đối chiếu sổ quỹ, camera quầy thu ngân, phiếu thu trong ca',
            'open_balance': 'rà danh sách khách nợ quá hạn, phân công gọi nhắc, xem có ca hoàn tất chưa xuất hóa đơn',
            'stock_usage': 'đối chiếu phiếu xuất kho với thủ thuật, kiểm tra hàng hỏng / hết hạn, xem lại định mức',
        }.get(self.kind, 'xem chứng từ liên quan')
        return ('%s. Mức %s (điểm thống kê %s). %s Có thể có lý do hợp lý (ca phức tạp, chương trình khuyến mãi, '
                'nhập liệu nhầm) – chưa đủ để kết luận sai phạm. Nên: %s.') % (
            self.observed or self.name, dict(SEVERITY)[self.severity].lower(),
            ('%.1f' % self.score).replace('.', ','), ('Chuẩn so sánh: %s.' % self.norm) if self.norm else '', checks)

    # ------------------------------------------------------------------ chạy phát hiện
    @api.model
    def action_detect(self):
        if not is_manager(self.env):
            raise AccessError(_('Chỉ Quản lý / Giám đốc được chạy phát hiện bất thường.'))
        found = self._detect()
        return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {
            'title': _('Phát hiện bất thường'), 'type': 'info', 'sticky': False,
            'message': _('Đã quét xong: %s cảnh báo mới / cập nhật.', len(found)),
            'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'}}}

    @api.model
    def detect_now(self):
        if not is_manager(self.env):
            raise AccessError(_('Chỉ Quản lý / Giám đốc được chạy phát hiện bất thường.'))
        return len(self._detect())

    @api.model
    def _cron_detect(self):
        for company in self.env['res.company'].search([]):
            env = self.with_company(company).with_context(allowed_company_ids=[company.id])
            if env.env['dmag.ai'].is_feature_active('AI-15'):
                env._detect()

    @api.model
    def _detect(self, today=None):
        today = today or fields.Date.context_today(self)
        det = AnomalyDetector(self.env, today)
        found = []
        for method in (det.discount_staff, det.discount_service, det.commission_spike, det.locked_edits,
                       det.refunds, det.cash_diff, det.open_balance, det.stock_usage):
            try:
                with self.env.cr.savepoint():
                    found += method()
            except Exception as e:  # noqa: BLE001 – một bộ phát hiện lỗi không chặn các bộ khác
                det.errors.append('%s: %s' % (method.__name__, e))
        records = self.browse()
        Anomaly = self.sudo()
        for vals in found:
            vals.setdefault('company_id', self.env.company.id)
            vals.setdefault('date', today)
            vals['evidence_json'] = json.dumps(vals.pop('evidence', {}), ensure_ascii=False, default=str)
            vals['res_ids_json'] = json.dumps(vals.pop('res_ids', []))
            existing = Anomaly.search([('company_id', '=', vals['company_id']),
                                       ('fingerprint', '=', vals['fingerprint'])], limit=1)
            if existing:
                if existing.state in ('new', 'review'):
                    existing.write({k: v for k, v in vals.items() if k not in ('date',)})
                    records |= existing
                continue
            records |= Anomaly.create(vals)
        log_local(self.env, 'AI-15', 'Quét bất thường: %s cảnh báo mới / cập nhật' % len(records))
        self.env['ir.config_parameter'].sudo().set_param(
            'dmag_ai_insights.anomaly_last_run', json.dumps({'at': fields.Datetime.to_string(fields.Datetime.now()),
                                                            'found': len(records), 'errors': det.errors[:10]}))
        return records

    # ------------------------------------------------------------------ RPC màn hình
    @api.model
    def get_anomaly_board(self):
        if not is_manager(self.env):
            raise AccessError(_('Chỉ Quản lý / Giám đốc xem cảnh báo bất thường.'))
        recs = self.search([('company_id', 'in', self.env.companies.ids)], limit=200)
        last = json.loads(self.env['ir.config_parameter'].sudo().get_param('dmag_ai_insights.anomaly_last_run')
                          or '{}')
        rows = []
        for rec in recs:
            rows.append({
                'id': rec.id, 'name': rec.name, 'kind': rec.kind, 'kind_label': dict(KINDS)[rec.kind],
                'severity': rec.severity, 'severity_label': dict(SEVERITY)[rec.severity], 'score': rec.score,
                'state': rec.state, 'state_label': dict(STATES)[rec.state], 'subject': rec.subject or '',
                'observed': rec.observed or '', 'norm': rec.norm or '', 'explanation': rec.explanation or '',
                'amount': rec.amount, 'date': str(rec.date), 'doc_count': rec.doc_count,
                'manager_note': rec.manager_note or '', 'director_note': rec.director_note or '',
                'ai_narrative': rec.ai_narrative or '', 'evidence': json.loads(rec.evidence_json or '{}'),
            })
        counts = defaultdict(int)
        for r in rows:
            if r['state'] in ('new', 'review'):
                counts[r['severity']] += 1
        by_kind = defaultdict(int)
        for r in rows:
            if r['state'] in ('new', 'review'):
                by_kind[r['kind_label']] += 1
        return {'rows': rows, 'open': {k: counts[k] for k in ('high', 'medium', 'low')},
                'by_kind': sorted(by_kind.items(), key=lambda kv: -kv[1]), 'last_run': last,
                'is_director': is_director(self.env), 'kinds': KINDS}

    @api.model
    def set_note(self, anomaly_id, field, value):
        rec = self.browse(anomaly_id)
        if field == 'manager_note' and is_manager(self.env):
            rec.manager_note = value
        elif field == 'director_note' and is_director(self.env):
            rec.director_note = value
        else:
            raise AccessError(_('Không có quyền ghi mục này.'))
        return True


def _dec(value):
    return ('%.1f' % value).replace('.', ',')


class AnomalyDetector:
    """Các bộ phát hiện thống kê. Mỗi hàm trả danh sách giá trị tạo ``dmag.ai.anomaly``."""

    Z_STAFF = 3.0

    def __init__(self, env, today):
        self.env = env
        self.today = today
        self.companies = env.companies
        self.errors = []
        self.engine = env['dmag.goal.engine']

    def M(self, model):
        return self.env[model].sudo()

    def has(self, model):
        return model in self.env

    def scope(self, days):
        return self.engine._scope(self.today - timedelta(days=days - 1), self.today, self.companies,
                                  today=self.today)

    @staticmethod
    def sev(score, high, medium):
        return 'high' if score >= high else 'medium' if score >= medium else 'low'

    # ------------------------------------------------------------------ giảm giá theo bác sĩ
    def discount_staff(self, days=90):
        s = self.scope(days)
        procs = s.procedures.filtered(lambda p: p.price_unit > 0)
        by_doc = defaultdict(list)
        for p in procs:
            by_doc[p.doctor_id].append(p)
        out = []
        for doctor, plist in by_doc.items():
            if not doctor or len(plist) < 8:
                continue
            others = [q for d, ql in by_doc.items() if d != doctor for q in ql]
            if len(others) < 8:
                continue
            own = [p.discount or 0.0 for p in plist]
            oth = [q.discount or 0.0 for q in others]
            sd = fm.stdev(oth) or 1.0
            z = (fm.mean(own) - fm.mean(oth)) / (sd / math.sqrt(len(own)))
            share = 100.0 * sum(1 for v in own if v > 0) / len(own)
            share_o = 100.0 * sum(1 for v in oth if v > 0) / len(oth)
            amount = sum(p.quantity * p.price_unit * (p.discount or 0) / 100.0 for p in plist)
            discounted = [p for p in plist if p.discount]
            if z < self.Z_STAFF or amount < 500000 or fm.mean(own) < 1.5 * fm.mean(oth) + 0.3 or share < share_o + 3:
                continue
            out.append({
                'kind': 'discount_staff', 'fingerprint': 'discount_staff:%s:%s' % (doctor.id, self.today.isocalendar()[:2]),
                'name': 'Giảm giá bất thường – %s' % doctor.name, 'practitioner_id': doctor.id,
                'user_id': doctor.user_id.id, 'subject': doctor.name, 'score': round(z, 2),
                'severity': 'high' if z >= 6 and amount >= 3000000 else 'medium' if z >= 4 else 'low',
                'amount': amount, 'period_from': s.date_from, 'period_to': s.date_to,
                'observed': '%s giảm giá %s/%s thủ thuật (%.0f%%), bình quân %s%%/thủ thuật, tổng %s' % (
                    doctor.name, len(discounted), len(own), share, _dec(fm.mean(own)), vnd(amount)),
                'norm': 'Các bác sĩ khác: %.0f%% số thủ thuật được giảm, bình quân %s%%' % (share_o, _dec(fm.mean(oth))),
                'explanation': ('Kiểm định z trên %% giảm giá mỗi thủ thuật (%s ngày, %s thủ thuật của bác sĩ so với %s '
                                'thủ thuật còn lại): z = %s (ngưỡng %.0f). Giảm giá cao hơn hẳn đồng nghiệp có thể do '
                                'chương trình riêng, khách quen hoặc chiết khấu không được duyệt.') % (
                    days, len(own), len(oth), _dec(z), self.Z_STAFF),
                'evidence': {'n_doctor': len(own), 'n_others': len(oth), 'mean_doctor': round(fm.mean(own), 2),
                             'mean_others': round(fm.mean(oth), 2), 'share_doctor': round(share, 1),
                             'share_others': round(share_o, 1), 'z': round(z, 2), 'amount': amount},
                'res_model': 'dmag.dental.procedure', 'res_ids': [p.id for p in discounted],
            })
        return out

    # ------------------------------------------------------------------ giảm giá vượt chuẩn dịch vụ
    def discount_service(self, days=90):
        s = self.scope(days)
        procs = s.procedures.filtered(lambda p: p.price_unit > 0)
        limit = max(self.companies.mapped('dmag_max_discount') or [0.0])
        by_service = defaultdict(list)
        for p in procs:
            by_service[p.product_id].append(p)
        out = []
        over_limit = procs.filtered(lambda p: limit and (p.discount or 0) > limit)
        if over_limit:
            amount = sum(p.quantity * p.price_unit * p.discount / 100.0 for p in over_limit)
            out.append({
                'kind': 'discount_service', 'fingerprint': 'discount_limit:%s' % ','.join(map(str, over_limit.ids[:50])),
                'name': '%s thủ thuật giảm giá vượt hạn mức %s%%' % (len(over_limit), ('%g' % limit)),
                'subject': ', '.join(sorted(set(over_limit.mapped('product_id.name'))))[:200],
                'score': round(max(over_limit.mapped('discount')) / limit, 2) if limit else 0.0,
                'severity': 'high' if amount >= 5000000 else 'medium', 'amount': amount,
                'period_from': s.date_from, 'period_to': s.date_to,
                'observed': 'Giảm tới %g%% (tổng %s) – vượt hạn mức %g%% của phòng khám' % (
                    max(over_limit.mapped('discount')), vnd(amount), limit),
                'norm': 'Hạn mức giảm giá không cần Giám đốc duyệt: %g%%' % limit,
                'explanation': 'Giảm vượt hạn mức chỉ hợp lệ khi Giám đốc duyệt – đối chiếu người duyệt trên kế hoạch.',
                'evidence': {'count': len(over_limit), 'limit': limit, 'amount': amount},
                'res_model': 'dmag.dental.procedure', 'res_ids': over_limit.ids,
            })
        for product, plist in by_service.items():
            if len(plist) < 8:
                continue
            values = [p.discount or 0.0 for p in plist]
            fence, q1, q3 = fm.iqr_fence(values)
            outliers = [p for p in plist if (p.discount or 0) > max(fence, 0.0) and p.discount
                        and not (limit and p.discount > limit)]
            if len(outliers) < 2:
                continue
            amount = sum(p.quantity * p.price_unit * p.discount / 100.0 for p in outliers)
            if amount < 300000:
                continue
            out.append({
                'kind': 'discount_service', 'fingerprint': 'discount_service:%s:%s' % (product.id, len(outliers)),
                'name': '%s – %s ca giảm giá cao bất thường' % (product.name, len(outliers)),
                'subject': product.name, 'score': round(max(p.discount for p in outliers) / max(fence, 1.0), 2),
                'severity': 'medium' if amount >= 2000000 else 'low', 'amount': amount,
                'period_from': s.date_from, 'period_to': s.date_to,
                'observed': '%s ca giảm %s%% (tổng %s)' % (len(outliers), '–'.join(
                    sorted({'%g' % p.discount for p in outliers})), vnd(amount)),
                'norm': 'Chuẩn dịch vụ: Q1 %g%%, Q3 %g%% → ngưỡng Tukey %g%%' % (q1, q3, fence),
                'explanation': 'Phương pháp IQR (Tukey): giảm giá > Q3 + 1,5 × (Q3 − Q1) của chính dịch vụ trong %s ngày '
                               '(%s thủ thuật).' % (days, len(plist)),
                'evidence': {'q1': q1, 'q3': q3, 'fence': fence, 'n': len(plist), 'outliers': len(outliers)},
                'res_model': 'dmag.dental.procedure', 'res_ids': [p.id for p in outliers],
            })
        return out

    # ------------------------------------------------------------------ hoa hồng
    def commission_spike(self, weeks=12):
        if not self.has('dmag.commission.line'):
            return []
        start = self.today - timedelta(days=self.today.weekday() + 7 * weeks)
        lines = self.M('dmag.commission.line').search([('company_id', 'in', self.companies.ids),
                                                        ('state', '=', 'valid'), ('date', '>=', start),
                                                        ('date', '<=', self.today)])
        by_ben = defaultdict(lambda: defaultdict(list))
        for line in lines:
            week = (line.date - start).days // 7
            by_ben[line.beneficiary or '?'][week].append(line)
        out = []
        current = (self.today - start).days // 7
        for ben, weeks_map in by_ben.items():
            totals = [sum(l.amount for l in weeks_map.get(w, [])) for w in range(current + 1)]
            history = [t for t in totals[:-2] if t]
            if len(history) < 4:
                continue
            for w in (current - 1, current):
                total = totals[w]
                z = fm.robust_z(total, history)
                med = fm.quantile(history, 0.5)
                if z < 3.5 or total < 1500000 or total < 1.8 * med:
                    continue
                wlines = weeks_map[w]
                week_start = start + timedelta(days=7 * w)
                out.append({
                    'kind': 'commission_spike', 'fingerprint': 'commission:%s:%s' % (ben, week_start),
                    'name': 'Hoa hồng tăng đột biến – %s' % ben, 'subject': ben,
                    'user_id': wlines[0].user_id.id, 'practitioner_id': wlines[0].practitioner_id.id,
                    'score': round(z, 2), 'severity': self.sev(z, 8, 5), 'amount': total,
                    'period_from': week_start, 'period_to': week_start + timedelta(days=6),
                    'observed': 'Tuần %s: %s (%s dòng)' % (week_start.strftime('%d/%m'), vnd(total), len(wlines)),
                    'norm': 'Trung vị các tuần trước: %s' % vnd(med),
                    'explanation': 'Điểm z bền vững (median/MAD) so với %s tuần trước của chính người hưởng: z = %s.'
                                   % (len(history), _dec(z)),
                    'evidence': {'weekly_history': [round(h) for h in history], 'week_total': total, 'z': round(z, 2)},
                    'res_model': 'dmag.commission.line', 'res_ids': [l.id for l in wlines],
                })
        return out

    # ------------------------------------------------------------------ hủy / hoàn chứng từ đã khóa
    def _events(self, days=30):
        since = self.today - timedelta(days=days)
        since_dt = fields.Datetime.to_datetime(since)
        until_dt = fields.Datetime.to_datetime(self.today + timedelta(days=1))
        events = []  # (user, label, model, id, amount)
        comp = [('company_id', 'in', self.companies.ids)]
        for move in self.M('account.move').search(comp + [('move_type', '=', 'out_invoice'), ('state', '=', 'cancel'),
                                                         ('write_date', '>=', since_dt), ('write_date', '<', until_dt)]):
            events.append((move.write_uid, 'Hủy hóa đơn', 'account.move', move.id, move.amount_total))
        for move in self.M('account.move').search(comp + [('move_type', '=', 'out_refund'), ('state', '=', 'posted'),
                                                         ('date', '>=', since), ('date', '<=', self.today)]):
            events.append((move.create_uid, 'Hóa đơn điều chỉnh giảm / hoàn', 'account.move', move.id,
                           move.amount_total))
        visits = self.M('dmag.dental.visit').search(comp + [('state', '=', 'cancel'), ('checkin_time', '!=', False),
                                                            ('write_date', '>=', since_dt), ('write_date', '<', until_dt)])
        for visit in visits:
            events.append((visit.write_uid, 'Hủy lượt khám đã check-in', 'dmag.dental.visit', visit.id, 0.0))
        plans = self.M('dmag.treatment.plan').search(comp + [('state', '=', 'cancel'),
                                                             ('accepted_option_id', '!=', False),
                                                             ('write_date', '>=', since_dt), ('write_date', '<', until_dt)])
        for plan in plans:
            events.append((plan.write_uid, 'Hủy kế hoạch đã chốt', 'dmag.treatment.plan', plan.id,
                           plan.amount_accepted))
        if self.has('dmag.prescription'):
            for rx in self.M('dmag.prescription').search([('state', '=', 'cancelled'), ('write_date', '>=', since_dt), ('write_date', '<', until_dt)]):
                events.append((rx.write_uid, 'Hủy đơn thuốc đã phát hành', 'dmag.prescription', rx.id, 0.0))
        if self.has('dmag.lab.order'):
            for order in self.M('dmag.lab.order').search(comp + [('state', '=', 'cancelled'),
                                                                 ('sent_date', '!=', False),
                                                                 ('write_date', '>=', since_dt), ('write_date', '<', until_dt)]):
                events.append((order.write_uid, 'Hủy phiếu labo đã gửi', 'dmag.lab.order', order.id, order.cost))
        if self.has('dmag.warranty.card'):
            for card in self.M('dmag.warranty.card').search(comp + [('state', '=', 'void'),
                                                                    ('write_date', '>=', since_dt), ('write_date', '<', until_dt)]):
                events.append((card.write_uid, 'Vô hiệu thẻ bảo hành', 'dmag.warranty.card', card.id, 0.0))
        return events

    def locked_edits(self, days=30):
        events = [e for e in self._events(days) if e[0] and e[0].id != 1]
        by_user = defaultdict(list)
        for e in events:
            by_user[e[0]].append(e)
        counts = {u: len(v) for u, v in by_user.items()}
        out = []
        for user, evs in by_user.items():
            others = [c for u, c in counts.items() if u != user] or [0]
            others += [0] * max(0, 3 - len(others))
            z = fm.robust_z(len(evs), others)
            money_events = [e for e in evs if e[2] == 'account.move']
            if len(evs) < 3 and not money_events:
                continue
            if len(evs) < 4 and z < 2 and len(money_events) < 2:
                continue
            kinds = defaultdict(int)
            for e in evs:
                kinds[e[1]] += 1
            score = max(z, float(len(evs)))
            model = max(set(e[2] for e in evs), key=lambda m: sum(1 for e in evs if e[2] == m))
            out.append({
                'kind': 'locked_edits', 'fingerprint': 'locked:%s:%s' % (user.id, self.today.isocalendar()[:2]),
                'name': '%s thao tác hủy / hoàn chứng từ – %s' % (len(evs), user.name), 'user_id': user.id,
                'subject': user.name, 'score': round(score, 2),
                'severity': 'high' if len(money_events) >= 2 or len(evs) >= 8 else 'medium' if (
                    money_events or len(evs) >= 4) else 'low',
                'amount': sum(e[4] or 0.0 for e in evs), 'period_from': self.today - timedelta(days=days),
                'period_to': self.today,
                'observed': '; '.join('%s × %s' % (v, k) for k, v in sorted(kinds.items(), key=lambda kv: -kv[1])),
                'norm': 'Đồng nghiệp: trung vị %g thao tác / %s ngày' % (fm.quantile(others, 0.5), days),
                'explanation': 'Chứng từ đã có hiệu lực (hóa đơn, kế hoạch đã chốt, đơn thuốc, labo, bảo hành, lượt đã '
                               'check-in) bị hủy / hoàn bởi cùng một người – điểm z so với đồng nghiệp %s.' % _dec(z),
                'evidence': {'events': dict(kinds), 'peer_counts': others, 'z': round(z, 2)},
                'res_model': model, 'res_ids': [e[3] for e in evs if e[2] == model],
            })
        return out

    def refunds(self, days=30):
        comp = [('company_id', 'in', self.companies.ids)]
        Move = self.M('account.move')
        refunds = Move.search(comp + [('move_type', '=', 'out_refund'), ('state', '=', 'posted'),
                                      ('date', '>=', self.today - timedelta(days=days)), ('date', '<=', self.today)])
        if not refunds:
            return []
        invoices = Move.search(comp + [('move_type', '=', 'out_invoice'), ('state', '=', 'posted'),
                                       ('date', '>=', self.today - timedelta(days=90)), ('date', '<=', self.today)])
        avg = fm.mean(invoices.mapped('amount_total')) or 1.0
        out = []
        for ref in refunds:
            ratio = ref.amount_total / avg
            out.append({
                'kind': 'refund', 'fingerprint': 'refund:%s' % ref.id,
                'name': 'Hoàn tiền / điều chỉnh giảm %s' % vnd(ref.amount_total), 'user_id': ref.create_uid.id,
                'subject': ref.create_uid.name, 'score': round(ratio, 2), 'severity': self.sev(ratio, 3, 1),
                'amount': ref.amount_total, 'period_from': ref.date, 'period_to': ref.date,
                'observed': '%s ngày %s – %s (người lập: %s)' % (ref.name, ref.date.strftime('%d/%m'),
                                                                vnd(ref.amount_total), ref.create_uid.name),
                'norm': 'Giá trị hóa đơn trung bình 90 ngày: %s' % vnd(avg),
                'explanation': 'Mọi khoản hoàn / điều chỉnh giảm đều cần lý do và Giám đốc xác nhận. Bội số so với hóa '
                               'đơn trung bình: %.1f×.' % ratio,
                'evidence': {'amount': ref.amount_total, 'avg_invoice': avg, 'reason': ref.ref or ''},
                'res_model': 'account.move', 'res_ids': ref.ids,
            })
        return out

    def cash_diff(self, days=30):
        if not self.has('dmag.cash.closing'):
            return []
        closings = self.M('dmag.cash.closing').search([('company_id', 'in', self.companies.ids),
                                                       ('date', '>=', self.today - timedelta(days=days)),
                                                       ('date', '<=', self.today), ('cash_diff', '!=', 0)])
        by_user = defaultdict(list)
        for c in closings:
            by_user[c.create_uid].append(c)
        out = []
        total_days = self.M('dmag.cash.closing').search_count([('company_id', 'in', self.companies.ids),
                                                               ('date', '>=', self.today - timedelta(days=days)),
                                                               ('date', '<=', self.today)])
        for user, recs in by_user.items():
            short = sum(c.cash_diff for c in recs)
            if len(recs) < 2:
                continue
            rate = 100.0 * len(recs) / max(1, total_days)
            out.append({
                'kind': 'cash_diff', 'fingerprint': 'cash:%s:%s' % (user.id, self.today.isocalendar()[:2]),
                'name': 'Chênh lệch quỹ lặp lại – %s' % user.name, 'user_id': user.id, 'subject': user.name,
                'score': round(len(recs), 2), 'severity': 'high' if len(recs) >= 6 else 'medium' if len(recs) >= 3
                else 'low', 'amount': abs(short), 'period_from': self.today - timedelta(days=days),
                'period_to': self.today,
                'observed': '%s/%s ca chốt két lệch, tổng %s%s' % (len(recs), total_days, '−' if short < 0 else '+',
                                                                    vnd(abs(short))),
                'norm': 'Chuẩn: 0 đ chênh lệch; ≤ 1 lần / tháng có lý do',
                'explanation': 'Tỷ lệ ca lệch quỹ %.0f%% trong %s ngày.' % (rate, days),
                'evidence': {'diffs': [c.cash_diff for c in recs], 'closings': total_days},
                'res_model': 'dmag.cash.closing', 'res_ids': [c.id for c in recs],
            })
        return out

    # ------------------------------------------------------------------ công nợ
    def _receivable_at(self, moves, day):
        total = 0.0
        for move in moves:
            if not move.invoice_date or move.invoice_date > day:
                continue
            for line in move.line_ids.filtered(lambda l: l.account_id.account_type == 'asset_receivable'):
                paid = sum(p.amount for p in line.matched_credit_ids if p.max_date and p.max_date <= day)
                total += line.balance - paid
        return total

    def open_balance(self):
        moves = self.M('account.move').search([('company_id', 'in', self.companies.ids),
                                               ('move_type', '=', 'out_invoice'), ('state', '=', 'posted'),
                                               ('invoice_date', '>=', self.today - timedelta(days=180)),
                                               ('invoice_date', '<=', self.today)])
        if not moves:
            return []
        now = self._receivable_at(moves, self.today)
        before = self._receivable_at(moves, self.today - timedelta(days=28))
        weekly = [self._receivable_at(moves, self.today - timedelta(days=7 * i)) for i in range(8, -1, -1)]
        growth = (now - before) * 100.0 / before if before > 0 else (100.0 if now > 0 else 0.0)
        if now < 5000000 or growth < 20:
            return []
        overdue = moves.filtered(lambda m: m.amount_residual > 0 and m.invoice_date_due
                                 and m.invoice_date_due < self.today - timedelta(days=30))
        open_moves = moves.filtered(lambda m: m.amount_residual > 0)
        return [{
            'kind': 'open_balance', 'fingerprint': 'open_balance:%s' % (self.today.isocalendar()[:2],),
            'name': 'Công nợ phải thu tăng %.0f%% trong 4 tuần' % growth, 'subject': 'Phải thu khách hàng',
            'score': round(growth / 20.0, 2), 'severity': 'high' if growth >= 60 else 'medium' if growth >= 35
            else 'low', 'amount': now, 'period_from': self.today - timedelta(days=28), 'period_to': self.today,
            'observed': 'Phải thu %s (4 tuần trước %s); %s hóa đơn quá hạn > 30 ngày' % (vnd(now), vnd(before),
                                                                                         len(overdue)),
            'norm': 'Ngưỡng cảnh báo: tăng ≥ 20% trong 4 tuần và ≥ 5 tr',
            'explanation': 'Số dư phải thu tính lại theo ngày (hóa đơn đã ghi sổ − khoản đã đối soát đến ngày đó). '
                           'Chuỗi 8 tuần: %s.' % ', '.join(vnd(w) for w in weekly),
            'evidence': {'weekly': [round(w) for w in weekly], 'growth_pct': round(growth, 1),
                         'overdue_30': len(overdue)},
            'res_model': 'account.move', 'res_ids': open_moves.ids,
        }]

    # ------------------------------------------------------------------ vật tư so với định mức
    def stock_usage(self, days=60):
        if not self.has('dmag.material.usage'):
            return []
        since = fields.Datetime.to_datetime(self.today - timedelta(days=days))
        usages = self.M('dmag.material.usage').search([
            ('company_id', 'in', self.companies.ids), ('date', '>=', since),
            ('date', '<', fields.Datetime.to_datetime(self.today + timedelta(days=1)))])
        if not usages:
            return []
        out = []
        # theo vật tư: thực dùng so với định mức của các thủ thuật đã làm
        procs = usages.mapped('procedure_id')
        norm = defaultdict(float)
        for proc in procs:
            for product, qty in proc._dmag_material_requirements().items():
                norm[product] += qty
        actual = defaultdict(float)
        extra_ids = defaultdict(list)
        for u in usages:
            actual[u.product_id] += u.quantity
            if u.kind == 'extra':
                extra_ids[u.product_id].append(u.id)
        for product, qty in actual.items():
            base = norm.get(product, 0.0)
            over = qty - base
            if base <= 0 or over <= 0:
                continue
            ratio = qty / base
            cost = over * product.standard_price
            if ratio < 1.15 or cost < 300000:
                continue
            out.append({
                'kind': 'stock_usage', 'fingerprint': 'stock:%s:%s' % (product.id, self.today.isocalendar()[:2]),
                'name': '%s dùng vượt định mức %.0f%%' % (product.name, (ratio - 1) * 100), 'subject': product.name,
                'score': round(ratio, 2), 'severity': 'high' if ratio >= 1.6 else 'medium' if ratio >= 1.3 else 'low',
                'amount': cost, 'period_from': self.today - timedelta(days=days), 'period_to': self.today,
                'observed': 'Thực dùng %g %s, định mức %g → vượt %g (≈ %s)' % (
                    round(qty, 2), product.uom_id.name, round(base, 2), round(over, 2), vnd(cost)),
                'norm': 'Định mức BOM × số thủ thuật đã làm trong %s ngày' % days,
                'explanation': 'So sánh tổng vật tư đã ghi nhận với định mức dịch vụ (dmag.service.bom) của chính các '
                               'thủ thuật đó; ngưỡng cảnh báo vượt 15%.',
                'evidence': {'actual': qty, 'norm': base, 'ratio': round(ratio, 3)},
                'res_model': 'dmag.material.usage', 'res_ids': extra_ids.get(product, [])[:200],
            })
        # theo bác sĩ: chi phí phát sinh ngoài định mức / thủ thuật
        per_proc = defaultdict(float)
        for u in usages.filtered(lambda u: u.kind == 'extra'):
            per_proc[u.procedure_id] += u.cost
        by_doc = defaultdict(list)
        for proc in procs:
            by_doc[proc.doctor_id].append(per_proc.get(proc, 0.0))
        for doctor, values in by_doc.items():
            others = [v for d, vals in by_doc.items() if d != doctor for v in vals]
            if not doctor or len(values) < 6 or len(others) < 6:
                continue
            sd = fm.stdev(others) or max(fm.mean(others), 10000.0)
            z = (fm.mean(values) - fm.mean(others)) / (sd / math.sqrt(len(values)))
            total = sum(values)
            if z < self.Z_STAFF or total < 300000:
                continue
            ids = usages.filtered(lambda u, d=doctor: u.kind == 'extra' and u.doctor_id == d).ids
            out.append({
                'kind': 'stock_usage', 'fingerprint': 'stock_doc:%s:%s' % (doctor.id, self.today.isocalendar()[:2]),
                'name': 'Vật tư phát sinh ngoài định mức cao – %s' % doctor.name, 'practitioner_id': doctor.id,
                'user_id': doctor.user_id.id, 'subject': doctor.name, 'score': round(z, 2),
                'severity': 'high' if z >= 6 and total >= 2000000 else 'medium' if z >= 4 or total >= 1000000
                else 'low', 'amount': total,
                'period_from': self.today - timedelta(days=days), 'period_to': self.today,
                'observed': 'Bình quân %s/thủ thuật vật tư ngoài định mức (tổng %s, %s thủ thuật)' % (
                    vnd(fm.mean(values)), vnd(total), len(values)),
                'norm': 'Bác sĩ khác: %s/thủ thuật' % vnd(fm.mean(others)),
                'explanation': 'Kiểm định z trên chi phí vật tư phát sinh mỗi thủ thuật: z = %s.' % _dec(z),
                'evidence': {'mean_doctor': fm.mean(values), 'mean_others': fm.mean(others), 'z': round(z, 2)},
                'res_model': 'dmag.material.usage', 'res_ids': ids,
            })
        return out
