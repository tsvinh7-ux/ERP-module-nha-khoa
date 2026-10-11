"""Trung tâm AI – một màn hình cho mọi người dùng hiểu 20 tính năng AI-00 … AI-19 trong thực tế.

Mỗi thẻ: làm gì, nguồn AI (LOCAL / API trong nước / Claude API), trạng thái (bật/tắt, giả lập/thật), số lần dùng và chi
phí tháng này, nút "Thử ngay" mở đúng màn hình chứa tính năng (bàn làm việc bác sĩ, bảng điều phối, Zalo giả lập,
cổng bệnh nhân, bảng điều hành…), ví dụ thực tế. Lọc theo vai trò người xem.

Các màn hình của ``dmag_ai_clinical`` / ``dmag_ai_customer`` được dò mềm qua external id (module chưa cài → hiện
"Chưa cài" và mở màn hình gốc gần nhất).
"""
import calendar
from collections import defaultdict

from odoo import _, api, fields, models

from odoo.addons.dmag_dental_base.models.dmag_access import is_director, is_manager

AUDIENCES = [
    ('manager', 'Quản lý / Giám đốc', 'Bám mục tiêu, ra quyết định nhanh, chống thất thoát'),
    ('doctor', 'Bác sĩ', 'Bớt giấy tờ, thêm thời gian cho bệnh nhân'),
    ('front', 'Lễ tân · Tư vấn · CSKH', 'Nhanh hơn, không bỏ sót khách'),
    ('patient', 'Khách hàng', 'Trải nghiệm xuất sắc, hiểu và tin bác sĩ'),
    ('platform', 'Nền tảng', 'An toàn dữ liệu, kiểm soát chi phí'),
]
SOURCE_BADGES = {
    'local': ('LOCAL', 'Chạy tại phòng khám – dữ liệu không ra ngoài, không tốn phí theo lượt'),
    'api_vn': ('API trong nước', 'FPT.AI / Viettel AI – dữ liệu ở Việt Nam'),
    'api_llm': ('Claude API', 'Mô hình ngôn ngữ lớn – chỉ nhận văn bản đã ẩn danh, tính phí theo token'),
    'hybrid': ('LOCAL + Claude API', 'Quy tắc / xử lý thô tại chỗ, phần suy luận gửi Claude đã ẩn danh'),
}
DOCTOR_DESK = ('dmag_clinic_workspace.action_dmag_doctor_desk', 'Bàn làm việc bác sĩ')
FRONTDESK = ('dmag_clinic_workspace.action_dmag_frontdesk', 'Bảng điều phối')
GOALS = ('dmag_clinic_workspace.action_dmag_owner_cockpit', 'Bảng điều hành mục tiêu')

# Mỗi tính năng: (làm gì, ví dụ thực tế, lợi ích đo được, [ứng viên màn hình (xmlid, nhãn)], url cổng, phút tiết kiệm)
CATALOG = {
    'AI-00': ('Cổng gọi AI chung: ẩn danh họ tên / SĐT / CCCD trước khi gửi, nhật ký từng lần gọi (ai, khi nào, token, '
              'chi phí), trần ngân sách tháng, ghi nhận bệnh nhân đồng ý, bật/tắt từng tính năng.',
              'Bác sĩ bấm "Tóm tắt hồ sơ" cho chị Mai: Claude chỉ nhận "[BN_1], 34 tuổi, dị ứng Lidocaine…" – kết '
              'quả quay về được ghép lại tên thật. Giám đốc xem được lần gọi đó tốn bao nhiêu đồng.',
              'Không lộ dữ liệu định danh ra nước ngoài; chi phí không vượt trần',
              [('dmag_ai_core.action_dmag_ai_log', 'Nhật ký & chi phí AI'),
               ('dmag_ai_core.action_dmag_ai_feature', 'Bật / tắt tính năng')], None),
    'AI-01': ('Bác sĩ / phụ tá nói trong lúc khám, AI chép thành chữ và điền đúng mục bệnh án 16/BV1 (lý do khám, '
              'khám ngoài mặt / trong miệng, chẩn đoán, xử trí). Bác sĩ sửa rồi mới ký.',
              '"Bệnh nhân đau răng 36 ba ngày, gõ đau, lạnh kéo dài" → AI điền Lý do khám, Khám trong miệng, gợi ý '
              'K04.0 Viêm tủy – bác sĩ chỉ đọc lại và bấm Ký.',
              'Giảm 5–8 phút gõ mỗi lượt khám',
              [DOCTOR_DESK], None),
    'AI-02': ('Kiểm tra bệnh án trước khi ký: thiếu mục bắt buộc, chẩn đoán ICD-10 không khớp mô tả, mâu thuẫn với '
              'sơ đồ răng; gợi ý mã ICD-10.',
              'Bệnh án ghi "trám răng 26" nhưng sơ đồ răng đánh dấu 27 và thiếu mục Lời dặn → hệ thống chặn ký, chỉ '
              'rõ 2 lỗi cần sửa.',
              'Hồ sơ đủ chuẩn thanh tra, giảm trả hồ sơ',
              [DOCTOR_DESK], None),
    'AI-03': ('An toàn đơn thuốc: quy tắc cố định chặn dị ứng, tương tác, liều trẻ em / phụ nữ có thai / người dùng '
              'thuốc chống đông, vượt 30 ngày; AI giải thích dễ hiểu.',
              'Kê Amoxicillin cho bệnh nhân có cảnh báo "dị ứng Penicillin" → chặn ngay, đề xuất Clindamycin và giải '
              'thích lý do bằng 2 câu.',
              'An toàn người bệnh, đúng TT 26/2025',
              [DOCTOR_DESK], None),
    'AI-04': ('Tóm tắt hồ sơ 30 giây trước khi khám: tiền sử, dị ứng, lần khám gần nhất, kế hoạch đang dở, công nợ, '
              'ghi chú chăm sóc.',
              'Trước khi gọi khách vào ghế: "Nam, 52t, tăng huyết áp, đang dùng Aspirin; implant 46 đã cấy 6 tuần – '
              'hôm nay hẹn lấy dấu; còn nợ 3,5 tr".',
              'Bác sĩ nắm bệnh nhân ngay, không lật hồ sơ',
              [DOCTOR_DESK], None),
    'AI-05': ('Từ sơ đồ răng, gợi ý kế hoạch điều trị nhiều phương án (thứ tự, dịch vụ, số buổi) kèm bản giải thích '
              'không thuật ngữ cho khách. Bác sĩ chỉnh rồi duyệt.',
              'Mất 46, sâu 36: phương án A implant + trám, phương án B cầu răng sứ – mỗi phương án có giá theo bảng '
              'giá và đoạn giải thích "vì sao nên làm sớm" cho khách.',
              'Tư vấn nhanh, thống nhất giữa các bác sĩ, tăng tỷ lệ chốt',
              [DOCTOR_DESK], None),
    'AI-06': ('Hỗ trợ đọc phim X-quang: khoanh vùng nghi sâu răng, tiêu xương, tổn thương chóp – CHỈ minh họa, bác sĩ '
              'quyết định (cần sản phẩm có số lưu hành khi dùng thật).',
              'Phim cận chóp răng 46: AI khoanh vùng thấu quang quanh chóp chân xa để bác sĩ xem kỹ và giải thích cho '
              'khách bằng hình.',
              'Phát hiện sớm, hình minh họa thuyết phục khách',
              [DOCTOR_DESK], None),
    'AI-07': ('Trợ lý Zalo OA 24/7: trả lời giá, giờ mở cửa, chuẩn bị trước khi khám; xem giờ trống và đặt lịch thẳng '
              'vào Odoo; ca khẩn hoặc khách bực → chuyển người ngay. Không tư vấn chẩn đoán.',
              '22:40 khách nhắn "mai chiều còn chỗ cạo vôi không?" → trợ lý báo 14:00 / 15:30 còn trống, khách chọn '
              '15:30, lịch hiện ngay trên Bảng điều phối sáng hôm sau.',
              'Không mất khách ngoài giờ; lễ tân bớt trả lời lặp lại',
              [('dmag_ai_customer.action_dmag_ai_zalo_simulator', 'Mô phỏng Zalo OA'),
               ('dmag_ai_customer.action_dmag_ai_inbox', 'Hộp thư trợ lý Zalo'), FRONTDESK], None),
    'AI-08': ('Dự báo khách không đến (no-show) học trên lịch sử của chính phòng khám: đánh dấu lịch hẹn rủi ro cao '
              'để gọi xác nhận hoặc xếp bù.',
              'Lịch 14:00 thứ Bảy của khách mới, đặt qua Zalo, từng bỏ hẹn 1 lần → rủi ro 62 %: lễ tân gọi xác nhận '
              'và chuẩn bị khách dự phòng.',
              'Tăng công suất ghế, nhất là buổi chiều',
              [FRONTDESK, ('dmag_ai_customer.action_dmag_ai_noshow_model', 'Mô hình dự báo không đến')], None),
    'AI-09': ('Đọc phản hồi và khiếu nại (NPS, bình luận, tin nhắn): phân loại chủ đề, mức độ nghiêm trọng, cảm xúc; '
              'gợi ý cách xử lý; cảnh báo khách có nguy cơ rời bỏ.',
              '"Chờ 40 phút mà không ai báo" (NPS 3) → chủ đề Thời gian chờ, mức Cao, gợi ý gọi xin lỗi trong 24 giờ '
              'và tặng ưu đãi lần sau.',
              'Xử lý khiếu nại trong 24 giờ, giữ chân khách',
              [('dmag_ai_customer.action_dmag_ai_feedback', 'Phản hồi cần xử lý'),
               ('dmag_dental_journey.action_dmag_nps_response', 'Phản hồi NPS')], None),
    'AI-10': ('Nhập bệnh nhân từ CCCD gắn chip: quét mã QR bằng camera / máy quét, tự điền họ tên, ngày sinh, giới, số '
              'định danh, địa chỉ – tại chỗ, không cần AI.',
              'Khách mới đưa CCCD: lễ tân quét QR 2 giây, hồ sơ có đủ số định danh 12 số theo TT 13/2025.',
              'Đăng ký trong 10 giây, không gõ sai số định danh',
              [FRONTDESK], None),
    'AI-11': ('Gợi ý xếp lịch thông minh: đề xuất khung giờ lấp chỗ trống, cân bác sĩ chính / phụ, ưu tiên buổi '
              'chiều, tránh 2 ca nặng trùng giờ.',
              'Khách cần nội nha 60 phút: gợi ý 14:00 ghế 2 với bác sĩ phụ đủ phạm vi thay vì 9:00 đang kín.',
              'Công suất ghế cao hơn, khách ít phải chờ',
              [FRONTDESK], None),
    'AI-12': ('Soạn nội dung chăm sóc cá nhân hóa: kịch bản gọi hỏi thăm sau 24 giờ, tin OA theo từng ca điều trị '
              '(ZNS vẫn dùng mẫu đã đăng ký).',
              'Sau nhổ răng khôn: kịch bản gọi hỏi đau / chảy máu, nhắc chườm lạnh, hẹn cắt chỉ ngày thứ 7.',
              'Khách thấy được quan tâm thật, tăng quay lại',
              [('dmag_ai_customer.action_dmag_ai_care_draft', 'Nội dung chăm sóc'), FRONTDESK], None),
    'AI-13': ('Hỏi đáp số liệu bằng tiếng Việt ngay trên Bảng điều hành mục tiêu. AI CHỈ ĐỌC qua bộ chỉ số có sẵn, '
              'trả lời kèm số liệu và nút "Mở danh sách" tới chứng từ.',
              '"Vì sao doanh thu tháng này chậm?" → so cùng kỳ: lượt khám hoàn tất giảm 12 %, giá trị TB/lượt giữ '
              'nguyên, ghế chiều mới dùng 48 % → gợi ý lấp ghế chiều; bấm "Mở danh sách" xem từng thủ thuật.',
              'Ra quyết định trong 1 phút, không cần lập báo cáo',
              [('dmag_ai_insights.action_dmag_ai_qa', 'Hỏi đáp số liệu'), GOALS], None),
    'AI-14': ('Bản tin điều hành mỗi sáng thứ Hai 07:00 (và khi bấm nút): chỉ tiêu đang lệch, nguyên nhân có thể '
              '(phễu / bác sĩ / nhóm dịch vụ), 3 việc nên làm tuần này, điểm sáng – gửi Giám đốc trong Odoo.',
              'Họp giao ban 8:00 thứ Hai có sẵn: "Doanh thu dự báo đạt 91 % – gọi lại 7 khách đang cân nhắc kế hoạch '
              '(186 tr), xác nhận 12 lịch chưa xác nhận, lấp ghế chiều".',
              'Họp giao ban có sẵn nội dung, không ai phải tổng hợp',
              [('dmag_ai_insights.action_dmag_ai_brief_screen', 'Bản tin điều hành'), GOALS], None),
    'AI-15': ('Phát hiện bất thường bằng thống kê tại chỗ: giảm giá lệch chuẩn, hoa hồng tăng đột biến, hủy / hoàn '
              'chứng từ đã khóa, chênh lệch quỹ, công nợ tăng nhanh, vật tư vượt định mức. Quản lý giải trình, Giám '
              'đốc đóng.',
              'Một bác sĩ giảm giá 41 % số thủ thuật (đồng nghiệp 9 %, z = 5,2) → cảnh báo mức Cao kèm danh sách '
              'thủ thuật; Quản lý ghi giải trình "chương trình tri ân khách cũ", Giám đốc đóng.',
              'Chống thất thoát, gian lận – không gửi dữ liệu ra ngoài',
              [('dmag_ai_insights.action_dmag_ai_anomaly_screen', 'Cảnh báo bất thường')], None),
    'AI-16': ('Dự báo doanh thu tháng này / tháng sau từ lịch đã đặt × tỷ lệ đến khám × giá trị trung bình + xu hướng '
              'mùa vụ (Holt-Winters), có khoảng tin cậy; nhu cầu vật tư 30 ngày theo định mức → gợi ý đặt hàng.',
              'Ngày 11: dự báo cuối tháng 612 tr (80 %: 570–655 tr), khả năng đạt mục tiêu 600 tr là 62 %; trụ '
              'implant còn đủ 9 ngày → đặt thêm 6 trụ.',
              'Đặt mục tiêu sát thực tế, không thiếu vật tư',
              [('dmag_ai_insights.action_dmag_ai_forecast_screen', 'Dự báo doanh thu & vật tư'), GOALS], None),
    'AI-17': ('Trợ lý trên cổng / app bệnh nhân: giải thích kế hoạch điều trị và đơn thuốc bằng lời dễ hiểu, hướng dẫn '
              'chăm sóc sau thủ thuật, nhắc uống thuốc.',
              'Khách hỏi trên cổng "vì sao phải chữa tủy trước khi bọc sứ?" → trả lời dễ hiểu dựa trên kế hoạch của '
              'chính khách, không chẩn đoán mới.',
              'Khách hiểu và tin, tăng tỷ lệ chốt',
              [], '/my/dental'),
    'AI-18': ('Theo dõi sau điều trị: hỏi mức đau, chảy máu, sưng sau 24 / 72 giờ qua Zalo hoặc app; dấu hiệu bất '
              'thường → báo ngay bác sĩ phụ trách.',
              '24 giờ sau nhổ răng khôn khách trả lời "vẫn chảy máu nhiều, sưng to" → quy tắc đánh dấu Khẩn, bác sĩ '
              'nhận thông báo và gọi lại.',
              'An toàn, khách cảm thấy được chăm sóc',
              [('dmag_ai_customer.action_dmag_ai_followup', 'Theo dõi sau điều trị')], '/my/dental'),
    'AI-19': ('Mô phỏng nụ cười từ ảnh chụp (thẩm mỹ, chỉnh nha) – minh họa ý tưởng, giai đoạn sau dùng nhà cung cấp '
              'chuyên ngành.',
              'Khách cân nhắc veneer: xem ảnh minh họa "trước – sau" ngay trong buổi tư vấn.',
              'Bán gói thẩm mỹ, chỉnh nha',
              [('dmag_ai_customer.action_dmag_ai_smile', 'Mô phỏng nụ cười')], None),
}
OWNER = {code: ('dmag_ai_core' if code == 'AI-00' else 'dmag_ai_clinical' if code <= 'AI-06'
                 else 'dmag_ai_insights' if 'AI-13' <= code <= 'AI-16' else 'dmag_ai_customer')
         for code in ['AI-%02d' % i for i in range(20)]}
STATUS_LABELS = {
    'live': 'Đang chạy AI thật', 'simulate': 'Đang giả lập', 'local': 'Chạy tại chỗ', 'off': 'Đang tắt',
    'not_installed': 'Chưa cài module',
}


class DmagAiHub(models.AbstractModel):
    _name = 'dmag.ai.hub'
    _description = 'DMAG – Trung tâm AI'

    @api.model
    def _audiences_for_user(self):
        env = self.env
        if is_manager(env):
            return [a[0] for a in AUDIENCES]
        allowed = ['platform', 'patient']
        if env.user.has_group('dmag_dental_base.group_dmag_receptionist'):
            allowed.append('front')
        if env.user.has_group('dmag_dental_base.group_dmag_assistant'):
            allowed.append('doctor')
        return allowed

    @api.model
    def _resolve_action(self, candidates, url=None):
        """Màn hình "Thử ngay": external id đầu tiên tồn tại và người dùng mở được."""
        for xmlid, label in candidates:
            rec = self.env.ref(xmlid, raise_if_not_found=False)
            rec = rec.sudo() if rec else rec
            if not rec or rec._name not in ('ir.actions.client', 'ir.actions.act_window', 'ir.actions.server'):
                continue
            if rec._name == 'ir.actions.act_window' and rec.res_model in self.env and not \
                    self.env[rec.res_model].check_access_rights('read', raise_exception=False):
                continue
            groups = rec.groups_id if 'groups_id' in rec._fields else rec.browse()
            if groups and not (groups & self.env.user.groups_id):
                continue
            return {'xmlid': xmlid, 'label': label, 'module': xmlid.split('.')[0], 'exact': xmlid == candidates[0][0]}
        if url:
            return {'url': url, 'label': 'Cổng bệnh nhân', 'module': 'dmag_patient_portal', 'exact': False}
        return None

    @api.model
    def _discover(self, code):
        """Dò màn hình do module AI khác khai báo (tên external id chứa 'ai_xx')."""
        token = code.lower().replace('-', '_')
        data = self.env['ir.model.data'].sudo().search([
            ('module', 'in', ('dmag_ai_clinical', 'dmag_ai_customer')),
            ('model', 'in', ('ir.actions.client', 'ir.actions.act_window')), ('name', 'ilike', token)], limit=1)
        return ('%s.%s' % (data.module, data.name), data.name) if data else None

    @api.model
    def get_hub(self):
        env = self.env
        company = env.company
        status = env['dmag.ai'].get_ai_status()
        today = fields.Date.context_today(self)
        month_start = fields.Datetime.to_datetime(today.replace(day=1))
        Log = env['dmag.ai.log'].sudo()
        groups = Log._read_group([('company_id', '=', company.id), ('create_date', '>=', month_start)],
                                 ['feature_id', 'mode'], ['__count', 'cost_vnd:sum', 'estimated_cost_vnd:sum',
                                                          'input_tokens:sum', 'output_tokens:sum'])
        usage = defaultdict(lambda: {'count': 0, 'cost': 0.0, 'estimated': 0.0, 'tokens': 0, 'live': 0})
        for feature, mode, count, cost, est, tin, tout in groups:
            u = usage[feature.id]
            u['count'] += count
            u['cost'] += cost or 0.0
            u['estimated'] += est or 0.0
            u['tokens'] += (tin or 0) + (tout or 0)
            if mode == 'live':
                u['live'] += count
        total_all = Log.search_count([('company_id', '=', company.id)])
        allowed = self._audiences_for_user()
        installed = set(env['ir.module.module'].sudo().search([('state', '=', 'installed'),
                                                               ('name', 'like', 'dmag_ai_')]).mapped('name'))
        features = []
        Feature = env['dmag.ai.feature'].sudo().with_context(active_test=False)
        for feat in Feature.search([], order='code'):
            info = CATALOG.get(feat.code)
            if not info:
                continue
            what, example, benefit, candidates, url = info
            owner_module = OWNER[feat.code]
            candidates = list(candidates)
            found = self._discover(feat.code)
            if found and found[0] not in [c[0] for c in candidates]:
                candidates.insert(0, (found[0], candidates[0][1] if candidates else found[1]))
            target = self._resolve_action(candidates, url)
            module_ready = owner_module in ('dmag_ai_core', 'dmag_ai_insights') or owner_module in installed
            if not feat.active:
                state = 'off'
            elif not module_ready:
                state = 'not_installed'
            elif feat.source == 'local':
                state = 'local'
            else:
                state = 'live' if company.dmag_ai_mode == 'live' else 'simulate'
            u = usage[feat.id]
            badge = SOURCE_BADGES.get(feat.source, (feat.source, ''))
            features.append({
                'code': feat.code, 'name': feat.name, 'audience': feat.audience or 'platform',
                'source': feat.source, 'source_label': badge[0], 'source_help': badge[1],
                'model': dict(feat._fields['model'].selection).get(feat.model, feat.model) if feat.source != 'local'
                else 'Không dùng mô hình ngôn ngữ',
                'active': feat.active, 'state': state, 'state_label': STATUS_LABELS[state],
                'module': owner_module, 'module_ready': module_ready,
                'sends_patient_data': feat.sends_patient_data, 'what': what, 'example': example,
                'benefit': benefit, 'target': target, 'visible': (feat.audience or 'platform') in allowed,
                'usage': u['count'], 'live_calls': u['live'], 'cost': u['cost'], 'estimated': u['estimated'],
                'tokens': u['tokens'],
            })
        spent = status['spent_vnd']
        estimated = sum(f['estimated'] for f in features)
        days_in_month = calendar.monthrange(today.year, today.month)[1]
        projected = estimated / today.day * days_in_month if today.day else estimated
        return {
            'mode': status['mode'], 'key_set': status['key_set'], 'library': status['library'],
            'budget': status['budget_vnd'], 'spent': spent, 'estimated': estimated, 'projected': projected,
            'usd_rate': company.dmag_ai_usd_rate, 'zdr': company.dmag_ai_zdr,
            'require_consent': company.dmag_ai_require_consent,
            'calls_month': sum(f['usage'] for f in features), 'calls_total': total_all,
            'audiences': [{'key': a[0], 'label': a[1], 'tagline': a[2], 'visible': a[0] in allowed}
                          for a in AUDIENCES],
            'features': features, 'is_manager': is_manager(env), 'is_director': is_director(env),
            'user': env.user.name, 'month_label': 'Tháng %s/%s' % (today.month, today.year),
            'settings_action': 'dmag_ai_core.action_dmag_ai_settings' if is_director(env) else False,
            'consent': self._consent_stats(),
        }

    @api.model
    def _consent_stats(self):
        Partner = self.env['res.partner'].sudo()
        patients = Partner.search_count([('is_patient', '=', True)])
        consent = Partner.search_count([('is_patient', '=', True), ('dmag_ai_consent', '=', True)])
        return {'patients': patients, 'consent': consent,
                'pct': round(consent * 100.0 / patients, 1) if patients else 0.0}

    @api.model
    def open_target(self, code):
        """Hành động của nút "Thử ngay" (kiểm tra lại quyền phía máy chủ)."""
        info = CATALOG.get(code)
        if not info:
            return False
        candidates = list(info[3])
        found = self._discover(code)
        if found and found[0] not in [c[0] for c in candidates]:
            candidates.insert(0, (found[0], candidates[0][1] if candidates else found[1]))
        target = self._resolve_action(candidates, info[4])
        if not target:
            return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {
                'type': 'warning', 'title': _('Chưa mở được'),
                'message': _('Màn hình của tính năng %s chưa được cài hoặc bạn chưa có quyền.', code)}}
        if target.get('url'):
            return {'type': 'ir.actions.act_url', 'url': target['url'], 'target': 'new'}
        action = self.env['ir.actions.actions']._for_xml_id(target['xmlid'])
        if code == 'AI-13' and target['xmlid'] == GOALS[0]:
            action['context'] = {'dmag_ai_open_chat': True}
        return action

    @api.model
    def get_goal_panel(self):
        """Dải AI trên Bảng điều hành mục tiêu: dự báo (AI-16), bản tin mới nhất (AI-14), bất thường (AI-15)."""
        if not is_manager(self.env):
            return {}
        env = self.env
        status = env['dmag.ai'].get_ai_status()
        feats = status['features']
        res = {'mode': status['mode'], 'qa_active': feats.get('AI-13', {}).get('active', False)}
        if feats.get('AI-16', {}).get('active'):
            try:
                res['forecast'] = env['dmag.ai.forecast'].get_dashboard_summary()
            except Exception as e:  # noqa: BLE001 – dự báo lỗi không làm hỏng bảng điều hành
                res['forecast_error'] = str(e)
        brief = env['dmag.ai.brief'].search([('company_id', 'in', env.companies.ids)], limit=1)
        if brief:
            res['brief'] = {'id': brief.id, 'name': brief.name, 'headline': brief.headline, 'date': str(brief.date),
                            'off_track': brief.off_track_count}
        res['brief_active'] = feats.get('AI-14', {}).get('active', False)
        anomalies = env['dmag.ai.anomaly'].search([('company_id', 'in', env.companies.ids),
                                                   ('state', 'in', ('new', 'review'))])
        res['anomalies'] = {'total': len(anomalies),
                            'high': len(anomalies.filtered(lambda a: a.severity == 'high')),
                            'medium': len(anomalies.filtered(lambda a: a.severity == 'medium')),
                            'top': anomalies[:1].name or ''}
        return res
