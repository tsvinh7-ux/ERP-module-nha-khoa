"""Trợ lý AI cho bác sĩ (AI-01 … AI-06) – dịch vụ cho giao diện Bàn làm việc bác sĩ.

Mọi lời gọi AI đi qua cổng chung ``dmag.ai.run`` (dmag_ai_core):
* chế độ **Giả lập**: hàm ``simulate`` dựng kết quả từ DỮ LIỆU THẬT của lượt khám / bệnh nhân (không gọi AI);
* chế độ **Claude API**: hướng dẫn tiếng Việt + ``schema`` (structured outputs) / công cụ ``strict``.

Nguyên tắc: AI chỉ trả BẢN NHÁP. Không phương thức nào ở đây tự ký bệnh án, tự phát hành đơn hay tự tạo kế hoạch;
chỉ ``ai01_apply`` / ``ai02_add_diagnosis`` ghi vào bệnh án – và chỉ khi bác sĩ bấm chấp nhận trên giao diện.
"""
import base64
import io
import json
import logging
import re

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools import file_open

from odoo.addons.dmag_dental_base.models.dmag_access import is_director

from . import rx_safety
from .res_company import FPT_DEFAULT_ENDPOINT, VIETTEL_DEFAULT_ENDPOINT

_logger = logging.getLogger(__name__)

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None

DOCTOR_GROUP = 'dmag_dental_base.group_dmag_doctor'
CLINICAL_FEATURES = ('AI-01', 'AI-02', 'AI-03', 'AI-04', 'AI-05', 'AI-06')
XRAY_SAMPLES_JSON = 'dmag_ai_clinical/static/img/xray_samples.json'
SAMPLE_TAG = 'dmag_ai_sample:'
MAX_IMAGE_SIDE = 1568

# Các mục bệnh án AI-01 điền được (khóa đúng như EmrPanel / save_record_from_workspace)
AI01_FIELDS = [
    ('chief_complaint', 'Lý do khám / triệu chứng (S)', 'text'),
    ('present_illness', 'Quá trình bệnh lý (bệnh sử)', 'text'),
    ('personal_history', 'Tiền sử bản thân', 'text'),
    ('family_history', 'Tiền sử gia đình', 'text'),
    ('pulse', 'Mạch (lần/phút)', 'int'),
    ('temperature', 'Nhiệt độ (°C)', 'float'),
    ('bp_systolic', 'Huyết áp tâm thu (mmHg)', 'int'),
    ('bp_diastolic', 'Huyết áp tâm trương (mmHg)', 'int'),
    ('respiratory_rate', 'Nhịp thở (lần/phút)', 'int'),
    ('weight', 'Cân nặng (kg)', 'float'),
    ('height', 'Chiều cao (cm)', 'float'),
    ('exam_extraoral', 'Khám ngoài mặt', 'text'),
    ('exam_intraoral', 'Khám trong miệng', 'text'),
    ('exam_occlusion', 'Khớp cắn', 'text'),
    ('exam_soft_tissue', 'Mô mềm', 'text'),
    ('exam_periodontal', 'Nha chu', 'text'),
    ('paraclinical_summary', 'Tóm tắt cận lâm sàng (X-quang, xét nghiệm)', 'text'),
    ('examination', 'Khám lâm sàng (O) – tóm tắt', 'text'),
    ('assessment', 'Chẩn đoán / đánh giá (A)', 'text'),
    ('treatment_direction', 'Hướng điều trị', 'text'),
    ('treatment_note', 'Xử trí / thủ thuật đã làm (P)', 'text'),
    ('advice', 'Lời dặn bệnh nhân', 'text'),
]
AI01_KEYS = [f[0] for f in AI01_FIELDS]

# Từ khóa (đã bỏ dấu) → mã ICD-10 – dùng cho chế độ giả lập; luôn lọc lại theo danh mục dmag.dental.diagnosis
ICD_KEYWORDS = [
    (('sau ngung tien trien',), 'K02.3'),
    (('sau men',), 'K02.0'),
    (('sau nga', 'lo sau', 'sau rang', 'sau mat'), 'K02.1'),
    (('sau co ho tuy', 'ho tuy'), 'K02.5'),
    (('hoai tu tuy',), 'K04.1'),
    (('viem tuy',), 'K04.0'),
    (('ap xe',), 'K04.7'),
    (('viem quanh cuong cap',), 'K04.4'),
    (('viem quanh cuong', 'ton thuong quanh chop'), 'K04.5'),
    (('viem loi cap',), 'K05.0'),
    (('viem loi',), 'K05.1'),
    (('viem quanh rang', 'viem nha chu', 'tieu xuong'), 'K05.3'),
    (('cao rang',), 'K03.6'),
    (('mon rang', 'mon co rang'), 'K03.1'),
    (('tut loi',), 'K06.0'),
    (('mat rang',), 'K08.1'),
    (('chan rang sot',), 'K08.3'),
    (('rang ngam', 'moc lech', 'rang khon'), 'K01.1'),
    (('khop thai duong',), 'K07.6'),
    (('ap to', 'loet mieng'), 'K12.0'),
]

# Câu đọc mẫu theo tình trạng trên sơ đồ răng (giả lập AI-01)
DICTATION_BY_CONDITION = {
    'caries': 'răng {t} lỗ sâu mặt {s}, thăm có ngà mềm, thử lạnh ê buốt hết ngay khi bỏ kích thích',
    'pulpitis': 'răng {t} đau tự nhiên về đêm, thử lạnh đau kéo dài, gõ dọc đau nhẹ',
    'periapical': 'răng {t} gõ dọc đau, ngách lợi tương ứng hơi nề',
    'fracture': 'răng {t} có đường nứt thân răng, cắn đau khi nhai',
    'calculus': 'cao răng độ hai vùng {t}',
    'mobility': 'răng {t} lung lay độ một',
    'residual_root': 'răng {t} còn chân răng sót',
    'impacted': 'răng {t} mọc lệch, lợi trùm phía xa',
    'missing': 'mất răng {t}',
    'filling': 'răng {t} có miếng trám cũ còn tốt',
    'root_canal': 'răng {t} đã điều trị tủy',
    'crown': 'răng {t} có mão phục hình',
    'implant': 'răng {t} là implant',
}

SURFACE_WORDS = {'O': 'nhai', 'I': 'cắn', 'M': 'gần', 'D': 'xa', 'B': 'ngoài', 'F': 'ngoài', 'L': 'trong',
                 'P': 'trong'}

# Dịch vụ gợi ý theo tình trạng (giả lập AI-05): (cơ bản, tối ưu) – mỗi bên là danh sách "khóa dịch vụ"
PLAN_RULES = {
    'caries': (['filling'], ['filling']),
    'pulpitis': (['endo', 'filling'], ['endo', 'crown_premium']),
    'periapical': (['endo', 'filling'], ['endo', 'crown_premium']),
    'fracture': (['crown_basic'], ['crown_premium']),
    'calculus': (['scaling'], ['scaling']),
    'mobility': (['scaling'], ['scaling']),
    'residual_root': (['extract'], ['extract']),
    'impacted': (['extract'], ['extract']),
    'missing': (['bridge'], ['implant']),
}
SERVICE_FINDERS = {
    'filling': (('restorative',), ('trám', 'composite')),
    'endo': (('endo',), ('tủy',)),
    'crown_premium': (('prosthodontic',), ('zirconia', 'toàn sứ', 'cercon')),
    'crown_basic': (('prosthodontic',), ('kim loại', 'titan')),
    'bridge': (('prosthodontic',), ('kim loại', 'cầu')),
    'implant': (('implant',), ('implant',)),
    'extract': (('surgery',), ('nhổ',)),
    'scaling': (('hygiene',), ('cạo vôi', 'lấy cao')),
    'xray': (('imaging',), ('panorama', 'phim', 'x-quang')),
}
PHASE_BY_SERVICE = {'scaling': 1, 'extract': 1, 'endo': 1, 'xray': 1, 'filling': 2, 'crown_premium': 3,
                    'crown_basic': 3, 'bridge': 3, 'implant': 3}


def _num(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


class DmagAiClinical(models.AbstractModel):
    _name = 'dmag.ai.clinical'
    _description = 'Trợ lý AI cho bác sĩ'

    # ================================================================== chung
    @api.model
    def _is_doctor(self):
        return self.env.su or self.env.user.has_group(DOCTOR_GROUP)

    @api.model
    def _check_doctor(self):
        if not self._is_doctor():
            raise AccessError(_('Chỉ bác sĩ mới dùng được trợ lý AI lâm sàng.'))

    @api.model
    def _get_visit(self, visit_id):
        self._check_doctor()
        visit = self.env['dmag.dental.visit'].browse(int(visit_id or 0)).exists()
        if not visit:
            raise UserError(_('Không tìm thấy lượt khám.'))
        visit.check_access_rights('read')
        visit.check_access_rule('read')
        return visit

    @api.model
    def _feature(self, code):
        return self.env['dmag.ai.feature'].sudo().with_context(active_test=False).search([('code', '=', code)], limit=1)

    @api.model
    def _consent_block(self, code, patient):
        """Trả dict cho giao diện khi bệnh nhân chưa đồng ý AI (thay vì để cổng AI báo lỗi)."""
        feature = self._feature(code)
        company = self.env.company
        if (feature.sends_patient_data and patient and company.dmag_ai_require_consent
                and not patient.sudo().dmag_ai_consent):
            return {
                'consent_required': True,
                'patient_id': patient.id,
                'patient_name': patient.name,
                'can_consent': self._is_doctor(),
                'message': _('Bệnh nhân %s chưa đồng ý cho phép hỗ trợ bằng AI (NĐ 13/2023). Hỏi ý kiến bệnh nhân; '
                             'nếu đồng ý, bấm "Bệnh nhân đồng ý" để ghi nhận (có thời điểm).', patient.name),
            }
        return None

    @api.model
    def _run(self, code, system, user, visit, schema=None, tools=None, tool_handlers=None, simulate=None,
             max_tokens=8000):
        res = self.env['dmag.ai'].run(code, system, user, schema=schema, tools=tools, tool_handlers=tool_handlers,
                                      simulate=simulate, record=visit, patient=visit.patient_id,
                                      max_tokens=max_tokens)
        if schema and not isinstance(res.get('data'), dict):
            raise UserError(_('AI trả kết quả không đúng định dạng – vui lòng thử lại hoặc nhập thủ công.'))
        return res

    @staticmethod
    def _meta(res):
        return {k: res.get(k) for k in ('mode', 'simulated', 'model', 'cost_vnd', 'estimated_cost_vnd', 'log_id',
                                         'feature')}

    @api.model
    def get_status(self, visit_id=False):
        """Trạng thái AI cho giao diện bác sĩ: chế độ, tính năng bật/tắt, nguồn giọng nói, đồng ý của bệnh nhân."""
        company = self.env.company
        Feature = self.env['dmag.ai.feature'].sudo().with_context(active_test=False)
        features = {f.code: bool(f.active) for f in Feature.search([('code', 'in', CLINICAL_FEATURES)])}
        status = {
            'mode': company.dmag_ai_mode,
            'is_doctor': self._is_doctor(),
            'is_director': is_director(self.env),
            'features': {code: features.get(code, False) for code in CLINICAL_FEATURES},
            'stt_provider': company.dmag_stt_provider or 'simulate',
            'stt_ready': {'fpt': company.dmag_stt_fpt_key_set, 'viettel': company.dmag_stt_viettel_key_set,
                          'browser': True, 'simulate': True},
            'require_consent': company.dmag_ai_require_consent,
            'consent': True,
        }
        if visit_id:
            visit = self.env['dmag.dental.visit'].browse(int(visit_id)).exists()
            if visit:
                status['consent'] = not company.dmag_ai_require_consent or bool(visit.patient_id.sudo().dmag_ai_consent)
                status['patient_id'] = visit.patient_id.id
        return status

    @api.model
    def record_consent(self, patient_id):
        """Bác sĩ ghi nhận bệnh nhân đồng ý hỗ trợ bằng AI (một chạm, có thời điểm, ghi chatter)."""
        self._check_doctor()
        patient = self.env['res.partner'].browse(int(patient_id)).exists()
        if not patient or not patient.is_patient:
            raise UserError(_('Không tìm thấy bệnh nhân.'))
        patient.check_access_rights('read')
        patient.check_access_rule('read')
        patient.sudo().write({'dmag_ai_consent': True, 'dmag_ai_consent_date': fields.Datetime.now()})
        patient.sudo().message_post(body=_(
            'Bệnh nhân đồng ý cho phép hỗ trợ bằng AI (dữ liệu được ẩn danh trước khi gửi). Ghi nhận bởi %s.',
            self.env.user.name))
        return {'consent': True, 'date': fields.Datetime.to_string(patient.sudo().dmag_ai_consent_date)}

    # ------------------------------------------------------------------ dữ liệu dùng chung
    @api.model
    def _diagnosis_catalog(self):
        return self.env['dmag.dental.diagnosis'].search([])

    @api.model
    def _chart(self, patient):
        entries = self.env['dmag.dental.chart.entry'].search([('patient_id', '=', patient.id)],
                                                             order='date asc, id asc')
        return [{
            'id': e.id, 'tooth': e.tooth_id.code, 'tooth_name': e.tooth_id.name or '',
            'surfaces': e.surface_ids.mapped('code'), 'condition': e.condition_id.name,
            'condition_code': e.condition_id.code, 'category': e.condition_id.category, 'layer': e.layer,
            'diagnosis_code': e.diagnosis_id.code or '', 'diagnosis_id': e.diagnosis_id.id,
            'visit_id': e.visit_id.id,
        } for e in entries]

    @api.model
    def _gender_text(self, patient):
        return {'male': 'nam', 'female': 'nữ'}.get(patient.gender or '', '')

    @api.model
    def _patient_brief(self, visit):
        """Hồ sơ tóm tắt (văn bản) gửi kèm lời gọi AI – cổng AI sẽ ẩn danh họ tên, SĐT, CCCD…"""
        p = visit.patient_id.sudo()
        alerts = ', '.join(p.patient_alert_ids.mapped('name')) or 'không'
        lines = [
            f'Bệnh nhân: {p.name}, {self._gender_text(p)} {p.age or "?"} tuổi.',
            f'Cảnh báo y khoa: {alerts}. Dị ứng: {p.allergy or "chưa ghi nhận"}.',
            f'Tiền sử toàn thân: {p.medical_history or "không ghi"}. Thuốc đang dùng: {p.current_medication or "không"}.',
            f'Đang mang thai: {"có" if p.is_pregnant else "không"}.',
            f'Lý do đến khám (lễ tân ghi): {visit.reason or "không ghi"}.',
        ]
        return '\n'.join(lines)

    @api.model
    def _chart_text(self, chart):
        if not chart:
            return 'Sơ đồ răng: chưa có ghi nhận.'
        rows = []
        for e in chart:
            surf = f" mặt {''.join(e['surfaces'])}" if e['surfaces'] else ''
            diag = f" (ICD {e['diagnosis_code']})" if e['diagnosis_code'] else ''
            rows.append(f"- R{e['tooth']}{surf}: {e['condition']} [{e['category']}/{e['layer']}]{diag}")
        return 'Sơ đồ răng hiện tại:\n' + '\n'.join(rows)

    @api.model
    def _plain_tooth(self, code):
        tooth = self.env['dmag.dental.tooth'].search([('code', '=', str(code))], limit=1)
        return (tooth.name or f'răng {code}').lower()

    # ================================================================== AI-01 ghi bệnh án bằng giọng nói
    @api.model
    def ai01_sample_transcript(self, visit_id):
        """Bản đọc mẫu (giả lập) dựng từ dữ liệu thật của lượt khám: tuổi, giới, lý do, sơ đồ răng, dị ứng."""
        visit = self._get_visit(visit_id)
        return {'text': self._sample_transcript(visit), 'provider': 'simulate'}

    @api.model
    def _sample_transcript(self, visit):
        p = visit.patient_id.sudo()
        chart = [e for e in self._chart(p) if e['layer'] == 'existing']
        findings = [e for e in chart if e['category'] in ('finding', 'missing')]
        reason = (visit.reason or visit.chief_complaint or 'khám răng định kỳ').rstrip('.').lower()
        gender = self._gender_text(p) or 'bệnh nhân'
        parts = [f'Bệnh nhân {gender} {p.age or ""} tuổi, đến khám vì {reason}, khoảng hai tuần nay.'.replace('  ', ' ')]
        if p.allergy:
            parts.append(f'Tiền sử dị ứng {p.allergy.lower().replace("dị ứng ", "")}.')
        if p.medical_history:
            parts.append(f'Tiền sử toàn thân {p.medical_history.rstrip(".").lower()}.')
        elif not p.allergy:
            parts.append('Tiền sử bản thân khỏe mạnh, chưa ghi nhận dị ứng thuốc.')
        if p.current_medication:
            parts.append(f'Đang dùng {p.current_medication.rstrip(".").lower()}.')
        bp = '135 trên 85' if p.patient_alert_ids.filtered(lambda a: 'huyết áp' in (a.name or '').lower()) else '120 trên 75'
        parts.append(f'Mạch 80, huyết áp {bp}, nhiệt độ 36 độ 8.')
        parts.append('Khám ngoài mặt: mặt cân đối, không sưng nề, hạch dưới hàm không sờ thấy, há miệng bình thường.')
        intra = []
        for e in findings[:6]:
            tpl = DICTATION_BY_CONDITION.get(e['condition_code'])
            if tpl:
                surf = ' '.join(SURFACE_WORDS.get(c, c) for c in e['surfaces']) or 'nhai'
                intra.append(tpl.format(t=e['tooth'], s=surf))
        if not intra:
            intra = ['cao răng độ một hai hàm', 'lợi viêm nhẹ vùng răng cửa dưới, chảy máu khi thăm']
        parts.append('Khám trong miệng: ' + '; '.join(intra) + '.')
        parts.append('Khớp cắn loại một. Niêm mạc má, lưỡi, sàn miệng bình thường.')
        parts.append('Nha chu: cao răng độ một, lợi viêm nhẹ, túi lợi dưới 3 mi li mét.')
        codes = {e['condition_code'] for e in findings}
        dx = []
        teeth_caries = [e['tooth'] for e in findings if e['condition_code'] == 'caries']
        if teeth_caries:
            dx.append('sâu ngà răng ' + ', '.join(teeth_caries))
        if codes & {'pulpitis'}:
            dx.append('viêm tủy răng ' + ', '.join(e['tooth'] for e in findings if e['condition_code'] == 'pulpitis'))
        if codes & {'periapical'}:
            dx.append('viêm quanh cuống răng ' + ', '.join(e['tooth'] for e in findings
                                                            if e['condition_code'] == 'periapical'))
        if codes & {'missing'}:
            dx.append('mất răng ' + ', '.join(e['tooth'] for e in findings if e['condition_code'] == 'missing'))
        if codes & {'impacted'}:
            dx.append('răng khôn mọc lệch ' + ', '.join(e['tooth'] for e in findings if e['condition_code'] == 'impacted'))
        if not dx:
            dx = ['viêm lợi mạn do cao răng']
        parts.append('Chẩn đoán: ' + '; '.join(dx) + '.')
        plan = []
        if teeth_caries:
            plan.append('trám composite răng ' + ', '.join(teeth_caries))
        if codes & {'pulpitis', 'periapical'}:
            plan.append('điều trị tủy')
        if codes & {'missing'}:
            plan.append('tư vấn phục hình răng mất')
        if codes & {'impacted'}:
            plan.append('chụp phim, hẹn nhổ răng khôn')
        if not plan:
            plan.append('cạo vôi đánh bóng hai hàm')
        parts.append('Hướng điều trị: ' + ', '.join(plan) + '.')
        parts.append('Dặn bệnh nhân chải răng hai lần mỗi ngày với kem chống ê buốt, tránh đồ quá lạnh, '
                     'tái khám sau một tuần.')
        return ' '.join(parts)

    @api.model
    def _extract_fields(self, transcript):
        """Giả lập "AI điền mẫu": tách lời đọc thành các mục 16/BV1 bằng quy tắc từ khóa."""
        text = (transcript or '').strip()
        out = {k: '' for k in AI01_KEYS}
        for k, _l, kind in AI01_FIELDS:
            if kind != 'text':
                out[k] = 0
        if not text:
            return out
        low = rx_safety.norm(text)
        m = re.search(r'mach\s*(\d{2,3})', low)
        if m:
            out['pulse'] = int(m.group(1))
        m = re.search(r'huyet ap\s*(\d{2,3})\s*(?:tren|/)\s*(\d{2,3})', low)
        if m:
            out['bp_systolic'], out['bp_diastolic'] = int(m.group(1)), int(m.group(2))
        m = re.search(r'nhiet do\s*(\d{2})(?:\s*(?:do|,|\.)\s*(\d))?', low)
        if m:
            out['temperature'] = float(f"{m.group(1)}.{m.group(2) or 0}")
        m = re.search(r'nhip tho\s*(\d{1,2})', low)
        if m:
            out['respiratory_rate'] = int(m.group(1))
        m = re.search(r'can nang\s*(\d{1,3}(?:[.,]\d)?)', low)
        if m:
            out['weight'] = float(m.group(1).replace(',', '.'))
        m = re.search(r'chieu cao\s*(\d{2,3})', low)
        if m:
            out['height'] = float(m.group(1))
        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+|\n+', text) if s.strip()]
        routes = [
            ('chief_complaint', ('den kham vi', 'ly do', 'than phien', 'kham vi')),
            ('family_history', ('tien su gia dinh', 'gia dinh co', 'trong gia dinh')),
            ('personal_history', ('tien su', 'di ung', 'dang dung', 'dang uong')),
            ('exam_extraoral', ('ngoai mat', 'ngoai mieng', 'hach')),
            ('exam_occlusion', ('khop can',)),
            ('exam_soft_tissue', ('niem mac', 'mo mem', 'luoi', 'san mieng')),
            ('exam_periodontal', ('nha chu', 'tui loi', 'cao rang do')),
            ('paraclinical_summary', ('x quang', 'x-quang', 'phim', 'xet nghiem')),
            ('assessment', ('chan doan',)),
            ('treatment_direction', ('huong dieu tri', 'ke hoach', 'du kien')),
            ('treatment_note', ('da lam', 'tien hanh', 'gay te', 'da tram', 'da cao voi')),
            ('advice', ('dan ', 'dan benh nhan', 'tai kham')),
            ('exam_intraoral', ('trong mieng', 'rang ', 'lo sau', 'mat rang')),
        ]
        skip_vitals = ('mach ', 'huyet ap', 'nhiet do', 'nhip tho', 'can nang', 'chieu cao')
        for sentence in sentences:
            s_low = rx_safety.norm(sentence)
            if any(v in s_low for v in skip_vitals) and len(re.findall(r'\d', s_low)) >= 4:
                continue
            for key, words in routes:
                if any(w in s_low for w in words):
                    clean = re.sub(r'^(Khám ngoài mặt|Khám trong miệng|Nha chu|Chẩn đoán|Hướng điều trị|Tiền sử)\s*:\s*',
                                   '', sentence, flags=re.I)
                    clean = clean[0].upper() + clean[1:] if clean else clean
                    if key == 'chief_complaint':
                        m = re.search(r'(?:đến khám vì|khám vì|lý do)\s+(.*)', sentence, flags=re.I)
                        reason = m.group(1) if m else sentence
                        pieces = [x.strip() for x in reason.split(',')]
                        out['chief_complaint'] = pieces[0][0].upper() + pieces[0][1:].rstrip('.') + '.'
                        if len(pieces) > 1:
                            illness = ', '.join(pieces).rstrip('.')
                            out['present_illness'] = (out['present_illness'] + ' ' + illness[0].upper()
                                                      + illness[1:] + '.').strip()
                        break
                    out[key] = (out[key] + ' ' + clean).strip()
                    break
        intra = out['exam_intraoral']
        extra = out['exam_extraoral']
        out['examination'] = ' '.join(x for x in (extra, intra, out['exam_periodontal']) if x)[:600]
        return out

    @api.model
    def _icd_from_text(self, text, catalog=None):
        catalog = catalog if catalog is not None else self._diagnosis_catalog()
        by_code = {d.code: d for d in catalog}
        low = rx_safety.norm(text)
        found = []
        for words, code in ICD_KEYWORDS:
            if code in by_code and code not in [c for c, _r in found]:
                hit = next((w for w in words if w in low), None)
                if hit:
                    found.append((code, _('Lời đọc có "%s"', hit)))
        # "sâu ngà" và "sâu men" cùng lúc → chỉ giữ K02.1
        codes = [c for c, _r in found]
        if 'K02.1' in codes and 'K02.0' in codes:
            found = [f for f in found if f[0] != 'K02.0']
        return found

    @api.model
    def _ai01_schema(self, codes):
        props = {}
        for key, label, kind in AI01_FIELDS:
            if kind == 'text':
                props[key] = {'type': 'string', 'description': f'{label} – chuỗi rỗng nếu lời đọc không nhắc tới'}
            else:
                props[key] = {'type': 'number', 'description': f'{label} – 0 nếu không nhắc tới'}
        code_schema = {'type': 'string', 'enum': codes} if codes else {'type': 'string'}
        return {
            'type': 'object', 'additionalProperties': False, 'required': ['fields', 'icd10', 'notes'],
            'properties': {
                'fields': {'type': 'object', 'additionalProperties': False, 'required': AI01_KEYS,
                           'properties': props},
                'icd10': {'type': 'array', 'description': 'Mã ICD-10 gợi ý – CHỈ chọn trong danh mục cho sẵn',
                          'items': {'type': 'object', 'additionalProperties': False, 'required': ['code', 'reason'],
                                    'properties': {'code': code_schema, 'reason': {'type': 'string'}}}},
                'notes': {'type': 'string', 'description': 'Điểm chưa rõ / cần bác sĩ kiểm tra lại'},
            },
        }

    @api.model
    def ai01_structure(self, visit_id, transcript):
        """Lời đọc → các mục bệnh án 16/BV1 (BẢN NHÁP so sánh từng mục; chưa ghi gì vào bệnh án)."""
        visit = self._get_visit(visit_id)
        transcript = (transcript or '').strip()
        if len(transcript) < 10:
            raise UserError(_('Chưa có nội dung lời đọc để điền bệnh án.'))
        consent = self._consent_block('AI-01', visit.patient_id)
        if consent:
            return consent
        catalog = self._diagnosis_catalog()
        codes = catalog.mapped('code')
        current = self._ai01_current(visit)
        system = (
            'Bạn là trợ lý ghi bệnh án ngoại trú Răng Hàm Mặt (mẫu 16/BV1, Bộ Y tế). Nhận lời đọc của bác sĩ '
            '(đã chuyển giọng nói thành chữ, có thể sai chính tả, thiếu dấu câu) và điền vào đúng các mục. '
            'Quy tắc: chỉ dùng thông tin có trong lời đọc; không suy diễn, không thêm chẩn đoán; mục không được '
            'nhắc tới để chuỗi rỗng, số đo không được nhắc tới để 0. Viết câu ngắn, thuật ngữ nha khoa chuẩn, số răng '
            'theo FDI ("răng 36"). Mục "Khám lâm sàng (O)" là tóm tắt ngắn phần khám. Mã ICD-10 chỉ được chọn trong '
            'danh mục phòng khám cho sẵn; nếu không có mã phù hợp thì để trống danh sách.')
        user = (
            f'{self._patient_brief(visit)}\n\n'
            f'Bệnh án hiện tại (JSON): {json.dumps(current, ensure_ascii=False)}\n\n'
            f'Danh mục ICD-10 của phòng khám: {", ".join(f"{d.code} {d.name}" for d in catalog)}\n\n'
            f'Lời đọc của bác sĩ:\n"""{transcript}"""')

        def simulate():
            fields_out = self._extract_fields(transcript)
            for key, _label, kind in AI01_FIELDS:
                cur, new = current.get(key), fields_out.get(key)
                if kind != 'text' or not cur or not new:
                    continue
                words = {w for w in re.findall(r'\w{5,}', rx_safety.norm(new))}
                if words <= set(re.findall(r'\w{5,}', rx_safety.norm(cur))):
                    fields_out[key] = cur  # không có gì mới
                else:
                    fields_out[key] = f'{cur.rstrip()}\n{new}'  # bổ sung, giữ nội dung cũ
            icd = [{'code': c, 'reason': r} for c, r in self._icd_from_text(transcript, catalog)]
            return {'text': 'Đã tách lời đọc thành các mục bệnh án (giả lập theo quy tắc từ khóa).',
                    'data': {'fields': fields_out, 'icd10': icd,
                             'notes': 'Giả lập: tách câu theo từ khóa – bác sĩ kiểm tra từng mục trước khi chấp nhận.'}}

        res = self._run('AI-01', system, user, visit, schema=self._ai01_schema(codes), simulate=simulate)
        data = res['data']
        suggested = data.get('fields') or {}
        rows = []
        for key, label, kind in AI01_FIELDS:
            value = suggested.get(key)
            if kind == 'text':
                value = (value or '').strip()
                if not value:
                    continue
            else:
                value = _num(value)
                if not value:
                    continue
                value = int(round(value)) if kind == 'int' else round(value, 1)
            cur = current.get(key)
            changed = (cur or '') != value if kind == 'text' else _num(cur) != _num(value)
            if not changed:
                continue
            rows.append({'key': key, 'label': label, 'kind': kind, 'current': cur or ('' if kind == 'text' else 0),
                         'suggested': value, 'accept': True})
        existing = set(visit.diagnosis_ids.mapped('code'))
        by_code = {d.code: d for d in catalog}
        icd = []
        for item in data.get('icd10') or []:
            diag = by_code.get((item.get('code') or '').strip())
            if diag and diag.code not in [i['code'] for i in icd]:  # chỉ mã có trong danh mục
                icd.append({'id': diag.id, 'code': diag.code, 'name': diag.name, 'reason': item.get('reason') or '',
                            'already': diag.code in existing, 'accept': diag.code not in existing})
        return dict(self._meta(res), rows=rows, icd=icd, notes=data.get('notes') or '', transcript=transcript)

    @api.model
    def _ai01_current(self, visit):
        cur = {}
        for key, _label, kind in AI01_FIELDS:
            value = visit[key]
            cur[key] = (value or '') if kind == 'text' else (value or 0)
        return cur

    @api.model
    def ai01_apply(self, visit_id, values, diagnosis_ids=None, log_id=False):
        """Ghi các mục bác sĩ đã CHẤP NHẬN qua đường lưu sẵn có (save_record_from_workspace)."""
        visit = self._get_visit(visit_id)
        if visit.record_state == 'signed':
            raise UserError(_('Bệnh án đã ký – không ghi được nội dung AI gợi ý.'))
        specs = {k: kind for k, _l, kind in AI01_FIELDS}
        vals = {}
        for key, value in (values or {}).items():
            kind = specs.get(key)
            if not kind:
                continue
            if kind == 'text':
                vals[key] = (value or '').strip()
            elif kind == 'int':
                vals[key] = int(round(_num(value)))
            else:
                vals[key] = round(_num(value), 1)
        diag_ids = self.env['dmag.dental.diagnosis'].browse([int(i) for i in diagnosis_ids or []]).exists().ids
        if diag_ids:
            vals['diagnosis_ids'] = list(dict.fromkeys(visit.diagnosis_ids.ids + diag_ids))
        if not vals:
            return {'applied': []}
        visit.save_record_from_workspace(vals)
        labels = [label for key, label, _k in AI01_FIELDS if key in vals]
        if diag_ids:
            labels.append(_('ICD-10: %s', ', '.join(self.env['dmag.dental.diagnosis'].browse(diag_ids).mapped('code'))))
        visit.message_post(body=_(
            'Bệnh án có hỗ trợ AI (AI-01 – ghi bệnh án bằng giọng nói). Bác sĩ %(user)s đã xem và chấp nhận các mục: '
            '%(items)s.%(log)s', user=self.env.user.name, items='; '.join(labels),
            log=(_(' Nhật ký AI #%s.', log_id) if log_id else '')))
        return {'applied': list(vals)}

    @api.model
    def stt_transcribe(self, visit_id, provider, audio, mimetype='audio/webm'):
        """Nhận dạng giọng nói qua nhà cung cấp trong nước (FPT.AI / Viettel AI) hoặc giả lập.

        ``audio``: bytes âm thanh do trình duyệt ghi (MediaRecorder). Trả ``{'text', 'provider'}``.
        """
        visit = self._get_visit(visit_id)
        company = self.env.company.sudo()
        if provider == 'simulate':
            return {'text': self._sample_transcript(visit), 'provider': 'simulate'}
        if provider not in ('fpt', 'viettel'):
            raise UserError(_('Nguồn nhận dạng giọng nói không hợp lệ.'))
        consent = self._consent_block('AI-01', visit.patient_id)
        if consent:
            raise UserError(consent['message'])
        if not audio:
            raise UserError(_('Không nhận được âm thanh.'))
        if requests is None:
            raise UserError(_('Máy chủ thiếu thư viện "requests".'))
        audio, mimetype = self._maybe_convert_wav(audio, mimetype)
        try:
            if provider == 'fpt':
                key = company.dmag_stt_fpt_api_key
                if not key:
                    raise UserError(_('Chưa nhập khóa API FPT.AI (Cấu hình → Trợ lý AI → Cài đặt AI).'))
                resp = requests.post(company.dmag_stt_fpt_endpoint or FPT_DEFAULT_ENDPOINT, data=audio,
                                     headers={'api-key': key, 'Content-Type': mimetype}, timeout=90)
            else:
                token = company.dmag_stt_viettel_token
                if not token:
                    raise UserError(_('Chưa nhập token Viettel AI (Cấu hình → Trợ lý AI → Cài đặt AI).'))
                ext = 'wav' if 'wav' in mimetype else 'webm'
                resp = requests.post(company.dmag_stt_viettel_endpoint or VIETTEL_DEFAULT_ENDPOINT,
                                     headers={'token': token}, data={'token': token},
                                     files={'file': (f'ghi_am.{ext}', audio, mimetype)}, timeout=90)
        except requests.RequestException as e:
            raise UserError(_('Không kết nối được dịch vụ nhận dạng giọng nói: %s', e)) from e
        if resp.status_code >= 400:
            raise UserError(_('Dịch vụ nhận dạng giọng nói báo lỗi %(code)s: %(body)s', code=resp.status_code,
                              body=resp.text[:300]))
        try:
            payload = resp.json()
        except ValueError:
            payload = resp.text
        text = self._find_transcript(payload)
        if not text:
            raise UserError(_('Dịch vụ không trả về nội dung nhận dạng (kiểm tra định dạng âm thanh / địa chỉ API).'))
        return {'text': text, 'provider': provider}

    @api.model
    def _maybe_convert_wav(self, audio, mimetype):
        """Trình duyệt ghi WebM/Opus; nếu máy chủ có ffmpeg thì đổi sang WAV 16 kHz mono cho tương thích."""
        if 'wav' in (mimetype or ''):
            return audio, mimetype
        import shutil
        import subprocess
        ffmpeg = shutil.which('ffmpeg')
        if not ffmpeg:
            return audio, mimetype
        try:
            proc = subprocess.run([ffmpeg, '-hide_banner', '-loglevel', 'error', '-i', 'pipe:0', '-ac', '1', '-ar',
                                   '16000', '-f', 'wav', 'pipe:1'], input=audio, capture_output=True, timeout=60,
                                  check=True)
            return proc.stdout, 'audio/wav'
        except Exception as e:  # giữ nguyên âm thanh gốc
            _logger.info('DMAG STT: không đổi được sang WAV: %s', e)
            return audio, mimetype

    @api.model
    def _find_transcript(self, payload):
        """Lấy câu nhận dạng từ JSON trả về (cấu trúc khác nhau giữa nhà cung cấp)."""
        if isinstance(payload, str):
            return payload.strip()
        found = []

        def walk(obj):
            if isinstance(obj, dict):
                for key in ('utterance', 'transcript', 'text', 'result_text'):
                    if isinstance(obj.get(key), str) and obj[key].strip():
                        found.append(obj[key].strip())
                        return
                for value in obj.values():
                    walk(value)
            elif isinstance(obj, list):
                for value in obj[:1] if obj and isinstance(obj[0], dict) and 'utterance' in obj[0] else obj:
                    walk(value)
        walk(payload)
        return ' '.join(found).strip()

    # ================================================================== AI-02 kiểm tra trước khi ký
    @api.model
    def _ai02_local(self, visit, chart):
        """Kiểm tra cố định (không AI): mục bắt buộc + nhất quán sơ đồ răng ↔ ICD-10 ↔ nội dung."""
        issues = []

        def add(severity, field, message):
            issues.append({'severity': severity, 'field': field, 'message': message, 'source': 'rule'})

        for item in visit._emr_missing_for_signature():
            add('high', 'legal', _('Thiếu mục bắt buộc: %s', item))
        visit_codes = set(visit.diagnosis_ids.mapped('code'))
        findings = [e for e in chart if e['category'] == 'finding' and e['layer'] == 'existing']
        record_text = rx_safety.norm(' '.join(filter(None, [
            visit.examination, visit.exam_intraoral, visit.assessment, visit.chief_complaint, visit.present_illness])))
        for e in findings:
            if e['diagnosis_code'] and e['diagnosis_code'] not in visit_codes:
                add('medium', 'diagnosis_ids',
                    _('R%(t)s "%(c)s" ghi trên sơ đồ răng nhưng bệnh án chưa có mã ICD-10 tương ứng (%(code)s).',
                      t=e['tooth'], c=e['condition'], code=e['diagnosis_code']))
            if record_text and e['tooth'] not in record_text:
                add('low', 'exam_intraoral', _('R%(t)s (%(c)s) có trên sơ đồ nhưng phần khám chưa mô tả răng này.',
                                               t=e['tooth'], c=e['condition']))
        chart_codes = {e['diagnosis_code'] for e in chart if e['diagnosis_code']}
        mapped = set(self.env['dmag.dental.condition'].search([]).mapped('diagnosis_id.code'))
        for diag in visit.diagnosis_ids:
            if chart and diag.code in mapped and diag.code not in chart_codes:
                add('low', 'diagnosis_ids', _('Mã %(code)s (%(name)s) chưa có ghi nhận tương ứng trên sơ đồ răng.',
                                              code=diag.code, name=diag.name))
        if visit.diagnosis_ids and not (visit.assessment or '').strip():
            add('low', 'assessment', _('Đã chọn mã ICD-10 nhưng chưa ghi mô tả chẩn đoán (A).'))
        patient = visit.patient_id.sudo()
        if patient.allergy and rx_safety.norm(patient.allergy)[:8] not in rx_safety.norm(visit.personal_history or ''):
            add('medium', 'personal_history', _('Hồ sơ có dị ứng "%s" nhưng mục Tiền sử bản thân chưa ghi.', patient.allergy))
        if visit.bp_systolic >= 160 or visit.bp_diastolic >= 100:
            add('medium', 'bp_systolic', _('Huyết áp %(s)s/%(d)s mmHg – cân nhắc trước thủ thuật / thuốc tê có '
                                           'adrenalin, ghi rõ xử trí.', s=visit.bp_systolic, d=visit.bp_diastolic))
        if not (visit.pulse or visit.bp_systolic):
            add('low', 'pulse', _('Chưa ghi sinh hiệu (mạch, huyết áp) – mục IV.1 mẫu 16/BV1.'))
        if visit.procedure_ids and not (visit.treatment_note or '').strip():
            add('medium', 'treatment_note', _('Đã ghi nhận thủ thuật trong lượt nhưng chưa ghi phần Xử trí (P).'))
        return issues

    @api.model
    def ai02_check(self, visit_id):
        """Kiểm tra bệnh án trước khi ký: quy tắc cố định + AI đối chiếu + gợi ý ICD-10 (chỉ trong danh mục)."""
        visit = self._get_visit(visit_id)
        chart = self._chart(visit.patient_id)
        local = self._ai02_local(visit, chart)
        result = {'local': local, 'ai': None, 'icd': [], 'consent': None}
        consent = self._consent_block('AI-02', visit.patient_id)
        if consent:
            result['consent'] = consent
            return result
        catalog = self._diagnosis_catalog()
        codes = catalog.mapped('code')
        record = {k: visit[k] or '' for k in ('chief_complaint', 'present_illness', 'personal_history',
                                               'exam_extraoral', 'exam_intraoral', 'exam_periodontal', 'examination',
                                               'assessment', 'treatment_direction', 'treatment_note', 'advice')}
        record['icd10'] = [f'{d.code} {d.name}' for d in visit.diagnosis_ids]
        system = (
            'Bạn kiểm tra chất lượng bệnh án ngoại trú Răng Hàm Mặt trước khi bác sĩ ký. Đối chiếu: (1) mô tả '
            'triệu chứng / khám ↔ chẩn đoán ↔ mã ICD-10; (2) bệnh án ↔ sơ đồ răng (răng, tình trạng); (3) mâu thuẫn '
            'hoặc thiếu sót lâm sàng quan trọng. Không lặp lại các lỗi đã liệt kê trong "Kiểm tra cố định". Mức độ: '
            'high = sai/mâu thuẫn cần sửa, medium = nên bổ sung, low = gợi ý. Mã ICD-10 CHỈ chọn trong danh mục phòng '
            'khám – dùng công cụ lookup_icd10 nếu cần tra; tuyệt đối không tự tạo mã. Bác sĩ là người quyết định.')
        user = (f'{self._patient_brief(visit)}\n\nBệnh án (JSON): {json.dumps(record, ensure_ascii=False)}\n\n'
                f'{self._chart_text(chart)}\n\nKiểm tra cố định đã phát hiện:\n'
                + ('\n'.join('- ' + i['message'] for i in local) or '- (không có)')
                + f'\n\nDanh mục ICD-10 của phòng khám: {", ".join(f"{d.code} {d.name}" for d in catalog)}')
        schema = {
            'type': 'object', 'additionalProperties': False, 'required': ['summary', 'issues', 'icd10'],
            'properties': {
                'summary': {'type': 'string'},
                'issues': {'type': 'array', 'items': {
                    'type': 'object', 'additionalProperties': False, 'required': ['severity', 'field', 'message'],
                    'properties': {'severity': {'type': 'string', 'enum': ['high', 'medium', 'low']},
                                   'field': {'type': 'string'}, 'message': {'type': 'string'}}}},
                'icd10': {'type': 'array', 'items': {
                    'type': 'object', 'additionalProperties': False, 'required': ['code', 'reason'],
                    'properties': {'code': {'type': 'string', 'enum': codes} if codes else {'type': 'string'},
                                   'reason': {'type': 'string'}}}},
            },
        }
        tools = [{
            'name': 'lookup_icd10',
            'description': 'Tra danh mục ICD-10 RĂNG HÀM MẶT của phòng khám theo từ khóa tiếng Việt hoặc mã. '
                           'Chỉ các mã trả về từ công cụ này mới hợp lệ.',
            'strict': True,
            'input_schema': {'type': 'object', 'additionalProperties': False, 'required': ['query'],
                             'properties': {'query': {'type': 'string', 'description': 'Từ khóa, ví dụ "sâu ngà"'}}},
        }]

        def lookup(inp):
            q = rx_safety.norm(inp.get('query'))
            hits = [d for d in catalog if q and (q in rx_safety.norm(d.name) or q in d.code.lower())]
            return {'results': [{'code': d.code, 'name': d.name} for d in hits[:15]]}

        def simulate():
            issues = []
            text = ' '.join(record[k] for k in record if isinstance(record[k], str))
            suggested = self._icd_from_text(text, catalog)
            have = set(visit.diagnosis_ids.mapped('code'))
            for code, _reason in suggested:
                if code not in have:
                    diag = catalog.filtered(lambda d: d.code == code)
                    issues.append({'severity': 'medium', 'field': 'diagnosis_ids',
                                   'message': _('Nội dung bệnh án mô tả "%(name)s" nhưng chưa chọn mã %(code)s.',
                                                name=diag.name, code=code)})
            text_codes = {c for c, _r in suggested}
            for diag in visit.diagnosis_ids:
                if text and diag.code not in text_codes and diag.code[:3] not in {c[:3] for c in text_codes}:
                    issues.append({'severity': 'low', 'field': 'assessment',
                                   'message': _('Mã %(code)s (%(name)s) chưa được mô tả trong phần khám / chẩn đoán.',
                                                code=diag.code, name=diag.name)})
            patient = visit.patient_id.sudo()
            anesthetic_allergy = 'thuoc te' in rx_safety.patient_profile(patient)['allergy'] or any(
                w in rx_safety.norm(patient.allergy) for w in rx_safety.FAMILIES['local_anesthetic']['allergy'])
            plan_text = rx_safety.norm(' '.join([record['treatment_direction'], record['treatment_note']]))
            if anesthetic_allergy and any(w in plan_text for w in ('tram', 'tuy', 'nho', 'gay te', 'implant', 'phau')) \
                    and not any(w in plan_text for w in ('articain', 'mepivacain', 'thuoc te thay', 'khong gay te')):
                issues.append({'severity': 'high', 'field': 'treatment_direction',
                               'message': _('Bệnh nhân dị ứng thuốc tê (%s) nhưng hướng điều trị có thủ thuật cần gây tê – '
                                            'ghi rõ thuốc tê thay thế / biện pháp phòng phản vệ.', patient.allergy or _('cảnh báo y khoa'))})
            if len(visit.diagnosis_ids) >= 2 and not visit.primary_diagnosis_id:
                issues.append({'severity': 'low', 'field': 'primary_diagnosis_id',
                               'message': _('Có %(n)s mã ICD-10 nhưng chưa chọn bệnh chính – nên chọn %(code)s (liên quan lý do '
                                            'khám); nếu không, hệ thống lấy mã đầu tiên khi ký.', n=len(visit.diagnosis_ids),
                                            code=visit.diagnosis_ids[:1].code)})
            if record['treatment_direction'] and not visit.procedure_ids and not self.env['dmag.treatment.plan'].search_count(
                    [('patient_id', '=', patient.id), ('state', '!=', 'cancel')]):
                issues.append({'severity': 'low', 'field': 'treatment_direction',
                               'message': _('Đã nêu hướng điều trị nhưng chưa lập kế hoạch điều trị / chưa ghi thủ thuật – '
                                            'có thể dùng "AI gợi ý kế hoạch" (AI-05).')})
            if 'dau' in rx_safety.norm(record['chief_complaint']) and not record['exam_intraoral']:
                issues.append({'severity': 'medium', 'field': 'exam_intraoral',
                               'message': _('Lý do khám có đau nhưng chưa mô tả răng nguyên nhân khi khám trong miệng.')})
            icd = [{'code': c, 'reason': r} for c, r in suggested if c not in have]
            for e in chart:
                if (e['category'] == 'finding' and e['layer'] == 'existing' and e['diagnosis_code']
                        and e['diagnosis_code'] not in have and e['diagnosis_code'] not in [i['code'] for i in icd]):
                    icd.append({'code': e['diagnosis_code'],
                                'reason': _('Sơ đồ răng: R%(t)s %(c)s', t=e['tooth'], c=e['condition'])})
            n = len(local) + len(issues)
            summary = (_('Bệnh án nhất quán, có thể ký.') if not n else
                       _('Có %s điểm cần xem lại trước khi ký (bác sĩ vẫn có thể ký).', n))
            trace = [{'tool': 'lookup_icd10', 'input': {'query': 'sâu'}, 'output': lookup({'query': 'sâu'}),
                      'error': False}]
            return {'text': summary, 'data': {'summary': summary, 'issues': issues, 'icd10': icd}, 'tool_trace': trace}

        res = self._run('AI-02', system, user, visit, schema=schema, tools=tools,
                        tool_handlers={'lookup_icd10': lookup}, simulate=simulate)
        data = res['data']
        by_code = {d.code: d for d in catalog}
        have = set(visit.diagnosis_ids.mapped('code'))
        icd = []
        for item in data.get('icd10') or []:
            diag = by_code.get((item.get('code') or '').strip())
            if diag and diag.code not in have and diag.code not in [i['code'] for i in icd]:
                icd.append({'id': diag.id, 'code': diag.code, 'name': diag.name, 'reason': item.get('reason') or ''})
        result['ai'] = dict(self._meta(res), summary=data.get('summary') or '',
                            issues=[dict(i, source='ai') for i in data.get('issues') or []],
                            tools=len(res.get('tool_trace') or []))
        result['icd'] = icd
        return result

    @api.model
    def ai02_add_diagnosis(self, visit_id, diagnosis_id):
        """Bác sĩ bấm "Thêm" mã ICD-10 AI gợi ý – chỉ mã thuộc danh mục."""
        visit = self._get_visit(visit_id)
        diag = self.env['dmag.dental.diagnosis'].browse(int(diagnosis_id)).exists()
        if not diag:
            raise UserError(_('Mã ICD-10 không có trong danh mục.'))
        visit.save_record_from_workspace({'diagnosis_ids': list(dict.fromkeys(visit.diagnosis_ids.ids + [diag.id]))})
        visit.message_post(body=_('Thêm chẩn đoán %(code)s theo gợi ý AI (AI-02), bác sĩ %(user)s duyệt.',
                                  code=diag.display_name, user=self.env.user.name))
        return True

    # ================================================================== AI-03 an toàn đơn thuốc
    @api.model
    def rx_check(self, visit_id, lines, weight=0.0, prescription_id=False):
        """Quy tắc cố định (không AI) – chạy kể cả khi AI tắt. Kèm trạng thái duyệt vượt của Giám đốc (nếu có đơn)."""
        visit = self._get_visit(visit_id)
        max_days = self.env['dmag.dental.visit'].get_rx_catalog().get('max_days') or 30
        findings = rx_safety.check_lines(self.env, visit.patient_id, lines, max_days=max_days, weight=_num(weight))
        blocks = [f for f in findings if f['level'] == 'block']
        res = {
            'findings': findings,
            'blocks': len(blocks),
            'warns': sum(1 for f in findings if f['level'] == 'warn'),
            'ok': not blocks,
            'is_director': is_director(self.env),
            'override': False, 'override_valid': False, 'override_requested': False,
            'patient': visit.patient_id.name or '', 'doctor': visit.doctor_id.name or '',
        }
        rx = self._get_rx(visit, prescription_id) if prescription_id else None
        if rx:
            Rx = self.env['dmag.prescription']
            res['override'] = rx._rx_override_dict()
            res['override_requested'] = bool(rx.rx_override_requested_at)
            res['override_valid'] = bool(blocks and rx.rx_safety_override
                                         and rx.rx_override_codes == Rx._rx_block_signature(blocks))
        return res

    @api.model
    def _get_rx(self, visit, prescription_id):
        rx = self.env['dmag.prescription'].browse(int(prescription_id or 0)).exists()
        if not rx or rx.visit_id != visit:
            raise UserError(_('Đơn thuốc không thuộc lượt khám này.'))
        return rx

    @api.model
    def rx_request_override(self, visit_id, prescription_id, note=''):
        """Bác sĩ: "Đề nghị Giám đốc duyệt vượt" (tạo việc cần làm cho Giám đốc)."""
        visit = self._get_visit(visit_id)
        return self._get_rx(visit, prescription_id).action_request_override(note)

    @api.model
    def rx_override(self, visit_id, prescription_id, reason, confirm=False, issue=True):
        """Giám đốc: "Duyệt vượt & ký chịu trách nhiệm" – lý do bắt buộc, ghi vết, ký số bổ sung (nếu có)."""
        visit = self._get_visit(visit_id)
        rx = self._get_rx(visit, prescription_id)
        res = rx.action_director_override(reason, confirm=confirm, issue=False)
        if issue:
            errors = rx._get_issue_errors()
            if errors:
                # duyệt vượt đã lưu; đơn còn thiếu thông tin TT 26 → bác sĩ bổ sung rồi phát hành
                res.update(issued=False, issue_errors=errors)
                return res
            res.update(visit.issue_prescription(rx.id))
            res['issued'] = True
        return res

    @api.model
    def ai03_explain(self, visit_id, lines, weight=0.0):
        """AI giải thích các cảnh báo bằng lời dễ hiểu (không thay đổi kết quả quy tắc)."""
        visit = self._get_visit(visit_id)
        check = self.rx_check(visit_id, lines, weight)
        consent = self._consent_block('AI-03', visit.patient_id)
        if consent:
            return dict(check, consent=consent)
        drugs = self.env['dmag.drug'].sudo().browse([int(l.get('drug_id') or 0) for l in lines or []]).exists()
        catalog = self.env['dmag.dental.visit'].get_rx_catalog()['drugs']
        system = (
            'Bạn là dược sĩ lâm sàng hỗ trợ bác sĩ RHM. Hệ thống quy tắc cố định đã kiểm tra đơn thuốc; nhiệm vụ của '
            'bạn là GIẢI THÍCH các cảnh báo bằng tiếng Việt dễ hiểu (3–6 câu ngắn, gạch đầu dòng), nêu nguy cơ cụ thể '
            'và gợi ý thay thế CHỈ từ danh mục thuốc của phòng khám. Không đổi mức chặn/cảnh báo, không kê đơn thay '
            'bác sĩ. Nếu không có cảnh báo, xác nhận ngắn gọn các điểm cần dặn bệnh nhân.')
        user = (f'{self._patient_brief(visit)}\n\nĐơn đang kê:\n'
                + '\n'.join(f"- {d.name}: {l.get('dose_per_time')} x {l.get('times_per_day')} lần/ngày x {l.get('days')} ngày"
                            for d, l in zip(drugs, lines or []))
                + '\n\nKết quả quy tắc cố định:\n'
                + ('\n'.join(f"- [{f['level']}] {f['title']}: {f['message']}" for f in check['findings']) or '- không có')
                + '\n\nDanh mục thuốc phòng khám: ' + ', '.join(d['name'] for d in catalog))

        def simulate():
            names = {rx_safety.norm(d['name']): d['name'] for d in catalog}

            def pick(*words):
                for key, name in names.items():
                    if any(w in key for w in words):
                        return name
                return None
            bullets = []
            for f in check['findings']:
                if f['code'] == 'allergy':
                    alt = pick('clindamycin') if 'penicillin' in rx_safety.norm(f['message']) else None
                    bullets.append(_('• %(drug)s: bệnh nhân từng dị ứng nên có thể nổi mề đay, phù môi – mặt, khó thở, '
                                     'nặng nhất là sốc phản vệ. Bỏ thuốc này khỏi đơn%(alt)s.', drug=f['drug'],
                                     alt=(_('; có thể thay bằng %s (bác sĩ quyết định)', alt) if alt else '')))
                elif f['code'] in ('nsaid_anticoagulant', 'duplicate_nsaid'):
                    alt = pick('paracetamol')
                    bullets.append(_('• %(drug)s: thuốc giảm đau – kháng viêm loại này làm máu khó đông hơn, dễ chảy máu '
                                     'kéo dài sau thủ thuật%(alt)s.', drug=f['drug'],
                                     alt=(_('; ưu tiên %s để giảm đau', alt) if alt else '')))
                elif f['code'] == 'duplicate':
                    bullets.append(_('• %(drug)s: chứa cùng hoạt chất với một thuốc khác trong đơn – uống cả hai là gấp đôi '
                                     'liều, dễ tiêu chảy, nổi mẩn. Chỉ giữ một thuốc.', drug=f['drug']))
                elif f['code'].startswith('pregnancy'):
                    bullets.append(_('• %(drug)s: %(msg)s Nên dặn bệnh nhân báo bác sĩ sản khoa đang theo dõi.',
                                     drug=f['drug'], msg=f['message']))
                elif f['code'].startswith('child'):
                    bullets.append(_('• %(drug)s: trẻ nhỏ cần tính liều theo cân nặng; hướng dẫn phụ huynh dùng dụng cụ '
                                     'đo liều kèm theo, không tự tăng liều.', drug=f['drug']))
                else:
                    bullets.append('• %s: %s' % (f['drug'] or f['title'], f['message']))
            if not bullets:
                bullets.append(_('• Không phát hiện dị ứng, trùng thuốc hay tương tác cần chặn theo dữ liệu hiện có.'))
                bullets.append(_('• Dặn bệnh nhân uống thuốc đúng giờ, kháng sinh dùng đủ số ngày; ngừng thuốc và quay '
                                 'lại ngay nếu nổi mẩn, khó thở.'))
            text = '\n'.join(bullets)
            return {'text': text}

        res = self.env['dmag.ai'].run('AI-03', system, user, record=visit, patient=visit.patient_id,
                                      simulate=simulate, max_tokens=2000)
        return dict(check, explanation=res.get('text') or '', meta=self._meta(res))

    # ================================================================== AI-04 tóm tắt hồ sơ 30 giây
    @api.model
    def _ai04_facts(self, visit):
        p = visit.patient_id.sudo()
        Visit = self.env['dmag.dental.visit']
        history = Visit.search([('patient_id', '=', p.id), ('id', '!=', visit.id), ('state', '=', 'done')],
                               order='scheduled_start desc', limit=5)
        plans = self.env['dmag.treatment.plan'].search([('patient_id', '=', p.id),
                                                        ('state', 'in', ('draft', 'presented', 'accepted', 'in_progress'))])
        plan_rows = []
        for plan in plans:
            option = plan.accepted_option_id or plan.option_ids.filtered('is_recommended')[:1] or plan.option_ids[:1]
            todo = option.line_ids.filtered(lambda l: l.state == 'todo')
            plan_rows.append({
                'name': plan.name, 'title': plan.title or '', 'state': dict(plan._fields['state'].selection).get(plan.state),
                'raw_state': plan.state, 'progress': round(plan.progress or 0),
                'todo': [f"{l.product_id.name}{(' R' + ', '.join(l.tooth_ids.mapped('code'))) if l.tooth_ids else ''}"
                         for l in todo][:5],
                'amount': option.amount_total,
            })
        balance = 0.0
        if 'account.move' in self.env:
            moves = self.env['account.move'].sudo().search([
                ('partner_id', 'child_of', p.commercial_partner_id.id), ('move_type', '=', 'out_invoice'),
                ('state', '=', 'posted'), ('payment_state', 'in', ('not_paid', 'partial'))])
            balance = sum(moves.mapped('amount_residual'))
        balance += sum(Visit.search([('patient_id', '=', p.id), ('state', '=', 'done')]).filtered(
            lambda v: v.payment_status == 'to_invoice').mapped('amount_due'))
        last = history[:1]
        return {
            'name': p.name, 'age': p.age, 'gender': self._gender_text(p),
            'alerts': p.patient_alert_ids.mapped('name'), 'allergy': p.allergy or '',
            'medical_history': p.medical_history or '', 'dental_history': p.dental_history or '',
            'medication': p.current_medication or '', 'pregnant': bool(p.is_pregnant),
            'visits': [{'date': fields.Date.to_string(fields.Datetime.context_timestamp(self, v.scheduled_start).date()),
                        'doctor': v.doctor_id.name or '', 'assessment': v.assessment or '',
                        'procedures': v.procedure_ids.mapped('product_id.name'),
                        'pain': v.pain_score, 'advice': v.advice or ''} for v in history],
            'plans': plan_rows, 'balance': balance,
            'care_note': (p.comment and re.sub(r'<[^>]+>', ' ', p.comment).strip()) or '',
            'last_advice': last.advice or '', 'reason': visit.reason or '',
            'new_patient': visit.is_new_patient, 'consent_ai': bool(p.dmag_ai_consent),
        }

    @api.model
    def ai04_summary(self, visit_id):
        visit = self._get_visit(visit_id)
        consent = self._consent_block('AI-04', visit.patient_id)
        if consent:
            return consent
        facts = self._ai04_facts(visit)
        money = lambda v: '{:,.0f} đ'.format(v or 0).replace(',', '.')
        system = (
            'Bạn tóm tắt hồ sơ bệnh nhân nha khoa để bác sĩ đọc trong 30 giây trước khi khám. Ngắn, đúng trọng tâm, '
            'ưu tiên an toàn (dị ứng, bệnh nền, thuốc chống đông, thai kỳ) lên đầu. Mỗi ý ≤ 20 từ. Chỉ dùng dữ kiện '
            'được cung cấp; thiếu thì ghi "chưa có dữ liệu".')
        user = (f'Lý do khám hôm nay: {facts["reason"] or "không ghi"}\n'
                f'Dữ kiện hồ sơ (JSON): {json.dumps(facts, ensure_ascii=False, default=str)}')
        sections = ['safety', 'history', 'visits', 'plan', 'balance', 'care']
        schema = {
            'type': 'object', 'additionalProperties': False, 'required': ['headline', 'sections', 'talking_points'],
            'properties': {
                'headline': {'type': 'string', 'description': 'Một câu nắm nhanh bệnh nhân'},
                'sections': {'type': 'array', 'items': {
                    'type': 'object', 'additionalProperties': False, 'required': ['key', 'title', 'items'],
                    'properties': {'key': {'type': 'string', 'enum': sections}, 'title': {'type': 'string'},
                                   'items': {'type': 'array', 'items': {'type': 'string'}}}}},
                'talking_points': {'type': 'array', 'items': {'type': 'string'},
                                   'description': 'Tối đa 3 việc bác sĩ nên hỏi / làm hôm nay'},
            },
        }

        def simulate():
            f = facts
            safety = []
            if f['allergy']:
                allergy = re.sub(r'^\s*dị ứng\s*:?\s*', '', f['allergy'], flags=re.I)
                safety.append(f"Dị ứng: {allergy}")
            for a in f['alerts']:
                if not f['allergy'] or 'dị ứng' not in a.lower():
                    safety.append(f'Cảnh báo: {a}')
            if f['medication']:
                safety.append(f"Đang dùng thuốc: {f['medication']}")
            if f['pregnant']:
                safety.append('Đang mang thai – thận trọng thuốc, phim X-quang')
            if not safety:
                safety.append('Chưa ghi nhận dị ứng / bệnh nền đặc biệt')
            history = [x for x in (f['medical_history'] and f"Toàn thân: {f['medical_history']}",
                                   f['dental_history'] and f"Răng miệng: {f['dental_history']}") if x] \
                or ['Chưa có dữ liệu tiền sử chi tiết']
            visits = [f"{v['date']} · {v['assessment'] or 'không ghi chẩn đoán'}"
                      + (f" · {', '.join(v['procedures'][:2])}" if v['procedures'] else '')
                      + (f" · đau sau thủ thuật {v['pain']}/10" if v['pain'] else '') for v in f['visits'][:3]] \
                or ['Lần khám đầu tiên tại phòng khám']
            plans = [f"{pl['name']} {pl['title']} – {pl['state']}"
                     + (f", tiến độ {pl['progress']}%" if pl['raw_state'] in ('accepted', 'in_progress') else '')
                     + (f"; còn: {', '.join(pl['todo'][:3])}" if pl['todo'] else '') for pl in f['plans']] \
                or ['Không có kế hoạch điều trị đang dở']
            balance = [f"Còn nợ {money(f['balance'])}" if f['balance'] > 0 else 'Không có công nợ']
            care = [x for x in (f['care_note'], f['last_advice'] and f"Lời dặn lần trước: {f['last_advice']}") if x] \
                or ['Chưa có ghi chú chăm sóc']
            talking = []
            if f['allergy'] or f['alerts']:
                talking.append('Xác nhận lại dị ứng / bệnh nền trước khi gây tê, kê đơn')
            pending = [pl for pl in f['plans'] if pl['raw_state'] in ('draft', 'presented')]
            if pending:
                talking.append(f"Hỏi quyết định kế hoạch {pending[0]['name']} ({money(pending[0]['amount'])})")
            doing = [pl for pl in f['plans'] if pl['todo'] and pl['raw_state'] in ('accepted', 'in_progress')]
            if doing:
                talking.append(f"Tiếp tục: {doing[0]['todo'][0]}")
            if f['balance'] > 0:
                talking.append('Nhắc lễ tân về công nợ còn lại')
            if f['reason']:
                talking.insert(0, f"Hôm nay: {f['reason']}")
            age = f"{f['age']} tuổi" if f['age'] else ''
            head = (f"{f['gender'].capitalize()} {age}".strip() + (', khách mới' if f['new_patient'] else
                                                                     f", đã khám {len(f['visits'])} lần gần đây")
                    + (f"; ⚠ {safety[0]}" if (f['allergy'] or f['alerts']) else '') + '.')
            data = {'headline': head, 'talking_points': talking[:3], 'sections': [
                {'key': 'safety', 'title': 'An toàn', 'items': safety},
                {'key': 'history', 'title': 'Tiền sử', 'items': history},
                {'key': 'visits', 'title': 'Lần khám gần nhất', 'items': visits},
                {'key': 'plan', 'title': 'Kế hoạch đang dở', 'items': plans},
                {'key': 'balance', 'title': 'Công nợ', 'items': balance},
                {'key': 'care', 'title': 'Ghi chú chăm sóc', 'items': care},
            ]}
            return {'text': head, 'data': data}

        res = self._run('AI-04', system, user, visit, schema=schema, simulate=simulate, max_tokens=3000)
        data = res['data']
        return dict(self._meta(res), headline=data.get('headline') or '', sections=data.get('sections') or [],
                    talking_points=data.get('talking_points') or [], balance=facts['balance'])

    # ================================================================== AI-05 gợi ý kế hoạch điều trị
    @api.model
    def _service_catalog(self):
        products = self.env['product.product'].search([('is_dental_service', '=', True)])
        return products

    @api.model
    def _find_service(self, products, key):
        cats, words = SERVICE_FINDERS[key]
        for product in products:
            name = (product.name or '').lower()
            if (product.dental_category in cats or not cats) and any(w in name for w in words):
                return product
        for product in products:
            if product.dental_category in cats:
                return product
        return self.env['product.product']

    @api.model
    def _neighbours(self, code):
        q, p = int(code[0]), int(code[1])
        return [f'{q}{n}' for n in (p - 1, p + 1) if 1 <= n <= 7]

    @api.model
    def ai05_suggest(self, visit_id):
        visit = self._get_visit(visit_id)
        consent = self._consent_block('AI-05', visit.patient_id)
        if consent:
            return consent
        chart = self._chart(visit.patient_id)
        findings = [e for e in chart if e['layer'] == 'existing' and e['category'] in ('finding', 'missing')
                    and e['condition_code'] != 'unerupted']
        if not findings:
            raise UserError(_('Sơ đồ răng chưa có bệnh lý / răng mất để gợi ý kế hoạch. Ghi nhận trên sơ đồ trước.'))
        products = self._service_catalog()
        if not products:
            raise UserError(_('Chưa có danh mục dịch vụ nha khoa.'))
        missing_teeth = {e['tooth'] for e in chart if e['condition_code'] == 'missing'}
        catalog_rows = [{'id': p.id, 'name': p.name, 'price': p.lst_price, 'category': p.dental_category or '',
                         'per_tooth': bool(p.dental_requires_tooth)} for p in products]
        system = (
            'Bạn là bác sĩ RHM giàu kinh nghiệm hỗ trợ lập kế hoạch điều trị. Từ các bệnh lý / răng mất trên sơ đồ răng, '
            'đề xuất ĐÚNG 2 phương án: "basic" (cơ bản – chi phí hợp lý, xử lý bệnh lý cần thiết) và "optimal" (tối ưu '
            '– bền, thẩm mỹ, chức năng tốt nhất). Chỉ dùng dịch vụ trong danh mục (product_id), dịch vụ tính theo răng '
            'phải ghi răng FDI. Sắp xếp theo giai đoạn (phase): 1 = xử lý cấp / nhiễm trùng / vệ sinh, 2 = phục hồi, '
            '3 = phục hình. Không chỉ định quá mức cần thiết. Thêm bản giải thích cho bệnh nhân KHÔNG dùng thuật ngữ, '
            'không hứa hẹn kết quả, không nhắc giá.')
        user = (f'{self._patient_brief(visit)}\n\n{self._chart_text(chart)}\n\n'
                f'Danh mục dịch vụ (JSON): {json.dumps(catalog_rows, ensure_ascii=False)}')
        line_schema = {'type': 'object', 'additionalProperties': False,
                       'required': ['product_id', 'teeth', 'phase', 'reason'],
                       'properties': {'product_id': {'type': 'integer', 'enum': products.ids},
                                      'teeth': {'type': 'array', 'items': {'type': 'string'}},
                                      'phase': {'type': 'integer'}, 'reason': {'type': 'string'}}}
        schema = {
            'type': 'object', 'additionalProperties': False,
            'required': ['options', 'sequence_note', 'patient_explanation'],
            'properties': {
                'options': {'type': 'array', 'items': {
                    'type': 'object', 'additionalProperties': False,
                    'required': ['tier', 'name', 'summary', 'visits', 'lines'],
                    'properties': {'tier': {'type': 'string', 'enum': ['basic', 'optimal']},
                                   'name': {'type': 'string'}, 'summary': {'type': 'string'},
                                   'visits': {'type': 'integer'},
                                   'lines': {'type': 'array', 'items': line_schema}}}},
                'sequence_note': {'type': 'string'},
                'patient_explanation': {'type': 'string'},
            },
        }

        def simulate():
            tiers = {'basic': [], 'optimal': []}
            explain = []
            for e in findings:
                rule = PLAN_RULES.get(e['condition_code'])
                if not rule:
                    continue
                for tier, keys in zip(('basic', 'optimal'), rule):
                    for key in keys:
                        product = self._find_service(products, key)
                        if not product:
                            continue
                        teeth = [e['tooth']]
                        if key == 'bridge':
                            neigh = [n for n in self._neighbours(e['tooth']) if n not in missing_teeth]
                            if len(neigh) < 2:
                                continue
                            teeth = sorted(neigh + [e['tooth']])
                        if not product.dental_requires_tooth:
                            teeth = []
                        reason = {
                            'filling': _('Lấy sạch mô sâu, trám kín lỗ sâu R%s', e['tooth']),
                            'endo': _('Điều trị tủy R%s', e['tooth']),
                            'crown_premium': _('Bọc sứ toàn sứ bảo vệ răng R%s', e['tooth']),
                            'crown_basic': _('Bọc sứ kim loại R%s', e['tooth']),
                            'bridge': _('Cầu răng 3 đơn vị thay R%s', e['tooth']),
                            'implant': _('Cấy implant thay răng mất R%s', e['tooth']),
                            'extract': _('Nhổ R%s', e['tooth']),
                            'scaling': _('Làm sạch cao răng hai hàm'),
                        }.get(key, product.name)
                        if any(l['product_id'] == product.id and l['teeth'] == teeth for l in tiers[tier]):
                            continue
                        if not teeth and any(l['product_id'] == product.id for l in tiers[tier]):
                            continue
                        tiers[tier].append({'product_id': product.id, 'teeth': teeth,
                                            'phase': PHASE_BY_SERVICE.get(key, 2), 'reason': reason})
                plain = self._plain_tooth(e['tooth'])
                explain.append({
                    'caries': _('%s bị sâu – cần làm sạch và trám lại để không sâu vào tủy gây đau.', plain.capitalize()),
                    'pulpitis': _('%s bị viêm tủy – cần lấy tủy để hết đau, sau đó phục hồi lại răng.', plain.capitalize()),
                    'periapical': _('%s bị viêm ở chân răng – cần làm sạch ống tủy để giữ răng.', plain.capitalize()),
                    'fracture': _('%s bị nứt – cần bọc lại để răng không vỡ thêm.', plain.capitalize()),
                    'missing': _('Chỗ %s đã mất – nên làm răng thay thế để ăn nhai tốt và các răng bên cạnh không bị '
                                 'xô lệch.', plain),
                    'impacted': _('%s mọc lệch – dễ viêm, sưng; nên nhổ khi chưa có biến chứng.', plain.capitalize()),
                    'calculus': _('Có nhiều cao răng – cần làm sạch để lợi hết viêm, chảy máu.'),
                }.get(e['condition_code'], _('%(t)s: %(c)s.', t=plain.capitalize(), c=e['condition'])))
            needs_xray = any(l['phase'] == 1 and l['teeth'] for l in tiers['optimal']) or \
                any(self.env['product.product'].browse(l['product_id']).dental_category == 'implant'
                    for l in tiers['optimal'])
            xray = self._find_service(products, 'xray') if needs_xray else self.env['product.product']
            options = []
            for tier in ('basic', 'optimal'):
                lines = sorted(tiers[tier], key=lambda l: l['phase'])
                if xray and tier == 'optimal':
                    lines.insert(0, {'product_id': xray.id, 'teeth': [], 'phase': 1,
                                     'reason': _('Chụp phim đánh giá chân răng, xương trước điều trị')})
                phases = {l['phase'] for l in lines}
                cats = [self.env['product.product'].browse(l['product_id']).dental_category for l in lines]
                extra = 2 * cats.count('implant') + (1 if 'prosthodontic' in cats else 0)
                options.append({
                    'tier': tier,
                    'name': _('Cơ bản – xử lý bệnh lý cần thiết') if tier == 'basic' else _('Tối ưu – bền & thẩm mỹ'),
                    'summary': (_('Chi phí hợp lý, giải quyết đủ các bệnh lý hiện có; phục hình bằng vật liệu tiêu '
                                  'chuẩn, có thể cần làm lại sau nhiều năm.') if tier == 'basic' else
                                _('Bảo tồn tối đa răng thật, phục hình toàn sứ / implant bền và thẩm mỹ; chi phí và số '
                                  'buổi cao hơn.')),
                    'visits': len(phases) + extra + (1 if tier == 'optimal' else 0),
                    'lines': lines,
                })
            note = _('Giai đoạn 1 xử lý viêm nhiễm / vệ sinh → giai đoạn 2 trám phục hồi → giai đoạn 3 phục hình. '
                     'Làm từng giai đoạn, tái đánh giá trước khi chuyển bước.')
            text = ' '.join(explain[:6]) + ' ' + _('Bác sĩ sẽ cùng anh/chị chọn phương án phù hợp nhất.')
            return {'text': text, 'data': {'options': options, 'sequence_note': note, 'patient_explanation': text}}

        res = self._run('AI-05', system, user, visit, schema=schema, simulate=simulate)
        data = res['data']
        teeth_codes = set(self.env['dmag.dental.tooth'].search([]).mapped('code'))
        options = []
        for opt in data.get('options') or []:
            lines = []
            total = 0.0
            for line in opt.get('lines') or []:
                product = products.filtered(lambda p: p.id == int(line.get('product_id') or 0))
                if not product:
                    continue  # chỉ dịch vụ thuộc danh mục
                teeth = [str(t) for t in line.get('teeth') or [] if str(t) in teeth_codes]
                qty = len(teeth) if product.dental_requires_tooth and teeth else 1
                subtotal = qty * product.lst_price
                total += subtotal
                lines.append({'product_id': product.id, 'product': product.name, 'teeth': teeth,
                              'phase': int(line.get('phase') or 1), 'reason': line.get('reason') or '',
                              'qty': qty, 'price': product.lst_price, 'subtotal': subtotal})
            options.append({'tier': opt.get('tier'), 'name': opt.get('name') or '', 'summary': opt.get('summary') or '',
                            'visits': int(opt.get('visits') or 0), 'lines': lines, 'total': total})
        options.sort(key=lambda o: 0 if o['tier'] == 'optimal' else 1)
        finding_map = [{'id': e['id'], 'tooth': e['tooth']} for e in findings]
        return dict(self._meta(res), options=options, sequence_note=data.get('sequence_note') or '',
                    patient_explanation=data.get('patient_explanation') or '', findings=finding_map)

    # ================================================================== AI-06 đọc phim (minh họa)
    @api.model
    def _xray_samples(self):
        with file_open(XRAY_SAMPLES_JSON, 'r') as fh:
            return json.load(fh)

    @api.model
    def ai06_images(self, visit_id):
        visit = self._get_visit(visit_id)
        Att = self.env['ir.attachment'].sudo()
        atts = Att.search(['|', '&', ('res_model', '=', 'dmag.dental.visit'), ('res_id', '=', visit.id),
                           '&', ('res_model', '=', 'res.partner'), ('res_id', '=', visit.patient_id.id),
                           ('mimetype', 'in', ('image/png', 'image/jpeg', 'image/webp'))], order='id desc', limit=20)
        samples = self._xray_samples()
        return {
            'images': [{'id': a.id, 'name': a.name, 'date': fields.Datetime.to_string(a.create_date),
                        'sample': (a.description or '').startswith(SAMPLE_TAG),
                        'url': f'/web/image/{a.id}'} for a in atts],
            'samples': [{'key': k, 'title': v['title'], 'url': f'/dmag_ai_clinical/static/img/{v["file"]}'}
                        for k, v in samples.items()],
        }

    @api.model
    def ai06_add_sample(self, visit_id, key):
        """Gắn phim mẫu tổng hợp (có sẵn trong module) vào lượt khám để demo."""
        visit = self._get_visit(visit_id)
        samples = self._xray_samples()
        if key not in samples:
            raise UserError(_('Không có phim mẫu này.'))
        with file_open(f'dmag_ai_clinical/static/img/{samples[key]["file"]}', 'rb') as fh:
            raw = fh.read()
        att = self.env['ir.attachment'].sudo().create({
            'name': _('Phim mẫu minh họa – %s.png', key.replace('xray_sample_', 'mẫu ')),
            'raw': raw, 'mimetype': 'image/png', 'res_model': 'dmag.dental.visit', 'res_id': visit.id,
            'description': SAMPLE_TAG + key,
        })
        return {'id': att.id, 'name': att.name, 'sample': True, 'url': f'/web/image/{att.id}'}

    @api.model
    def ai06_upload(self, visit_id, name, datas, mimetype):
        visit = self._get_visit(visit_id)
        if mimetype not in ('image/png', 'image/jpeg', 'image/webp'):
            raise UserError(_('Chỉ nhận ảnh PNG / JPEG / WEBP.'))
        att = self.env['ir.attachment'].sudo().create({
            'name': name or _('Phim X-quang'), 'datas': datas, 'mimetype': mimetype,
            'res_model': 'dmag.dental.visit', 'res_id': visit.id,
        })
        return {'id': att.id, 'name': att.name, 'sample': False, 'url': f'/web/image/{att.id}'}

    @api.model
    def _image_block(self, att):
        raw = att.raw or b''
        media = att.mimetype or 'image/png'
        try:
            from PIL import Image
            img = Image.open(io.BytesIO(raw))
            if max(img.size) > MAX_IMAGE_SIDE:
                img.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
                buf = io.BytesIO()
                img.convert('RGB').save(buf, format='JPEG', quality=88)
                raw, media = buf.getvalue(), 'image/jpeg'
        except Exception as e:  # ảnh không đọc được bằng PIL – gửi nguyên bản
            _logger.info('DMAG AI-06: không thu nhỏ được ảnh: %s', e)
        return {'type': 'image', 'source': {'type': 'base64', 'media_type': media,
                                            'data': base64.b64encode(raw).decode()}}

    @api.model
    def ai06_analyze(self, visit_id, attachment_id):
        visit = self._get_visit(visit_id)
        att = self.env['ir.attachment'].sudo().browse(int(attachment_id)).exists()
        if not att or not (
                (att.res_model == 'dmag.dental.visit' and att.res_id == visit.id)
                or (att.res_model == 'res.partner' and att.res_id == visit.patient_id.id)):
            raise UserError(_('Ảnh không thuộc lượt khám / bệnh nhân này.'))
        consent = self._consent_block('AI-06', visit.patient_id)
        if consent:
            return consent
        teeth = self.env['dmag.dental.tooth'].search([]).mapped('code')
        conditions = self.env['dmag.dental.condition'].search([])
        cond_codes = conditions.mapped('code') + ['other']
        system = (
            'Bạn hỗ trợ MINH HỌA việc đọc phim X-quang răng (panorama / quanh chóp). Đây KHÔNG phải thiết bị chẩn đoán '
            'được cấp phép – chỉ nêu các vùng NGHI NGỜ để bác sĩ tự đánh giá. Với mỗi phát hiện: răng FDI (phim '
            'panorama: bên trái ảnh là bên phải bệnh nhân), mô tả ngắn, mã tình trạng, độ tin cậy 0–1 (thận trọng, '
            'không phóng đại), vùng ước lượng trên ảnh (x, y, w, h theo tỉ lệ 0–1 tính từ góc trên trái). Nếu ảnh '
            'không phải phim răng hoặc chất lượng kém, nói rõ và để danh sách trống.')
        if self.env.company.dmag_ai_mode == 'simulate':
            # Giả lập: không gửi ảnh; ghi chỗ giữ chỗ (ảnh khi chạy thật ~1.600 token, không tính theo base64)
            image = {'type': 'text', 'text': f'[Ảnh phim đính kèm: {att.name} – khi chạy thật Claude nhận ảnh '
                                             f'(≤ {MAX_IMAGE_SIDE}px, khoảng 1.600 token)]'}
        else:
            image = self._image_block(att)
        user = [image,
                {'type': 'text', 'text': f'{self._patient_brief(visit)}\n\nTên ảnh: {att.name}. Hãy liệt kê các vùng '
                                         f'nghi ngờ trên phim.'}]
        schema = {
            'type': 'object', 'additionalProperties': False, 'required': ['image_quality', 'summary', 'findings'],
            'properties': {
                'image_quality': {'type': 'string'},
                'summary': {'type': 'string'},
                'findings': {'type': 'array', 'items': {
                    'type': 'object', 'additionalProperties': False,
                    'required': ['tooth', 'finding', 'condition_code', 'confidence', 'box'],
                    'properties': {
                        'tooth': {'type': 'string', 'enum': teeth} if teeth else {'type': 'string'},
                        'finding': {'type': 'string'},
                        'condition_code': {'type': 'string', 'enum': cond_codes},
                        'confidence': {'type': 'number'},
                        'box': {'type': 'object', 'additionalProperties': False, 'required': ['x', 'y', 'w', 'h'],
                                'properties': {k: {'type': 'number'} for k in ('x', 'y', 'w', 'h')}},
                    }}},
            },
        }
        sample_key = (att.description or '')[len(SAMPLE_TAG):] if (att.description or '').startswith(SAMPLE_TAG) else ''

        def simulate():
            if sample_key and sample_key in self._xray_samples():
                found = [dict(f) for f in self._xray_samples()[sample_key]['findings']]
                quality = _('Phim panorama tổng hợp (ảnh mẫu), độ tương phản đủ để minh họa.')
            else:
                # Ảnh thật của người dùng: giả lập dựa trên sơ đồ răng hiện có (không phân tích ảnh)
                found = []
                for e in self._chart(visit.patient_id):
                    if e['layer'] == 'existing' and e['category'] in ('finding', 'missing', 'existing'):
                        conf = {'finding': 0.72, 'missing': 0.9, 'existing': 0.85}[e['category']]
                        found.append({'tooth': e['tooth'], 'finding': _('%s (giả lập theo sơ đồ răng)', e['condition']),
                                      'condition_code': e['condition_code'], 'confidence': conf,
                                      'box': {'x': 0, 'y': 0, 'w': 0, 'h': 0}})
                quality = _('Giả lập: không phân tích điểm ảnh – kết quả lấy từ sơ đồ răng để minh họa luồng.')
            susp = [f for f in found if f['condition_code'] in ('caries', 'periapical', 'fracture', 'impacted',
                                                               'mobility', 'pulpitis', 'residual_root')]
            summary = (_('Nghi ngờ %(n)s vùng bệnh lý (%(t)s); %(m)s phục hồi / răng mất ghi nhận thêm. Bác sĩ đối chiếu '
                         'lâm sàng.', n=len(susp), t=', '.join('R' + f['tooth'] for f in susp) or '-',
                         m=len(found) - len(susp)))
            return {'text': summary, 'data': {'image_quality': quality, 'summary': summary, 'findings': found}}

        res = self._run('AI-06', system, user, visit, schema=schema, simulate=simulate, max_tokens=4000)
        data = res['data']
        chart_codes = {(e['tooth'], e['condition_code']) for e in self._chart(visit.patient_id) if e['layer'] == 'existing'}
        cond_by_code = {c.code: c for c in conditions}
        findings = []
        for f in data.get('findings') or []:
            tooth = str(f.get('tooth') or '')
            if tooth not in teeth:
                continue
            cond = cond_by_code.get(f.get('condition_code'))
            box = f.get('box') or {}
            box = {k: max(0.0, min(1.0, _num(box.get(k)))) for k in ('x', 'y', 'w', 'h')}
            findings.append({
                'tooth': tooth, 'finding': f.get('finding') or '', 'confidence': max(0.0, min(1.0, _num(f.get('confidence')))),
                'condition_code': f.get('condition_code') or 'other',
                'condition_id': cond.id if cond else False, 'condition': cond.name if cond else _('Khác'),
                'scope': cond.scope if cond else 'tooth', 'category': cond.category if cond else 'finding',
                'color': cond.color if cond else '#8E4EC6',
                'box': box if box['w'] > 0 and box['h'] > 0 else None,
                'on_chart': (tooth, f.get('condition_code')) in chart_codes,
                'surfaces': f.get('surfaces') or [],
            })
        return dict(self._meta(res), image={'id': att.id, 'name': att.name, 'url': f'/web/image/{att.id}'},
                    image_quality=data.get('image_quality') or '', summary=data.get('summary') or '',
                    findings=findings, sample=bool(sample_key))

    @api.model
    def ai06_add_to_chart(self, visit_id, tooth, condition_id, surfaces=None):
        """Bác sĩ chấp nhận một phát hiện → ghi lên sơ đồ răng qua đường ghi nhận sẵn có."""
        visit = self._get_visit(visit_id)
        cond = self.env['dmag.dental.condition'].browse(int(condition_id)).exists()
        if not cond:
            raise UserError(_('Tình trạng không hợp lệ.'))
        if cond.scope == 'surface' and cond.category == 'finding' and not surfaces:
            raise UserError(_('"%s" cần chọn mặt răng – chọn răng trên sơ đồ rồi ghi nhận thủ công.', cond.name))
        self.env['dmag.dental.chart.entry'].add_from_chart(visit.patient_id.id, [str(tooth)], cond.id,
                                                            surfaces=surfaces or [], visit_id=visit.id,
                                                            note=_('Theo gợi ý AI đọc phim (AI-06), bác sĩ xác nhận'))
        return True
