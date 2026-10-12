"""Dữ liệu mẫu tĩnh (tên, dịch vụ, vật tư, thuốc, chính sách) cho bộ sinh dữ liệu demo.

Mọi giá trị là dữ liệu MẪU – phòng khám thay bằng số liệu thật khi vận hành.
"""

SAMPLE = '(mẫu)'

COMPANY = {
    'name_if_default': 'Nha khoa DMAG (Demo)',
    'street': '125 Nguyễn Thị Minh Khai, Phường Bến Thành',
    'city': 'TP. Hồ Chí Minh',
    'phone': '028 3822 6868',
    'email': 'lienhe@nhakhoa-dmag.demo',
    'dmag_facility_code': '79999',
    'dmag_license_number': '01234/HCM-GPHĐ (demo)',
    'dmag_professional_director': 'BSCKII Trần Minh Đức',
}

# ---------------------------------------------------------------------------- người dùng
# key: (login, họ tên, vai trò, nhóm dmag, chức danh 3P, bậc 3P)
USERS = [
    ('receptionist', 'letan.demo', 'Lê Thị Ngọc Ánh', 'dmag_dental_base.group_dmag_receptionist',
     'dmag_hr_3p.job_reception', 'P2'),
    ('consultant', 'tuvan.demo', 'Võ Thanh Trúc', 'dmag_dental_base.group_dmag_receptionist',
     'dmag_hr_3p.job_consultant', 'P2'),
    ('assistant', 'phuta.demo', 'Phạm Thị Thu Trang', 'dmag_dental_base.group_dmag_assistant',
     'dmag_hr_3p.job_nurse', 'P2'),
    ('doctor', 'bacsi.demo', 'Trần Minh Đức', 'dmag_dental_base.group_dmag_doctor',
     'dmag_hr_3p.job_doctor', 'P5'),
    ('doctor2', 'bacsi2.demo', 'Nguyễn Hoàng Yến', 'dmag_dental_base.group_dmag_doctor',
     'dmag_hr_3p.job_doctor', 'P3'),
    ('doctor3', 'bacsi3.demo', 'Lê Hoàng Nam', 'dmag_dental_base.group_dmag_doctor',
     'dmag_hr_3p.job_doctor', 'P3'),
    ('assistant2', 'phuta2.demo', 'Ngô Thị Hồng Nhung', 'dmag_dental_base.group_dmag_assistant',
     'dmag_hr_3p.job_nurse', 'P2'),
    ('manager', 'quanly.demo', 'Đỗ Quang Huy', 'dmag_dental_base.group_dmag_manager',
     'dmag_hr_3p.job_manager', 'M2'),
    ('director', 'giamdoc.demo', 'Nguyễn Văn Phúc', 'dmag_dental_base.group_dmag_director',
     'dmag_hr_3p.job_manager', 'M3'),
]
PORTAL_LOGIN = 'benhnhan.demo'
PASSWORD = 'demo'

PRACTITIONERS = {
    # key user: (chức danh, vai trò, số CCHN, bậc lâm sàng, phạm vi, màu, mã liên thông đơn thuốc)
    'doctor': ('BSCKII', 'doctor', '000123/HCM-CCHN', 'dmag_dental_base.level_3',
               ['scope_general', 'scope_endo', 'scope_surgery', 'scope_implant', 'scope_prostho', 'scope_perio'],
               4, 'BS-DEMO-0001'),
    'doctor2': ('BSCKI', 'doctor', '004567/HCM-CCHN', 'dmag_dental_base.level_2',
                ['scope_general', 'scope_endo', 'scope_ortho', 'scope_pedo', 'scope_prostho', 'scope_perio'],
                10, 'BS-DEMO-0002'),
    'doctor3': ('BSCKI', 'doctor', '007890/HCM-CCHN', 'dmag_dental_base.level_2',
                ['scope_general', 'scope_endo', 'scope_prostho', 'scope_perio'], 7, 'BS-DEMO-0003'),
    'assistant': ('ĐD', 'assistant', '010203/HCM-CCHN', False, [], 2, False),
    'assistant2': ('ĐD', 'assistant', '010204/HCM-CCHN', False, [], 3, False),
}

# Lịch nghỉ luân phiên (quyết định 11/10/2026: mở cửa cả tuần, Chủ nhật đông khách, nhân sự nghỉ luân phiên ngày thường)
# key người dùng: vai trò trong lịch luân phiên – bộ xếp lịch tự động chia ngày nghỉ (Quản lý bấm nút thật)
ROTATION = [
    ('doctor', 'doctor'), ('doctor2', 'doctor'), ('doctor3', 'doctor'),
    ('assistant', 'assistant'), ('assistant2', 'assistant'),
    ('receptionist', 'receptionist'), ('consultant', 'receptionist'),
]
SUNDAY_EXTRA = (3, 5)  # Chủ nhật thêm 3–5 lượt so với ngày thường (~1,5–2×)

CHAIRS = [
    ('Ghế 1 (demo)', 'G1', 'Phòng điều trị A'),
    ('Ghế 2 (demo)', 'G2', 'Phòng điều trị A'),
    ('Ghế 3 – Implant (demo)', 'G3', 'Phòng phẫu thuật'),
    ('Ghế 4 – Chỉnh nha (demo)', 'G4', 'Phòng chỉnh nha & trẻ em'),
]

# ---------------------------------------------------------------------------- dịch vụ
# code: (tên, nhóm, giá, phút, độ nặng, cần răng, phạm vi, bậc, bảo hành tháng, nhắc tái khám tháng,
#        tình trạng sau điều trị, cần BS thứ hai)
SERVICES = {
    'exam': ('Khám & tư vấn tổng quát', 'exam', 100000, 20, 'light', False, 'scope_general', 1, 0, 0, False, False),
    'xray_pa': ('Chụp phim X-quang cận chóp', 'imaging', 50000, 10, 'light', False, False, 0, 0, 0, False, False),
    'xray_pano': ('Chụp phim Panorama', 'imaging', 200000, 10, 'light', False, False, 0, 0, 0, False, False),
    'cbct': ('Chụp CT Cone Beam (CBCT) 1 hàm', 'imaging', 600000, 15, 'light', False, False, 0, 0, 0, False, False),
    'scaling': ('Cạo vôi & đánh bóng 2 hàm', 'hygiene', 300000, 30, 'light', False, 'scope_general', 1, 0, 6,
                False, False),
    'perio': ('Điều trị viêm nướu – nha chu (1 hàm)', 'hygiene', 700000, 45, 'normal', False, 'scope_perio', 1,
              0, 3, False, False),
    'filling': ('Trám răng Composite', 'restorative', 400000, 30, 'normal', True, 'scope_general', 1, 12, 0,
                'condition_filling', False),
    'filling_kid': ('Trám răng sữa GIC (trẻ em)', 'pediatric', 200000, 20, 'light', True, 'scope_pedo', 1, 6, 6,
                    'condition_filling', False),
    'endo_front': ('Điều trị tủy răng cửa', 'endo', 1200000, 45, 'normal', True, 'scope_endo', 2, 0, 0,
                   'condition_root_canal', False),
    'endo_molar': ('Điều trị tủy răng hàm', 'endo', 2000000, 60, 'heavy', True, 'scope_endo', 2, 0, 0,
                   'condition_root_canal', False),
    'extract': ('Nhổ răng thường', 'surgery', 500000, 30, 'normal', True, 'scope_general', 1, 0, 0,
                'condition_missing', False),
    'extract_wisdom': ('Nhổ răng khôn mọc lệch', 'surgery', 2500000, 60, 'heavy', True, 'scope_surgery', 2, 0, 0,
                       'condition_missing', False),
    'extract_kid': ('Nhổ răng sữa', 'pediatric', 100000, 15, 'light', True, 'scope_pedo', 1, 0, 0,
                    'condition_missing', False),
    'implant_kr': ('Cấy ghép Implant Hàn Quốc (Dentium)', 'implant', 15000000, 90, 'heavy', True,
                   'scope_implant', 3, 120, 6, 'condition_implant', False),
    'implant_ch': ('Cấy ghép Implant Thụy Sĩ (Straumann)', 'implant', 28000000, 90, 'heavy', True,
                   'scope_implant', 3, 240, 6, 'condition_implant', False),
    'crown_implant': ('Mão sứ trên Implant', 'prosthodontic', 6000000, 45, 'normal', True, 'scope_prostho', 2,
                      60, 0, 'condition_crown', False),
    'crown_metal': ('Mão sứ kim loại (Ni-Cr)', 'prosthodontic', 1500000, 45, 'normal', True, 'scope_prostho', 2,
                    36, 0, 'condition_crown', True),
    'crown_zirconia': ('Mão sứ Zirconia', 'prosthodontic', 5000000, 45, 'normal', True, 'scope_prostho', 2,
                       120, 0, 'condition_crown', True),
    'veneer': ('Mặt dán sứ Veneer Emax (thẩm mỹ)', 'cosmetic', 8000000, 60, 'normal', True, 'scope_prostho', 2,
               60, 0, 'condition_veneer', True),
    'whitening': ('Tẩy trắng răng tại phòng khám (thẩm mỹ)', 'cosmetic', 2500000, 60, 'normal', False,
                  'scope_general', 1, 0, 12, False, False),
    'whitening_home': ('Tẩy trắng tại nhà – máng & thuốc (thẩm mỹ)', 'cosmetic', 1500000, 20, 'light', False,
                       'scope_general', 1, 0, 0, False, False),
    'ortho_metal': ('Niềng răng mắc cài kim loại (trọn gói)', 'orthodontic', 30000000, 60, 'normal', False,
                    'scope_ortho', 2, 0, 0, False, False),
    'ortho_clear': ('Niềng răng khay trong suốt (trọn gói)', 'orthodontic', 80000000, 60, 'normal', False,
                    'scope_ortho', 2, 0, 0, False, False),
    'ortho_check': ('Tái khám chỉnh nha định kỳ (trong gói)', 'orthodontic', 0, 20, 'light', False,
                    'scope_ortho', 2, 0, 0, False, False),
    'splint': ('Máng chống nghiến răng', 'other', 1500000, 20, 'light', False, 'scope_general', 1, 12, 0,
               False, False),
}
AFTERCARE = {
    'extract_wisdom': '<p>Cắn chặt gạc 30–60 phút, chườm lạnh 24 giờ đầu, ăn mềm nguội, không súc miệng mạnh. '
                      'Tái khám cắt chỉ sau 7 ngày.</p>',
    'implant_kr': '<p>Không nhai vùng cấy ghép, vệ sinh nhẹ nhàng, không hút thuốc. Tái khám sau 7–10 ngày.</p>',
    'filling': '<p>Không ăn nhai mạnh trong 2 giờ đầu. Ê buốt nhẹ 1–2 ngày là bình thường.</p>',
    'whitening': '<p>Tránh thực phẩm sẫm màu (cà phê, trà, nước ngọt có màu) trong 48 giờ.</p>',
    'scaling': '<p>Chải răng 2 lần/ngày, dùng chỉ nha khoa. Tái khám cạo vôi sau 6 tháng.</p>',
}

# Gợi ý dịch vụ cho tình trạng trên sơ đồ răng (chỉ bổ sung khi tình trạng chưa có gợi ý)
CONDITION_SUGGESTIONS = {
    'condition_caries': ['filling'],
    'condition_pulpitis': ['endo_molar', 'endo_front'],
    'condition_periapical': ['endo_molar'],
    'condition_impacted': ['extract_wisdom'],
    'condition_fracture': ['crown_zirconia', 'crown_metal'],
    'condition_missing': ['implant_kr', 'implant_ch'],
    'condition_calculus': ['scaling'],
    'condition_residual_root': ['extract'],
}

# ---------------------------------------------------------------------------- vật tư & định mức
# code: (tên, loại, đơn vị xmlid hoặc False, giá vốn, theo dõi, tồn đầu)
MATERIALS = {
    'gloves': ('Găng tay khám (đôi)', 'consu', False, 2500, 'none', 0),
    'anesthetic': ('Thuốc tê Lidocain 2% (ống 1,8 ml)', 'product', False, 12000, 'none', 400),
    'composite': ('Composite trám răng 3M Z350 (g)', 'product', 'uom.product_uom_gram', 45000, 'none', 300),
    'niti_file': ('Trâm NiTi điều trị tủy (bộ)', 'product', False, 180000, 'none', 60),
    'gutta': ('Côn Gutta-percha (hộp)', 'product', False, 95000, 'none', 40),
    'suture': ('Chỉ khâu phẫu thuật 4.0 (sợi)', 'product', False, 35000, 'none', 120),
    'fixture_kr': ('Trụ implant Dentium SuperLine Ø4.0 × 10', 'product', False, 2800000, 'serial', 0),
    'fixture_ch': ('Trụ implant Straumann BLT Ø4.1 × 10', 'product', False, 8500000, 'serial', 0),
    'healing': ('Trụ lành thương (healing abutment)', 'product', False, 350000, 'none', 30),
}
IMPLANT_SERIALS = {
    'fixture_kr': ['DT-SL-26%04d' % i for i in range(1, 17)],
    'fixture_ch': ['ST-BLT-26%04d' % i for i in range(1, 9)],
}
# dịch vụ: [(vật tư, số lượng, per_tooth|per_procedure)]
BOMS = {
    'filling': [('composite', 0.5, 'per_tooth'), ('gloves', 2, 'per_procedure')],
    'endo_molar': [('niti_file', 1, 'per_procedure'), ('gutta', 0.2, 'per_procedure'),
                   ('anesthetic', 1, 'per_procedure'), ('gloves', 2, 'per_procedure')],
    'extract_wisdom': [('anesthetic', 2, 'per_procedure'), ('suture', 1, 'per_procedure'),
                       ('gloves', 2, 'per_procedure')],
    'implant_kr': [('fixture_kr', 1, 'per_tooth'), ('healing', 1, 'per_tooth'), ('anesthetic', 2, 'per_procedure'),
                   ('suture', 1, 'per_procedure'), ('gloves', 3, 'per_procedure')],
    'implant_ch': [('fixture_ch', 1, 'per_tooth'), ('healing', 1, 'per_tooth'), ('anesthetic', 2, 'per_procedure'),
                   ('suture', 1, 'per_procedure'), ('gloves', 3, 'per_procedure')],
}

# ---------------------------------------------------------------------------- thuốc & đơn mẫu
# code: (hoạt chất, hàm lượng, dạng, đơn vị, đường dùng, tên thương mại, nhiều hoạt chất, liều, lần/ngày, ngày,
#        thời điểm, đơn vị liều)
DRUGS = {
    'amox': ('Amoxicilin', '500 mg', 'Viên nang', 'Viên', 'oral', 'Hagimox', False, 1, 3, 5, 'after_meal', False),
    'augmentin': ('Amoxicilin + Acid clavulanic', '500 mg + 125 mg', 'Viên nén bao phim', 'Viên', 'oral',
                  'Augmentin', True, 1, 2, 5, 'after_meal', False),
    'metro': ('Metronidazol', '250 mg', 'Viên nén', 'Viên', 'oral', False, False, 2, 2, 5, 'after_meal', False),
    'rodogyl': ('Spiramycin + Metronidazol', '750.000 IU + 125 mg', 'Viên nén bao phim', 'Viên', 'oral',
                'Rodogyl', True, 2, 2, 5, 'with_meal', False),
    'clinda': ('Clindamycin', '300 mg', 'Viên nang', 'Viên', 'oral', 'Dalacin C', False, 1, 3, 5,
               'after_meal', False),
    'para': ('Paracetamol', '500 mg', 'Viên nén', 'Viên', 'oral', 'Panadol', False, 1, 3, 3, 'when_pain', False),
    'ibu': ('Ibuprofen', '400 mg', 'Viên nén bao phim', 'Viên', 'oral', False, False, 1, 3, 3, 'after_meal', False),
    'etori': ('Etoricoxib', '90 mg', 'Viên nén bao phim', 'Viên', 'oral', 'Arcoxia', False, 1, 1, 3,
              'after_meal', False),
    'alpha': ('Alphachymotrypsin', '4,2 mg', 'Viên nén', 'Viên', 'oral', 'Alphachoay', False, 2, 3, 5,
              'before_meal', False),
    'chx': ('Chlorhexidin digluconat', '0,12%', 'Dung dịch súc miệng', 'Chai', 'mouthwash', 'Kin Gingival',
            False, 10, 2, 7, 'after_brushing', 'ml'),
    'gel': ('Metronidazol + Chlorhexidin', '10 mg/g + 2,5 mg/g', 'Gel bôi nướu', 'Tuýp', 'topical',
            'Metrogyl Denta', True, 1, 2, 5, 'after_brushing', 'lần bôi'),
}
RX_TEMPLATES = [
    ('Sau nhổ răng khôn (mẫu)', 'diag_k01_1', 7,
     'Cắn chặt gạc 30–60 phút. Chườm lạnh 24 giờ đầu. Không súc miệng mạnh, không hút thuốc 24 giờ. '
     'Ăn thức ăn mềm, nguội. Tái khám cắt chỉ sau 7 ngày; chảy máu kéo dài hoặc sốt liên hệ ngay phòng khám.',
     [('augmentin', 1, 2, 5), ('ibu', 1, 3, 3), ('para', 1, 3, 3), ('chx', 10, 2, 7)]),
    ('Viêm tủy cấp (mẫu)', 'diag_k04_0', 3,
     'Tránh nhai bên răng đau, tránh đồ quá nóng / lạnh. Tái khám đúng hẹn để tiếp tục điều trị tủy.',
     [('amox', 1, 3, 5), ('metro', 2, 2, 5), ('ibu', 1, 3, 3)]),
    ('Sau cấy ghép Implant (mẫu)', 'diag_k08_1', 10,
     'Chườm lạnh 24 giờ đầu, không nhai vùng cấy ghép, không hút thuốc, không uống rượu bia. Tái khám sau 7–10 ngày.',
     [('augmentin', 1, 2, 7), ('etori', 1, 1, 3), ('alpha', 2, 3, 5), ('chx', 10, 2, 10)]),
    ('Viêm nướu – nha chu (mẫu)', 'diag_k05_1', 14,
     'Chải răng kỹ 2 lần/ngày bằng bàn chải lông mềm, dùng chỉ nha khoa, súc miệng sau chải răng.',
     [('rodogyl', 2, 2, 5), ('gel', 1, 2, 5), ('chx', 10, 2, 7)]),
]

LAB_PARTNERS = [
    ('Labo Răng Sứ Việt Mỹ (demo)', 5, '028 3999 0001', 'Quận 10, TP. Hồ Chí Minh'),
    ('Labo Kỹ thuật số Sài Gòn Digital (demo)', 7, '028 3999 0002', 'Quận Bình Thạnh, TP. Hồ Chí Minh'),
    ('Clear Aligner Lab Hà Nội (demo)', 14, '024 3999 0003', 'Quận Cầu Giấy, Hà Nội'),
]

# ---------------------------------------------------------------------------- chính sách mẫu
COMMISSION_RULES = [
    # (tên, vai trò, cách tính, tỷ lệ, số tiền cố định, ghi chú)
    ('Bác sĩ – thủ thuật phí 10% thực thu ' + SAMPLE, 'doctor', 'collected', 10.0, 0.0,
     'Tính trên tiền thực thu của thủ thuật (gồm thuế). Thu một phần → hưởng tương ứng.'),
    ('Phụ tá – 50.000 đ mỗi ca thủ thuật ' + SAMPLE, 'assistant', 'fixed', 0.0, 50000.0,
     'Cố định mỗi thủ thuật đã thu đủ tiền.'),
    ('Tư vấn viên – 3% giá trị kế hoạch đã thu ' + SAMPLE, 'consultant', 'collected', 3.0, 0.0,
     'Người tư vấn ghi trên kế hoạch điều trị.'),
    ('Lễ tân – 1% thực thu (người check-in) ' + SAMPLE, 'receptionist', 'collected', 1.0, 0.0,
     'Lễ tân tiếp đón (check-in) lượt khám.'),
    ('Người giới thiệu – 5% thực thu ' + SAMPLE, 'referrer', 'collected', 5.0, 0.0,
     'Chính sách mẫu "5% lần đầu": module hoa hồng hiện tính trên mọi lượt khám của khách được giới thiệu – '
     'giới hạn "chỉ lần đầu" cần Giám đốc theo dõi tay hoặc đặt "Hiệu lực đến".'),
]
CARE_PLANS = [
    ('Gói chăm sóc răng miệng 12 tháng ' + SAMPLE, 1200000, 12, [('exam', 2), ('scaling', 2), ('xray_pano', 1)]),
    ('Gói nụ cười gia đình 12 tháng ' + SAMPLE, 3900000, 12, [('exam', 8), ('scaling', 6), ('filling_kid', 2)]),
]

COMPLIANCE_EQUIPMENT = [
    # (key, tên, loại, hãng, serial, vị trí, kiểm định cách đây (tháng), bảo trì cách đây (tháng))
    ('cbct', 'Máy CT Cone Beam (demo)', 'cbct', 'Vatech', 'CBCT-DEMO-0001', 'Phòng X-quang', 11, 2),
    ('pano', 'Máy X-quang Panorama (demo)', 'pano', 'Carestream', 'PANO-DEMO-0002', 'Phòng X-quang', 5, 1),
    ('autoclave', 'Nồi hấp tiệt khuẩn class B 23L (demo)', 'autoclave', 'W&H', 'AC-DEMO-7788',
     'Phòng tiệt khuẩn', 3, 1),
    ('compressor', 'Máy nén khí không dầu (demo)', 'compressor', 'Cattani', 'MNK-DEMO-0003', 'Phòng kỹ thuật', 0, 7),
]
COMPLIANCE_DOCS = [
    # (tên, loại xmlid, số hiệu, nơi cấp, cấp cách đây (ngày), hết hạn sau (ngày) | None = không thời hạn, thiết bị)
    ('Giấy phép hoạt động phòng khám chuyên khoa RHM ' + SAMPLE, 'doc_type_facility_license', '01234/HCM-GPHĐ',
     'Sở Y tế TP.HCM', 1100, None, False),
    ('Giấy phép tiến hành công việc bức xạ – CBCT ' + SAMPLE, 'doc_type_radiation_license', '456/GP-SKHCN',
     'Sở Khoa học và Công nghệ TP.HCM', 700, 25, 'cbct'),
    ('Chứng thư kiểm định máy CBCT ' + SAMPLE, 'doc_type_xray_inspection', 'KĐ-2025-118', 'Trung tâm Kiểm định',
     340, 20, 'cbct'),
    ('Chứng thư kiểm định máy Panorama ' + SAMPLE, 'doc_type_xray_inspection', 'KĐ-2026-031', 'Trung tâm Kiểm định',
     150, 210, 'pano'),
    ('Hợp đồng xử lý chất thải y tế ' + SAMPLE, 'doc_type_waste_contract', 'HĐ-CTYT-2025/09',
     'Công ty Môi trường Đô thị', 370, -5, False),
    ('Biên bản kiểm tra PCCC ' + SAMPLE, 'doc_type_fire', 'PC07-2026-552', 'Phòng Cảnh sát PCCC', 200, 160, False),
    ('Quy trình kiểm soát nhiễm khuẩn ' + SAMPLE, 'doc_type_infection_control', 'QT-KSNK-01', 'Phòng khám',
     400, None, False),
    ('Đăng ký kinh doanh ' + SAMPLE, 'doc_type_business', '0312345678', 'Sở Kế hoạch và Đầu tư', 1500, None, False),
]

# ---------------------------------------------------------------------------- bệnh nhân
HCM_STREETS = [
    '45 Nguyễn Đình Chiểu, Phường Đa Kao, Quận 1', '128 Lê Văn Sỹ, Phường 13, Quận 3',
    '32 Nguyễn Trãi, Phường 3, Quận 5', '215 Cách Mạng Tháng Tám, Phường 10, Quận 3',
    '9 Phan Xích Long, Phường 2, Quận Phú Nhuận', '76 Trần Não, Phường An Khánh, TP. Thủ Đức',
    '410 Nguyễn Thị Thập, Phường Tân Quy, Quận 7', '58 Quang Trung, Phường 10, Quận Gò Vấp',
    '17 Hoàng Văn Thụ, Phường 9, Quận Phú Nhuận', '233 Điện Biên Phủ, Phường 15, Quận Bình Thạnh',
    '88 Lý Thường Kiệt, Phường 7, Quận 10', '14 Võ Văn Ngân, Phường Linh Chiểu, TP. Thủ Đức',
]
HN_STREETS = [
    '12 Phố Huế, Phường Hàng Bài, Quận Hoàn Kiếm', '56 Láng Hạ, Phường Láng Hạ, Quận Đống Đa',
    '102 Cầu Giấy, Phường Quan Hoa, Quận Cầu Giấy', '18 Nguyễn Chí Thanh, Phường Ngọc Khánh, Quận Ba Đình',
]
# key, họ tên, giới, năm sinh (hoặc 'age:N'), nghề, thành phố (hcm/hn), nguồn, gia đình, chủ hộ, giám hộ,
# cảnh báo, dị ứng, tiền sử, người giới thiệu
PATIENTS = [
    ('tuan', 'Hoàng Minh Tuấn', 'male', 1986, 'Kỹ sư phần mềm', 'hcm', 'source_facebook', 'hoang', True, False,
     ['alert_hypertension'], False, 'Tăng huyết áp, đang dùng Amlodipin 5 mg.', False),
    ('ha', 'Lê Thị Thu Hà', 'female', 1989, 'Giáo viên', 'hcm', 'source_returning', 'hoang', False, False,
     [], False, False, False),
    ('bao', 'Hoàng Gia Bảo', 'male', 'age:9', 'Học sinh', 'hcm', 'source_returning', 'hoang', False, 'tuan',
     [], False, False, False),
    ('ngoc', 'Hoàng Bảo Ngọc', 'female', 'age:4', False, 'hcm', 'source_returning', 'hoang', False, 'ha',
     ['alert_anxiety'], False, False, False),
    ('lan', 'Nguyễn Thị Lan', 'female', 1978, 'Kế toán', 'hcm', 'source_google', 'pham', True, False,
     [], False, False, False),
    ('hung', 'Phạm Văn Hùng', 'male', 1975, 'Kinh doanh', 'hcm', 'source_returning', 'pham', False, False,
     ['alert_hypertension', 'alert_diabetes'], False, 'Tiểu đường type 2, đang dùng Metformin.', False),
    ('khang', 'Phạm Minh Khang', 'male', 'age:5', False, 'hcm', 'source_returning', 'pham', False, 'lan',
     [], False, False, False),
    ('men', 'Trần Thị Mến', 'female', 1952, 'Hưu trí', 'hcm', 'source_returning', 'pham', False, False,
     ['alert_heart', 'alert_bleeding'], False, 'Bệnh mạch vành, đang dùng Aspirin 81 mg.', False),
    ('viet', 'Đặng Quốc Việt', 'male', 1983, 'Trưởng phòng kinh doanh', 'hn', 'source_zalo', 'dang', True, False,
     [], False, False, False),
    ('huong', 'Bùi Thanh Hương', 'female', 1987, 'Dược sĩ', 'hn', 'source_returning', 'dang', False, False,
     ['alert_drug_allergy'], 'Dị ứng Penicillin (nổi mề đay).', False, False),
    ('my', 'Đặng Hà My', 'female', 'age:12', 'Học sinh', 'hn', 'source_returning', 'dang', False, 'huong',
     [], False, False, False),
    ('mai', 'Nguyễn Thị Mai', 'female', 1995, 'Nhân viên văn phòng', 'hcm', 'source_referral', False, False, False,
     ['alert_anesthetic'], 'Dị ứng Lidocain.', False, 'tuan'),
    ('khanh', 'Vũ Quốc Khánh', 'male', 2001, 'Sinh viên', 'hcm', 'source_tiktok', False, False, False,
     [], False, False, False),
    ('huongdo', 'Đỗ Thanh Hương', 'female', 1979, 'Chủ cửa hàng', 'hcm', 'source_tiktok', False, False, False,
     ['alert_diabetes', 'alert_anxiety'], False, 'Tiểu đường type 2.', False),
    ('nam', 'Trần Hoài Nam', 'male', 1992, 'Kiến trúc sư', 'hcm', 'source_google', False, False, False,
     [], False, False, False),
    ('linh', 'Phan Thùy Linh', 'female', 1998, 'Nhân viên ngân hàng', 'hcm', 'source_facebook', False, False,
     False, [], False, False, False),
    ('son', 'Lý Thanh Sơn', 'male', 1969, 'Tài xế', 'hcm', 'source_hotline', False, False, False,
     ['alert_hypertension'], False, 'Tăng huyết áp.', False),
    ('thao', 'Ngô Phương Thảo', 'female', 1990, 'Thiết kế đồ họa', 'hcm', 'source_referral', False, False, False,
     [], False, False, 'mai'),
    ('duc', 'Huỳnh Tấn Đức', 'male', 1985, 'Kỹ sư xây dựng', 'hcm', 'source_walk_in', False, False, False,
     [], False, False, False),
    ('trang', 'Võ Ngọc Trâm', 'female', 2003, 'Sinh viên', 'hcm', 'source_tiktok', False, False, False,
     [], False, False, False),
    ('long', 'Tạ Đình Long', 'male', 1958, 'Hưu trí', 'hn', 'source_event', False, False, False,
     ['alert_heart'], False, 'Đặt stent mạch vành năm 2019.', False),
    ('quynh', 'Lê Như Quỳnh', 'female', 1994, 'Marketing', 'hcm', 'source_facebook', False, False, False,
     ['alert_pregnant'], False, 'Đang mang thai 20 tuần.', False),
    ('phat', 'Châu Gia Phát', 'male', 1988, 'Chủ doanh nghiệp', 'hcm', 'source_referral', False, False, False,
     [], False, False, 'viet'),
    ('yen', 'Trịnh Hải Yến', 'female', 1983, 'Bác sĩ thú y', 'hn', 'source_google', False, False, False,
     [], False, False, False),
    ('kiet', 'Mai Anh Kiệt', 'male', 1999, 'Lập trình viên', 'hcm', 'source_zalo', False, False, False,
     [], False, False, False),
    ('hanh', 'Dương Mỹ Hạnh', 'female', 1972, 'Nội trợ', 'hcm', 'source_hotline', False, False, False,
     ['alert_infectious'], False, 'Viêm gan B mạn, theo dõi định kỳ.', False),
    ('tam', 'Lâm Chí Tâm', 'male', 1996, 'Đầu bếp', 'hcm', 'source_walk_in', False, False, False,
     [], False, False, False),
    ('an', 'Kiều Bảo An', 'female', 2000, 'Người mẫu ảnh', 'hcm', 'source_tiktok', False, False, False,
     [], False, False, False),
    ('hai', 'Nghiêm Văn Hải', 'male', 1965, 'Kỹ sư điện', 'hn', 'source_referral', False, False, False,
     ['alert_bleeding'], False, 'Rung nhĩ, đang dùng thuốc chống đông Warfarin.', 'viet'),
    ('thu', 'Cao Minh Thư', 'female', 1997, 'Chuyên viên nhân sự', 'hcm', 'source_facebook', False, False, False,
     [], False, False, False),
    ('quang', 'Tô Vĩnh Quang', 'male', 1981, 'Luật sư', 'hcm', 'source_google', False, False, False,
     [], 'Dị ứng latex (găng tay cao su).', False, False),
    ('vy', 'La Tường Vy', 'female', 2005, 'Học sinh', 'hcm', 'source_tiktok', False, False, False,
     [], False, False, False),
    ('tien', 'Hồ Thị Cẩm Tiên', 'female', 1991, 'Dược sĩ', 'hcm', 'source_zalo', False, False, False,
     [], False, False, False),
    ('dung', 'Quách Tiến Dũng', 'male', 1977, 'Doanh nhân', 'hcm', 'source_event', False, False, False,
     ['alert_diabetes'], False, 'Tiểu đường kiểm soát tốt.', False),
    ('nhi', 'Âu Ngọc Nhi', 'female', 'age:7', 'Học sinh', 'hcm', 'source_referral', False, False, 'thu',
     [], False, False, 'thu'),
    ('loc', 'Văn Đình Lộc', 'male', 1993, 'Nhân viên IT', 'hn', 'source_facebook', False, False, False,
     [], False, False, False),
    ('xuan', 'Thái Thị Xuân', 'female', 1960, 'Hưu trí', 'hcm', 'source_hotline', False, False, False,
     ['alert_hypertension'], False, 'Tăng huyết áp, loãng xương.', False),
    ('binh', 'Giang Thanh Bình', 'male', 1987, 'Phi công', 'hcm', 'source_google', False, False, False,
     [], False, False, False),
    ('ha2', 'Lưu Khánh Hà', 'female', 1999, 'Tiếp viên hàng không', 'hcm', 'source_referral', False, False, False,
     [], False, False, 'binh'),
    ('minh', 'Đoàn Nhật Minh', 'male', 2002, 'Sinh viên', 'hn', 'source_tiktok', False, False, False,
     [], False, False, False),
]
FAMILIES = {
    'hoang': 'Gia đình anh Hoàng Minh Tuấn',
    'pham': 'Gia đình chị Nguyễn Thị Lan',
    'dang': 'Gia đình anh Đặng Quốc Việt',
}
PORTAL_PATIENT = 'tuan'

# Gói / kế hoạch điều trị mẫu (đều theo dịch vụ ở trên): key → mô tả kịch bản
#   findings: [(tình trạng, răng, mặt)]; options: [(tên, khuyến nghị, tóm tắt, trả góp tháng, đặt cọc,
#   [(dịch vụ, răng, mặt, giai đoạn)])]
SCENARIOS = {
    'caries': {
        'title': 'Điều trị sâu răng',
        'complaint': 'Ê buốt khi ăn đồ ngọt, lạnh vài tuần nay.',
        'exam': 'Lỗ sâu mặt nhai răng {t0}, {t1}; nướu hồng, không lung lay.',
        'assessment': 'Sâu ngà răng {t0}, {t1}.',
        'diagnoses': ['diag_k02_1'],
        'findings': [('condition_caries', 0, ['O']), ('condition_caries', 1, ['O', 'M'])],
        'teeth': [['16', '26'], ['36', '46'], ['17', '37'], ['15', '25']],
        'options': [('Trám Composite thẩm mỹ', True, 'Bảo tồn tối đa mô răng, màu tự nhiên, bảo hành 12 tháng.',
                     0, 0, [('filling', [0], ['O'], 1), ('filling', [1], ['O', 'M'], 1)])],
        'rx': False,
    },
    'endo_crown': {
        'title': 'Điều trị tủy và bọc sứ răng hàm',
        'complaint': 'Đau nhức răng hàm dưới về đêm, đau lan lên thái dương.',
        'exam': 'Răng {t0} sâu lớn sát tủy, gõ đau (+), thử lạnh đau kéo dài.',
        'assessment': 'Viêm tủy không hồi phục răng {t0}.',
        'diagnoses': ['diag_k04_0'],
        'findings': [('condition_pulpitis', 0, [])],
        'teeth': [['36'], ['46'], ['26'], ['16']],
        'options': [
            ('Phương án A – Tủy + Mão sứ Zirconia', True,
             'Thẩm mỹ cao, không đen viền nướu, bền chắc, bảo hành 10 năm. Chi phí cao hơn phương án B.', 6,
             2000000, [('endo_molar', [0], [], 1), ('crown_zirconia', [0], [], 2)]),
            ('Phương án B – Tủy + Mão sứ kim loại', False,
             'Chi phí tiết kiệm, chịu lực tốt. Có thể đen viền nướu sau vài năm, bảo hành 3 năm.', 0, 0,
             [('endo_molar', [0], [], 1), ('crown_metal', [0], [], 2)]),
        ],
        'rx': 'Viêm tủy cấp (mẫu)',
        'lab': ('crown_bridge', 'zirconia', 2500000),
    },
    'wisdom': {
        'title': 'Nhổ răng khôn mọc lệch',
        'complaint': 'Sưng đau vùng góc hàm, há miệng hạn chế.',
        'exam': 'Răng {t0} mọc lệch gần 45°, lợi trùm viêm đỏ. Phim Panorama: chân răng gần ống thần kinh.',
        'assessment': 'Răng khôn {t0} mọc lệch, viêm lợi trùm.',
        'diagnoses': ['diag_k01_1'],
        'findings': [('condition_impacted', 0, [])],
        'teeth': [['38'], ['48'], ['38'], ['48']],
        'options': [('Nhổ răng khôn tiểu phẫu', True, 'Loại bỏ nguyên nhân viêm tái phát, bảo vệ răng số 7.',
                     0, 0, [('extract_wisdom', [0], [], 1)])],
        'rx': 'Sau nhổ răng khôn (mẫu)',
        'senior': True,
    },
    'implant': {
        'title': 'Phục hình răng mất bằng Implant',
        'complaint': 'Mất răng hàm đã lâu, ăn nhai khó khăn.',
        'exam': 'Mất răng {t0}, sống hàm đủ rộng; CBCT: xương đủ chiều cao.',
        'assessment': 'Mất răng {t0} do sâu răng.',
        'diagnoses': ['diag_k08_1'],
        'findings': [('condition_missing', 0, [])],
        'teeth': [['36'], ['46'], ['26'], ['16']],
        'options': [
            ('Phương án A – Implant Hàn Quốc + mão sứ', True,
             'Chi phí hợp lý, tỷ lệ thành công cao, bảo hành trụ 10 năm.', 12, 5000000,
             [('implant_kr', [0], [], 1), ('crown_implant', [0], [], 2)]),
            ('Phương án B – Implant Thụy Sĩ cao cấp + mão sứ', False,
             'Bề mặt trụ thế hệ mới, tích hợp xương nhanh, bảo hành trụ 20 năm. Chi phí cao hơn.', 12, 10000000,
             [('implant_ch', [0], [], 1), ('crown_implant', [0], [], 2)]),
        ],
        'rx': 'Sau cấy ghép Implant (mẫu)',
        'senior': True,
        'lab': ('implant_abutment', 'zirconia', 1800000),
    },
    'ortho': {
        'title': 'Chỉnh nha 2 hàm',
        'complaint': 'Răng mọc lệch lạc, muốn niềng răng cho đều.',
        'exam': 'Chen chúc răng cửa hai hàm, cắn sâu; khớp cắn loại II.',
        'assessment': 'Lệch lạc răng – khớp cắn loại II.',
        'diagnoses': ['diag_k07_3'],
        'findings': [],
        'teeth': [[]],
        'options': [
            ('Phương án A – Mắc cài kim loại', True,
             'Hiệu quả với ca chen chúc, chi phí hợp lý; trả góp 24 tháng.', 24, 10000000,
             [('ortho_metal', [], [], 1)]),
            ('Phương án B – Khay trong suốt', False,
             'Thẩm mỹ, tháo lắp được, cần tuân thủ đeo 22 giờ/ngày; chi phí cao.', 24, 20000000,
             [('ortho_clear', [], [], 1)]),
        ],
        'rx': False,
        'ortho': True,
        'lab': ('aligner', 'thermoform', 1200000),
    },
    'whitening': {
        'title': 'Tẩy trắng răng thẩm mỹ',
        'complaint': 'Răng ố vàng, muốn làm trắng trước đám cưới.',
        'exam': 'Răng nhiễm màu ngoại sinh mức độ trung bình, không sâu, không viêm nướu.',
        'assessment': 'Nhiễm màu răng ngoại sinh.',
        'diagnoses': ['diag_k03_6'],
        'findings': [],
        'teeth': [[]],
        'options': [
            ('Tẩy trắng tại phòng khám', True, 'Hiệu quả ngay sau 1 buổi, kiểm soát ê buốt tốt.', 0, 0,
             [('whitening', [], [], 1)]),
            ('Tẩy trắng tại nhà', False, 'Chi phí thấp hơn, cần đeo máng 2 tuần.', 0, 0,
             [('whitening_home', [], [], 1)]),
        ],
        'rx': False,
    },
    'veneer': {
        'title': 'Dán sứ Veneer thẩm mỹ răng cửa',
        'complaint': 'Răng cửa thưa, sứt mẻ, muốn cải thiện nụ cười.',
        'exam': 'Răng {t0}, {t1} mẻ bờ cắn, khe thưa 1 mm.',
        'assessment': 'Mẻ men bờ cắn răng {t0}, {t1}.',
        'diagnoses': ['diag_k03_1'],
        'findings': [('condition_fracture', 0, []), ('condition_fracture', 1, [])],
        'teeth': [['11', '21'], ['12', '22']],
        'options': [
            ('Mặt dán sứ Veneer Emax', True, 'Mài răng tối thiểu, thẩm mỹ cao, bền màu.', 6, 4000000,
             [('veneer', [0, 1], ['B'], 1)]),
            ('Trám Composite thẩm mỹ', False, 'Chi phí thấp, có thể đổi màu sau 2–3 năm.', 0, 0,
             [('filling', [0], ['I'], 1), ('filling', [1], ['I'], 1)]),
        ],
        'rx': False,
        'lab': ('veneer', 'emax', 1800000),
    },
    'perio': {
        'title': 'Điều trị viêm nướu',
        'complaint': 'Chảy máu chân răng khi chải, hôi miệng.',
        'exam': 'Cao răng độ 2, nướu viêm đỏ, chảy máu khi thăm khám, túi nha chu 4 mm.',
        'assessment': 'Viêm nha chu mạn.',
        'diagnoses': ['diag_k05_3'],
        'findings': [('condition_calculus', 0, [])],
        'teeth': [['31'], ['41']],
        'options': [('Cạo vôi + điều trị nha chu', True, 'Làm sạch sâu, kiểm soát viêm, tái khám sau 3 tháng.',
                     0, 0, [('scaling', [], [], 1), ('perio', [], [], 1)])],
        'rx': 'Viêm nướu – nha chu (mẫu)',
    },
}
# Lượt khám lẻ (không kế hoạch)
SIMPLE_VISITS = {
    'hygiene': ('Cạo vôi định kỳ 6 tháng', 'Tái khám định kỳ, không đau.',
                'Cao răng độ 1 hai hàm, nướu viêm nhẹ vùng răng cửa dưới.', 'Viêm nướu mạn do cao răng.',
                ['diag_k05_1'], ['exam', 'scaling']),
    'kid': ('Khám răng cho bé', 'Bé kêu ê răng khi ăn kẹo.', 'Sâu răng sữa {t0} mặt nhai.',
            'Sâu răng sữa {t0}.', ['diag_k02_1'], ['exam', 'filling_kid']),
    'checkup': ('Khám tổng quát & chụp phim', 'Muốn kiểm tra răng tổng quát.',
                'Răng miệng ổn định, cao răng ít.', 'Răng miệng bình thường, cao răng độ 1.',
                ['diag_k03_6'], ['exam', 'xray_pano']),
    'splint': ('Nghiến răng ban đêm', 'Mỏi hàm buổi sáng, vợ/chồng phàn nàn nghiến răng.',
               'Mòn mặt nhai răng hàm, cơ cắn phì đại nhẹ.', 'Nghiến răng (bruxism).',
               ['diag_k03_0'], ['exam', 'splint']),
}
NPS_COMMENTS = {
    10: ['Bác sĩ rất nhẹ tay, giải thích kỹ.', 'Phòng khám sạch sẽ, không phải chờ lâu.', 'Sẽ giới thiệu bạn bè.',
         'Lễ tân nhiệt tình, nhắc lịch qua Zalo rất tiện.', 'Nhổ răng khôn mà gần như không đau, cảm ơn bác sĩ!'],
    9: ['Dịch vụ tốt, nhân viên thân thiện.', 'Hài lòng với kết quả.', 'Giá rõ ràng, được báo trước từng khoản.'],
    8: ['Ổn, nhưng chờ hơi lâu.', 'Bác sĩ giỏi nhưng chỗ gửi xe hơi chật.'],
    7: ['Chi phí hơi cao so với mong đợi.', 'Phải chờ 25 phút mới được vào ghế.'],
    5: ['Phải chờ gần 40 phút dù đã đặt lịch.', 'Nhân viên thu ngân trả lời cộc lốc, không giải thích hóa đơn.'],
    3: ['Ê buốt nhiều sau trám, gọi điện chưa ai phản hồi.', 'Đau nhức 2 ngày sau nhổ răng, thấy bị bỏ mặc.'],
}
CANCEL_REASONS = ['Bận việc đột xuất', 'Khách đổi lịch sang tuần sau', 'Khách bị ốm', 'Kẹt xe, xin hẹn lại']

# Trợ lý AI (dmag_ai_*): bệnh nhân CHƯA đồng ý xử lý bằng AI (~10 %) và thông tin cho kiểm tra an toàn đơn thuốc
AI_NO_CONSENT = ('vy', 'long', 'hanh', 'khanh')
AI_PATIENT_EXTRA = {
    'hai': {'current_medication': 'Warfarin 5 mg/ngày (rung nhĩ) – INR gần nhất 2,6.'},
    'men': {'current_medication': 'Aspirin 81 mg/ngày; Bisoprolol 2,5 mg/ngày.'},
    'hung': {'current_medication': 'Metformin 500 mg × 2 lần/ngày; Amlodipin 5 mg/ngày.'},
    'quynh': {'is_pregnant': True, 'current_medication': 'Viên sắt + acid folic (thai 20 tuần).'},
}
# Tin nhắn Zalo OA mẫu (đường webhook): hỏi giá (chờ duyệt), ca khẩn, khiếu nại
# Câu hỏi NGOÀI dữ liệu đã nạp → trợ lý gửi tin giữ chỗ, báo lễ tân đang trực; nhân viên trả lời rồi đề xuất kịch bản /
# nạp vào kho tri thức. (uid, tên, SĐT, câu hỏi, người trả lời, câu trả lời, xử lý)
#   xử lý: 'script_approved' – đề xuất thành kịch bản, Giám đốc duyệt (ví dụ khép vòng huấn luyện)
#          'script_draft'    – đề xuất thành kịch bản, chờ Giám đốc duyệt
#          'kb_approved' / 'kb_draft' – "Nạp vào kho tri thức", Giám đốc đã duyệt / chờ duyệt
#          'open' / 'overdue' – chưa trả lời (quá hạn → đã báo Quản lý)
AI_GAP_CHATS = [
    ('zalo-demo-004', 'Chị Vân (Zalo)', '0912777888',
     'Bên mình có xuất hóa đơn VAT cho công ty không ạ? Công ty em muốn khám định kỳ cho nhân viên.', 'receptionist',
     'Dạ có ạ. Phòng khám xuất hóa đơn điện tử (VAT) cho công ty – anh/chị gửi tên công ty, mã số thuế, địa chỉ và email '
     'nhận hóa đơn khi thanh toán. Với gói khám định kỳ cho nhân viên, quản lý sẽ gọi lại báo giá theo số lượng trong '
     'hôm nay ạ.', ('script_approved', 'kb_approved')),
    ('zalo-demo-005', 'Bác Tư (Zalo)', '0903456789',
     'Phòng khám có xe đưa đón người cao tuổi không cháu? Bác ở Thủ Đức.', 'consultant',
     'Dạ phòng khám chưa có xe đưa đón ạ. Bác đặt lịch trước, khi đến lễ tân sẽ hỗ trợ bác từ cửa xe vào ghế khám; tầng '
     'trệt có lối đi cho xe lăn ạ.', ('script_draft', 'kb_draft')),
    ('zalo-demo-006', 'Anh Tuấn (Zalo)', '0987654321',
     'Phòng khám có chỗ cho bé chơi trong lúc bố mẹ khám không?', 'receptionist',
     'Dạ có góc chơi cho bé ở khu chờ tầng trệt, lễ tân trông giúp trong lúc anh/chị khám ạ.', ('script_draft',)),
    ('zalo-demo-007', 'Chị Mai Anh (Zalo)', '0934222111',
     'Phòng khám có nhận bảo hiểm sức khỏe Bảo Việt không ạ?', None, None, ('overdue',)),
    ('zalo-demo-008', 'Anh Phát (Zalo)', '0966888999',
     'Em muốn hỏi có làm răng sứ cho người đang chạy thận được không?', None, None, ('open',)),
]
# Tài liệu mẫu nạp vào kho tri thức (Quản lý tải lên, Giám đốc duyệt)
KB_DOCUMENT = ('Cẩm nang khách hàng ' + SAMPLE, 'cam-nang-khach-hang.md', """# Chính sách hủy và đổi lịch
Khách đổi hoặc hủy lịch trước 24 giờ không mất phí giữ chỗ. Lịch niềng răng, implant đã đặt cọc: hoàn cọc nếu hủy trước
khi bắt đầu điều trị.

# Khám cho người cao tuổi và người khuyết tật
Tầng trệt có lối đi cho xe lăn, ghế nha nâng hạ; lễ tân hỗ trợ từ cửa vào ghế khám.

# Đi khám cùng trẻ nhỏ
Khu chờ có góc chơi cho bé; trẻ dưới 16 tuổi cần bố mẹ hoặc người giám hộ đi cùng khi khám, làm thủ thuật.

# Hóa đơn và chứng từ
Phòng khám xuất hóa đơn điện tử cho cá nhân và công ty; bản sao bệnh án, đơn thuốc cung cấp khi khách yêu cầu.
""")

AI_ZALO_CHATS = [
    ('zalo-demo-001', 'Minh Thư (Zalo)', '0938111222', ['Chào phòng khám, niềng răng trong suốt giá khoảng bao nhiêu ạ?',
                                                         'Có trả góp không ạ?']),
    ('zalo-demo-002', 'Anh Khoa (Zalo)', '0977333444', ['Răng khôn của em sưng to, sốt, há miệng không được, đau quá '
                                                         'có khám gấp được không?']),
    ('zalo-demo-003', 'Chị Loan (Zalo)', '0909555666', ['Hôm qua tôi đặt lịch 9h mà chờ tới 9h45, nhân viên còn cáu '
                                                         'gắt. Rất thất vọng, tôi muốn gặp quản lý.']),
]
