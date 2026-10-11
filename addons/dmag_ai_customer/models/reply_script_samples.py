"""Bộ kịch bản trả lời mẫu (tiếng Việt) cho trợ lý Zalo – nạp ở trạng thái NHÁP; Giám đốc đọc, sửa, rồi duyệt.

Câu chữ y khoa ở đây chỉ là hướng dẫn chung, không chẩn đoán; kịch bản "đau sau nhổ răng" gửi mẫu an toàn rồi chuyển
nhân viên / bác sĩ.
"""

SAMPLE_SCRIPTS = [
    {
        'code': 'gia_dich_vu', 'name': 'Giá dịch vụ', 'category': 'price', 'flow': 'template',
        'keywords': 'giá, bao nhiêu tiền, chi phí, bảng giá, báo giá, hết bao nhiêu',
        'sample_questions': 'Cạo vôi răng giá bao nhiêu ạ?\nTrám răng hết bao nhiêu tiền?\nCho em xin bảng giá\n'
                            'Chi phí bọc răng sứ khoảng bao nhiêu?\nImplant giá thế nào ạ?',
        'answer_template': 'Dạ {ten_khach} ơi, giá niêm yết của phòng khám:\n{gia_dich_vu}\n'
                           'Chi phí chính xác bác sĩ sẽ tư vấn sau khi khám ạ. Anh/chị muốn em giữ chỗ lịch khám không ạ?',
        'quick_replies': 'Đặt lịch khám | Giờ làm việc | Địa chỉ',
        'tools': ['search_services'], 'services': ['Khám & tư vấn', 'Cạo vôi'], 'allow_rephrase': True,
    },
    {
        'code': 'gio_mo_cua', 'name': 'Giờ mở cửa / lịch làm việc', 'category': 'info', 'flow': 'template',
        'keywords': 'mấy giờ, giờ mở cửa, giờ làm việc, mở cửa, đóng cửa, chủ nhật, nghỉ lễ, ngày lễ',
        'sample_questions': 'Phòng khám mở cửa mấy giờ ạ?\nChủ nhật có làm việc không?\nMấy giờ đóng cửa vậy?\n'
                            'Lễ có nghỉ không ạ?',
        'answer_template': 'Dạ phòng khám làm việc: {gio_lam_viec}.\n{ngay_nghi_sap_toi}\nHotline: {hotline}. '
                           'Anh/chị muốn em xem giờ trống để giữ chỗ không ạ?',
        'quick_replies': 'Xem giờ trống | Đặt lịch khám | Địa chỉ',
        'tools': ['get_clinic_info'], 'allow_rephrase': True,
    },
    {
        'code': 'dia_chi_do_xe', 'name': 'Địa chỉ & chỗ đỗ xe', 'category': 'info', 'flow': 'template',
        'keywords': 'địa chỉ, ở đâu, chỗ nào, đường nào, chỉ đường, gửi xe, đậu xe, đỗ xe, ô tô, bãi xe',
        'sample_questions': 'Phòng khám ở đâu vậy ạ?\nCho xin địa chỉ\nCó chỗ đậu ô tô không?\nGửi xe máy ở đâu ạ?',
        'answer_template': 'Dạ địa chỉ phòng khám: {dia_chi}.\n{gui_xe}\nCần chỉ đường anh/chị gọi hotline {hotline} ạ.',
        'quick_replies': 'Giờ làm việc | Đặt lịch khám',
        'tools': ['get_clinic_info'], 'allow_rephrase': True,
    },
    {
        'code': 'dat_lich', 'name': 'Đặt lịch khám', 'category': 'booking', 'flow': 'booking',
        'keywords': 'đặt lịch, đặt hẹn, hẹn lịch, giữ chỗ, lấy lịch, đăng ký khám, còn lịch, lịch trống, giờ trống',
        'sample_questions': 'Cho em đặt lịch cạo vôi chiều mai\nMình muốn đặt lịch khám thứ 7\n'
                            'Còn lịch trống chiều nay không ạ?\nĐặt hẹn khám răng giúp em',
        'answer_template': 'Dạ em giữ chỗ giúp anh/chị ạ. Giờ còn trống gần nhất: {gio_trong}.\n'
                           'Anh/chị chọn giờ và cho em xin họ tên, số điện thoại – lịch sẽ được lễ tân gọi xác nhận.',
        'quick_replies': 'Chiều nay | Sáng mai | Thứ 7',
        'tools': ['search_services', 'get_free_slots', 'find_patient_by_phone', 'book_appointment', 'get_clinic_info'],
    },
    {
        'code': 'doi_huy_lich', 'name': 'Đổi / hủy lịch hẹn', 'category': 'booking', 'flow': 'handoff',
        'handoff_reason': 'human_request',
        'keywords': 'đổi lịch, dời lịch, hủy lịch, huỷ lịch, hủy hẹn, không đến được, đổi giờ, lùi lịch',
        'sample_questions': 'Em muốn đổi lịch hẹn sang ngày khác\nCho mình hủy lịch hẹn mai nhé\n'
                            'Mai em bận không đến được, dời lịch giúp em',
        'answer_template': 'Dạ em đã ghi nhận yêu cầu đổi / hủy lịch của {ten_khach}. Lễ tân sẽ nhắn xác nhận lại trong '
                           'giờ làm việc ({gio_lam_viec}) ạ. Giờ còn trống gần nhất để anh/chị tham khảo: {gio_trong}.',
        'tools': ['get_clinic_info', 'get_free_slots', 'handoff_to_staff'],
    },
    {
        'code': 'chuan_bi_kham', 'name': 'Chuẩn bị trước khi khám', 'category': 'info', 'flow': 'template',
        'keywords': 'chuẩn bị, mang theo, cần mang, nhịn ăn, trước khi khám, giấy tờ',
        'sample_questions': 'Đi khám cần mang theo gì ạ?\nCó phải nhịn ăn trước khi nhổ răng không?\n'
                            'Trước khi khám cần chuẩn bị gì?',
        'answer_template': 'Dạ trước khi đến anh/chị chuẩn bị giúp em: {chuan_bi}\nCần hỗ trợ thêm anh/chị gọi {hotline} ạ.',
        'quick_replies': 'Đặt lịch khám | Địa chỉ',
        'tools': ['get_clinic_info'], 'allow_rephrase': True,
    },
    {
        'code': 'bao_hanh', 'name': 'Chính sách bảo hành', 'category': 'policy', 'flow': 'template',
        'keywords': 'bảo hành, bao lâu thì hỏng, hư thì sao, thẻ bảo hành',
        'sample_questions': 'Răng sứ bảo hành bao lâu ạ?\nImplant có bảo hành không?\nTrám răng bị bong có bảo hành không?',
        'answer_template': 'Dạ các dịch vụ phục hình (răng sứ, implant, trám…) có thẻ bảo hành điện tử theo từng dịch '
                           'vụ, thời hạn ghi trên thẻ và trong hồ sơ của anh/chị. Khi có vấn đề anh/chị mang theo CCCD '
                           'đến phòng khám ({gio_lam_viec}) để bác sĩ kiểm tra ạ.',
        'quick_replies': 'Đặt lịch kiểm tra | Hotline',
        'tools': ['get_clinic_info'], 'allow_rephrase': True,
    },
    {
        'code': 'tra_gop', 'name': 'Trả góp & thanh toán', 'category': 'policy', 'flow': 'template',
        'keywords': 'trả góp, góp, thanh toán, quẹt thẻ, chuyển khoản, trả trước',
        'sample_questions': 'Có trả góp không ạ?\nNiềng răng trả góp được không?\nCó quẹt thẻ được không?',
        'answer_template': 'Dạ phòng khám nhận: {thanh_toan}\nĐiều kiện trả góp cụ thể nhân viên tư vấn sẽ báo khi '
                           'anh/chị đến khám ạ.',
        'quick_replies': 'Bảng giá | Đặt lịch tư vấn',
        'tools': ['get_clinic_info'], 'allow_rephrase': True,
    },
    {
        'code': 'dau_sau_nho_rang', 'name': 'Đau sau nhổ răng (mẫu an toàn + chuyển nhân viên)', 'category': 'safety',
        'flow': 'handoff', 'handoff_reason': 'medical_question',
        'keywords': 'sau nhổ, nhổ răng xong, nhổ răng khôn xong, vừa nhổ, mới nhổ, sau khi nhổ',
        'sample_questions': 'Em mới nhổ răng khôn hôm qua giờ còn đau\nNhổ răng xong bị đau có sao không ạ?\n'
                            'Sau nhổ răng ê nhức quá phải làm sao',
        'answer_template': 'Dạ đau, ê nhẹ trong 2–3 ngày đầu sau nhổ răng là thường gặp. Anh/chị nghỉ ngơi, chườm lạnh '
                           'bên má, ăn đồ mềm nguội, không súc miệng mạnh và dùng thuốc đúng đơn bác sĩ đã kê ạ.\n'
                           'Em đã chuyển cho bác sĩ / nhân viên trực để gọi lại hỏi thăm. Nếu chảy máu không cầm, sưng '
                           'lan, sốt cao hoặc khó thở, anh/chị gọi ngay {hotline} hoặc đến cơ sở y tế gần nhất ạ.',
        'tools': ['get_clinic_info', 'handoff_to_staff'],
    },
    {
        'code': 'nieng_rang', 'name': 'Niềng răng – tư vấn chung', 'category': 'consult', 'flow': 'template',
        'keywords': 'niềng, chỉnh nha, mắc cài, khay trong, invisalign, răng hô, răng móm, răng lệch',
        'sample_questions': 'Niềng răng mất bao lâu ạ?\nEm muốn tư vấn niềng răng\nRăng hô có niềng được không?\n'
                            'Niềng răng trong suốt giá khoảng bao nhiêu?',
        'answer_template': 'Dạ thời gian và phương pháp niềng (mắc cài hay khay trong) bác sĩ chỉnh nha chỉ xác định được '
                           'sau khi khám, chụp phim và lấy dấu ạ. Tham khảo giá niêm yết:\n{gia_dich_vu}\n'
                           'Phòng khám có hỗ trợ trả góp. Anh/chị muốn đặt lịch tư vấn chỉnh nha không ạ?',
        'quick_replies': 'Đặt lịch tư vấn | Trả góp',
        'tools': ['search_services', 'get_clinic_info'], 'services': ['Niềng răng'], 'allow_rephrase': True,
    },
    {
        'code': 'tay_trang', 'name': 'Tẩy trắng răng', 'category': 'consult', 'flow': 'template',
        'keywords': 'tẩy trắng, trắng răng, răng ố, răng vàng, làm trắng',
        'sample_questions': 'Tẩy trắng răng giá bao nhiêu?\nRăng em bị ố vàng muốn làm trắng\n'
                            'Tẩy trắng có hại men răng không?',
        'answer_template': 'Dạ tẩy trắng tại phòng khám thực hiện sau khi bác sĩ kiểm tra răng, nướu (cạo vôi trước nếu '
                           'cần) để an toàn cho men răng. Giá niêm yết:\n{gia_dich_vu}\n'
                           'Anh/chị muốn em giữ chỗ lịch khám không ạ? Giờ trống gần nhất: {gio_trong}.',
        'quick_replies': 'Đặt lịch khám | Bảng giá',
        'tools': ['search_services', 'get_free_slots'], 'services': ['Tẩy trắng'], 'allow_rephrase': True,
    },
    {
        'code': 'kham_tre_em', 'name': 'Khám răng cho trẻ em', 'category': 'consult', 'flow': 'template',
        'keywords': 'trẻ em, cho bé, cho con, em bé, răng sữa, bé nhà, trẻ con, con tôi',
        'sample_questions': 'Phòng khám có khám cho bé 5 tuổi không?\nCon em bị sâu răng sữa\n'
                            'Bé nhà mình mấy tuổi thì nên đi khám răng?',
        'answer_template': 'Dạ phòng khám có khám và điều trị răng cho trẻ em ạ. Bé đi cùng bố/mẹ hoặc người giám hộ, '
                           'mang theo giấy khai sinh / mã định danh của bé. Giá khám tham khảo:\n{gia_dich_vu}\n'
                           'Giờ trống gần nhất: {gio_trong}. Anh/chị muốn em giữ chỗ không ạ?',
        'quick_replies': 'Đặt lịch cho bé | Địa chỉ',
        'tools': ['search_services', 'get_free_slots'], 'services': ['Khám & tư vấn'], 'allow_rephrase': True,
    },
]
