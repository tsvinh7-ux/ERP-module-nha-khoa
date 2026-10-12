"""Bộ kịch bản trả lời chuẩn (tiếng Việt) cho trợ lý Zalo – bản đã rà soát theo yêu cầu của chủ phòng khám ("đồng ý
hãy dựng", 11/10/2026).

Nguyên tắc biên soạn:
* KHÔNG ghi cứng giá, giờ, số tháng bảo hành, tên bác sĩ – mọi số liệu lấy từ dữ liệu THẬT của Odoo qua ô dữ liệu
  (``{gia_dich_vu}`` bảng giá, ``{bao_hanh}`` thời hạn bảo hành của dịch vụ, ``{gio_lam_viec}`` Lịch làm việc phòng
  khám – mở cả tuần, ``{bac_si_lam_viec}`` ngày trực của bác sĩ theo Lịch nghỉ luân phiên, ``{goi_cham_soc}`` gói chăm
  sóc, ``{thanh_toan}``, ``{dia_chi}``…). Đổi bảng giá / lịch → câu trả lời tự đổi, không phải duyệt lại kịch bản.
* Không chẩn đoán, không hứa kết quả; câu chữ y khoa chỉ là hướng dẫn chung đã được duyệt. Kịch bản "đau sau nhổ răng"
  gửi mẫu an toàn rồi chuyển bác sĩ / nhân viên trực.
* Nạp ở trạng thái NHÁP – Giám đốc đọc, sửa, duyệt (bản demo do Giám đốc demo duyệt bằng nút thật).
"""

SAMPLE_SCRIPTS = [
    {
        'code': 'gia_dich_vu', 'name': 'Giá dịch vụ', 'category': 'price', 'flow': 'template',
        'keywords': 'giá, bao nhiêu tiền, chi phí, bảng giá, báo giá, hết bao nhiêu, giá cả',
        'sample_questions': 'Cạo vôi răng giá bao nhiêu ạ?\nTrám răng hết bao nhiêu tiền?\nCho em xin bảng giá\n'
                            'Chi phí bọc răng sứ khoảng bao nhiêu?\nImplant giá thế nào ạ?\nNhổ răng khôn bao nhiêu tiền?',
        'answer_template': 'Dạ {ten_khach} ơi, em gửi giá niêm yết theo bảng giá của phòng khám ạ:\n{gia_dich_vu}\n'
                           'Đây là giá tham khảo – chi phí chính xác bác sĩ sẽ báo sau khi khám (và chụp phim nếu cần), '
                           'anh/chị đồng ý rồi mới làm ạ. Anh/chị muốn em giữ chỗ lịch khám không ạ?',
        'quick_replies': 'Đặt lịch khám | Giờ làm việc | Trả góp',
        'tools': ['search_services'], 'services': ['Khám & tư vấn', 'Cạo vôi'], 'allow_rephrase': True,
    },
    {
        'code': 'gio_mo_cua', 'name': 'Giờ làm việc (mở cả tuần, kể cả Chủ nhật)', 'category': 'info',
        'flow': 'template',
        'keywords': 'mấy giờ, giờ mở cửa, giờ làm việc, mở cửa, đóng cửa, chủ nhật, nghỉ lễ, ngày lễ, cuối tuần, thứ 7',
        'sample_questions': 'Phòng khám mở cửa mấy giờ ạ?\nChủ nhật có làm việc không?\nMấy giờ đóng cửa vậy?\n'
                            'Lễ có nghỉ không ạ?\nCuối tuần phòng khám có mở không?',
        'answer_template': 'Dạ lịch làm việc của phòng khám: {gio_lam_viec}.\n{ngay_nghi_sap_toi}\n'
                           'Cuối tuần (nhất là Chủ nhật) thường đông khách, anh/chị đặt lịch trước giúp em để không phải '
                           'chờ lâu ạ. Hotline: {hotline}.',
        'quick_replies': 'Xem giờ trống | Đặt lịch khám | Địa chỉ',
        'tools': ['get_clinic_info'], 'allow_rephrase': True,
    },
    {
        'code': 'dia_chi_do_xe', 'name': 'Địa chỉ & chỗ đỗ xe', 'category': 'info', 'flow': 'template',
        'keywords': 'địa chỉ, ở đâu, chỗ nào, đường nào, chỉ đường, gửi xe, đậu xe, đỗ xe, ô tô, bãi xe',
        'sample_questions': 'Phòng khám ở đâu vậy ạ?\nCho xin địa chỉ\nCó chỗ đậu ô tô không?\nGửi xe máy ở đâu ạ?',
        'answer_template': 'Dạ địa chỉ phòng khám: {dia_chi}.\nGửi xe: {gui_xe}\n'
                           'Cần chỉ đường anh/chị gọi hotline {hotline} ạ.',
        'quick_replies': 'Giờ làm việc | Đặt lịch khám',
        'tools': ['get_clinic_info'], 'allow_rephrase': True,
    },
    {
        'code': 'dat_lich', 'name': 'Đặt lịch khám', 'category': 'booking', 'flow': 'booking',
        'keywords': 'đặt lịch, đặt hẹn, hẹn lịch, giữ chỗ, lấy lịch, đăng ký khám, còn lịch, lịch trống, giờ trống',
        'sample_questions': 'Cho em đặt lịch cạo vôi chiều mai\nMình muốn đặt lịch khám thứ 7\n'
                            'Còn lịch trống chiều nay không ạ?\nĐặt hẹn khám răng giúp em\nChủ nhật này còn lịch không?',
        'answer_template': 'Dạ em giữ chỗ giúp anh/chị ạ. Giờ còn trống gần nhất: {gio_trong}.\n'
                           'Anh/chị chọn giờ và cho em xin họ tên, số điện thoại – lễ tân sẽ gọi / nhắn xác nhận lịch.',
        'quick_replies': 'Chiều nay | Sáng mai | Chủ nhật',
        'tools': ['search_services', 'get_free_slots', 'find_patient_by_phone', 'book_appointment', 'get_clinic_info'],
    },
    {
        'code': 'doi_huy_lich', 'name': 'Đổi / hủy lịch hẹn', 'category': 'booking', 'flow': 'handoff',
        'handoff_reason': 'human_request',
        'keywords': 'đổi lịch, dời lịch, hủy lịch, huỷ lịch, hủy hẹn, không đến được, đổi giờ, lùi lịch',
        'sample_questions': 'Em muốn đổi lịch hẹn sang ngày khác\nCho mình hủy lịch hẹn mai nhé\n'
                            'Mai em bận không đến được, dời lịch giúp em',
        'answer_template': 'Dạ em đã ghi nhận yêu cầu đổi / hủy lịch của {ten_khach} và chuyển lễ tân xử lý ngay; lễ tân '
                           'sẽ nhắn xác nhận lại trong giờ làm việc ({gio_lam_viec}) ạ. Giờ còn trống gần nhất để '
                           'anh/chị tham khảo: {gio_trong}.',
        'tools': ['get_clinic_info', 'get_free_slots', 'handoff_to_staff'],
    },
    {
        'code': 'chuan_bi_kham', 'name': 'Chuẩn bị trước khi khám', 'category': 'info', 'flow': 'template',
        'keywords': 'chuẩn bị, mang theo, cần mang, nhịn ăn, trước khi khám, giấy tờ',
        'sample_questions': 'Đi khám cần mang theo gì ạ?\nCó phải nhịn ăn trước khi nhổ răng không?\n'
                            'Trước khi khám cần chuẩn bị gì?',
        'answer_template': 'Dạ trước khi đến anh/chị chuẩn bị giúp em: {chuan_bi}\n'
                           'Nếu đang dùng thuốc chống đông, tiểu đường, huyết áp hoặc đang mang thai, anh/chị báo bác sĩ '
                           'khi khám ạ. Cần hỗ trợ thêm anh/chị gọi {hotline}.',
        'quick_replies': 'Đặt lịch khám | Địa chỉ',
        'tools': ['get_clinic_info'], 'allow_rephrase': True,
    },
    {
        'code': 'bao_hanh', 'name': 'Chính sách bảo hành', 'category': 'policy', 'flow': 'template',
        'keywords': 'bảo hành, bao lâu thì hỏng, hư thì sao, thẻ bảo hành, bị bong, bị mẻ',
        'sample_questions': 'Răng sứ bảo hành bao lâu ạ?\nImplant có bảo hành không?\n'
                            'Trám răng bị bong có bảo hành không?',
        'answer_template': 'Dạ thời hạn bảo hành theo từng dịch vụ (ghi trên thẻ bảo hành điện tử trong hồ sơ của '
                           'anh/chị):\n{bao_hanh}\n'
                           'Điều kiện: tái khám định kỳ đúng hẹn và vệ sinh răng miệng theo hướng dẫn của bác sĩ. Khi có '
                           'vấn đề anh/chị nhắn em hoặc đến phòng khám ({gio_lam_viec}), mang theo CCCD để bác sĩ kiểm '
                           'tra ạ.',
        'quick_replies': 'Đặt lịch kiểm tra | Hotline',
        'tools': ['search_services', 'get_clinic_info'],
        'services': ['Mão sứ Zirconia', 'Cấy ghép Implant Hàn Quốc', 'Trám răng', 'Veneer'], 'allow_rephrase': True,
    },
    {
        'code': 'tra_gop', 'name': 'Trả góp & thanh toán', 'category': 'policy', 'flow': 'template',
        'keywords': 'trả góp, góp, thanh toán, quẹt thẻ, chuyển khoản, trả trước, trả nhiều lần, đặt cọc',
        'sample_questions': 'Có trả góp không ạ?\nNiềng răng trả góp được không?\nCó quẹt thẻ được không?\n'
                            'Thanh toán chuyển khoản được không?',
        'answer_template': 'Dạ phòng khám nhận: {thanh_toan}\n'
                           'Với điều trị dài ngày (niềng răng, implant) anh/chị có thể thanh toán theo từng đợt điều trị; '
                           'điều kiện trả góp cụ thể nhân viên tư vấn sẽ báo khi anh/chị đến khám ạ.',
        'quick_replies': 'Bảng giá | Đặt lịch tư vấn',
        'tools': ['get_clinic_info'], 'allow_rephrase': True,
    },
    {
        'code': 'dau_sau_nho_rang', 'name': 'Đau sau nhổ răng (mẫu an toàn + chuyển bác sĩ)', 'category': 'safety',
        'flow': 'handoff', 'handoff_reason': 'medical_question',
        'keywords': 'sau nhổ, nhổ răng xong, nhổ răng khôn xong, vừa nhổ, mới nhổ, sau khi nhổ',
        'sample_questions': 'Em mới nhổ răng khôn hôm qua giờ còn đau\nNhổ răng xong bị đau có sao không ạ?\n'
                            'Sau nhổ răng ê nhức quá phải làm sao',
        'answer_template': 'Dạ em rất tiếc anh/chị đang khó chịu. Sau nhổ răng, đau và ê nhẹ trong 2–3 ngày đầu là '
                           'thường gặp; anh/chị nên:\n'
                           '• cắn chặt gạc 30 phút, không khạc nhổ, không súc miệng mạnh trong 24 giờ đầu;\n'
                           '• chườm lạnh bên má, ăn đồ mềm nguội, không hút thuốc, không uống rượu bia;\n'
                           '• dùng thuốc đúng đơn bác sĩ đã kê, không tự mua thêm thuốc.\n'
                           'Em đã báo bác sĩ / nhân viên trực gọi lại hỏi thăm anh/chị. Nếu chảy máu không cầm, sưng lan '
                           'rộng, sốt cao hoặc khó thở, anh/chị gọi ngay {hotline} hoặc đến cơ sở y tế gần nhất ạ.',
        'tools': ['get_clinic_info', 'handoff_to_staff'],
    },
    {
        'code': 'nieng_rang', 'name': 'Niềng răng – tư vấn chung', 'category': 'consult', 'flow': 'template',
        'keywords': 'niềng, chỉnh nha, mắc cài, khay trong, invisalign, răng hô, răng móm, răng lệch',
        'sample_questions': 'Niềng răng mất bao lâu ạ?\nEm muốn tư vấn niềng răng\nRăng hô có niềng được không?\n'
                            'Niềng răng trong suốt giá khoảng bao nhiêu?',
        'answer_template': 'Dạ phương pháp niềng (mắc cài hay khay trong suốt) và thời gian điều trị bác sĩ chỉnh nha '
                           'chỉ xác định được sau khi khám, chụp phim và lấy dấu ạ. Giá niêm yết tham khảo:\n'
                           '{gia_dich_vu}\nPhòng khám nhận thanh toán theo đợt / trả góp. Bác sĩ chỉnh nha: '
                           '{bac_si_lam_viec}\nAnh/chị muốn đặt lịch tư vấn chỉnh nha không ạ?',
        'quick_replies': 'Đặt lịch tư vấn | Trả góp',
        'tools': ['search_services', 'get_clinic_info'], 'services': ['Niềng răng'], 'allow_rephrase': True,
        'doctor_scope': 'scope_ortho',
    },
    {
        'code': 'tay_trang', 'name': 'Tẩy trắng răng', 'category': 'consult', 'flow': 'template',
        'keywords': 'tẩy trắng, trắng răng, răng ố, răng vàng, làm trắng',
        'sample_questions': 'Tẩy trắng răng giá bao nhiêu?\nRăng em bị ố vàng muốn làm trắng\n'
                            'Tẩy trắng có hại men răng không?',
        'answer_template': 'Dạ tẩy trắng chỉ thực hiện sau khi bác sĩ kiểm tra răng, nướu (cạo vôi trước nếu cần) để an '
                           'toàn cho men răng; sau tẩy trắng nên tránh cà phê, trà, nước có màu vài ngày ạ. Giá niêm yết:\n'
                           '{gia_dich_vu}\nGiờ trống gần nhất: {gio_trong}. Anh/chị muốn em giữ chỗ không ạ?',
        'quick_replies': 'Đặt lịch khám | Bảng giá',
        'tools': ['search_services', 'get_free_slots'], 'services': ['Tẩy trắng'], 'allow_rephrase': True,
    },
    {
        'code': 'kham_tre_em', 'name': 'Khám răng cho trẻ em', 'category': 'consult', 'flow': 'template',
        'keywords': 'trẻ em, cho bé, cho con, em bé, răng sữa, bé nhà, trẻ con, con tôi',
        'sample_questions': 'Phòng khám có khám cho bé 5 tuổi không?\nCon em bị sâu răng sữa\n'
                            'Bé nhà mình mấy tuổi thì nên đi khám răng?',
        'answer_template': 'Dạ phòng khám có khám và điều trị răng cho trẻ em ạ. Bé đi cùng bố/mẹ hoặc người giám hộ, mang '
                           'theo giấy khai sinh / mã định danh của bé. Giá tham khảo:\n{gia_dich_vu}\n'
                           'Giờ trống gần nhất: {gio_trong}. Anh/chị muốn em giữ chỗ cho bé không ạ?',
        'quick_replies': 'Đặt lịch cho bé | Địa chỉ',
        'tools': ['search_services', 'get_free_slots'], 'services': ['Khám & tư vấn', 'răng sữa'],
        'allow_rephrase': True,
    },
    {
        'code': 'lich_bac_si', 'name': 'Bác sĩ làm việc ngày nào (lịch luân phiên)', 'category': 'info',
        'flow': 'template',
        'keywords': 'bác sĩ nào, lịch bác sĩ, bác sĩ làm, bác sĩ trực, bác sĩ có làm, bác sĩ nghỉ, gặp bác sĩ hôm',
        'sample_questions': 'Bác sĩ Đức làm những ngày nào ạ?\nThứ 2 bác sĩ nào trực?\n'
                            'Chủ nhật có bác sĩ niềng răng không?\nLịch làm việc của bác sĩ thế nào?',
        'answer_template': 'Dạ phòng khám làm việc {gio_lam_viec}; các bác sĩ nghỉ luân phiên vào ngày thường, Chủ nhật '
                           'đủ bác sĩ ạ:\n{bac_si_lam_viec}\n'
                           'Anh/chị muốn khám với bác sĩ nào, em xem giờ trống và giữ chỗ giúp ạ.',
        'quick_replies': 'Đặt lịch khám | Giờ làm việc',
        'tools': ['get_clinic_info'], 'allow_rephrase': True,
    },
    {
        'code': 'goi_cham_soc', 'name': 'Gói chăm sóc răng miệng theo năm', 'category': 'policy', 'flow': 'template',
        'keywords': 'gói chăm sóc, gói năm, gói khám định kỳ, thẻ thành viên, gói gia đình, membership',
        'sample_questions': 'Phòng khám có gói chăm sóc theo năm không?\nGói khám định kỳ gồm những gì?\n'
                            'Có gói cho cả gia đình không ạ?',
        'answer_template': 'Dạ phòng khám có các gói chăm sóc răng miệng theo năm ạ:\n{goi_cham_soc}\n'
                           'Gói giúp anh/chị khám và cạo vôi định kỳ đúng hẹn với chi phí tiết kiệm hơn; nhân viên tư vấn '
                           'sẽ giới thiệu chi tiết khi anh/chị đến khám ạ.',
        'quick_replies': 'Đặt lịch khám | Bảng giá',
        'tools': ['get_clinic_info'], 'allow_rephrase': True,
    },
]
