DMAG – Hồ sơ pháp chế
=====================

"Lằn ranh đỏ" pháp lý của phòng khám nha khoa: giấy phép, hành nghề, bức xạ, chất thải, PCCC, thiết bị, tiệt khuẩn.

* **Loại hồ sơ** (danh mục có sẵn, sửa được): giấy phép hoạt động KCB, giấy phép hành nghề, giấy phép tiến hành
  công việc bức xạ, kiểm định X-quang/CBCT, chứng chỉ an toàn bức xạ nhân viên, đo liều cá nhân, hợp đồng xử lý
  chất thải y tế, quy trình KSNK, PCCC, đăng ký kinh doanh, hợp đồng thuê mặt bằng; mỗi loại có số ngày cảnh báo,
  thời hạn gợi ý, "bắt buộc cho thanh tra", căn cứ pháp lý (Luật KCB 15/2023/QH15, NĐ 96/2023, NĐ 142/2020,
  TT 59/2025/TT-BKHCN, TT 20/2021/TT-BYT, TT 16/2018/TT-BYT…).
* **Hồ sơ** ``dmag.compliance.doc``: số hiệu, nơi cấp, ngày cấp / hết hạn (hoặc không thời hạn), bản scan, người
  phụ trách, gắn người hành nghề / thiết bị / đối tác; tình trạng Còn hiệu lực / Sắp hết hạn / Hết hạn (tìm kiếm
  được); nút "Gia hạn" (hồ sơ cũ tự lưu trữ).
* **Thiết bị** ``dmag.equipment`` (ghế, X-quang, Pano, CBCT, autoclave, máy nén khí…): serial, ghế, lịch kiểm định /
  bảo trì (tự tính ngày kế tiếp), tình trạng đạt / sắp đến hạn / quá hạn; **nhật ký** bảo trì – kiểm định – sự cố
  (tạo được – không sửa); kiểm định đạt tự cập nhật ngày.
* **Mẻ tiệt khuẩn** ``dmag.sterilization.batch``: nồi hấp, số chu trình, chương trình, chỉ thị hóa học /
  Bowie-Dick / sinh học, bộ dụng cụ, người vận hành; chỉ phát hành khi chỉ thị hóa học đạt; chỉ thị sinh học
  không đạt sau khi phát hành → **thu hồi** + việc rà soát các lượt khám đã dùng. Lượt khám có tab
  "Kiểm soát nhiễm khuẩn" gắn mẻ hấp.
* **Sẵn sàng thanh tra** ``dmag.compliance.doc.get_compliance_status(company_id=False)`` →
  ``{company_id, date, ready, score, counts{valid, expiring, expired, missing}, documents{valid, expiring, expired},
  equipment{ok, due_soon, overdue}, sterilization{batches_30d, failed_30d, pending_biological},
  red_items[...], expiring_items[...]}``; mỗi mục: ``{kind (document/equipment/sterilization/missing), model, id,
  name, type, category, number, expiry_date, days_left, state, responsible, legal_basis}``.
* Cron hằng ngày tạo việc nhắc cho hồ sơ sắp hết hạn / hết hạn và thiết bị đến hạn kiểm định / bảo trì.

Cần xác nhận
------------

* Module phụ thuộc ``dmag_dental_clinic`` (để gắn mẻ tiệt khuẩn vào lượt khám) – chấp nhận hay tách cầu nối riêng?
* Đề bài ghi "TT 18/2018 kiểm soát nhiễm khuẩn"; theo hiểu biết hiện tại văn bản KSNK là **TT 16/2018/TT-BYT** – cần
  đối chiếu văn bản gốc.
* Chu kỳ kiểm định X-quang / CBCT, thời hạn giấy phép bức xạ, chu kỳ đọc liều kế theo TT 59/2025/TT-BKHCN;
  văn bản PCCC áp dụng cho phòng khám – cần đối chiếu (đang để thời hạn gợi ý, sửa được trong danh mục).
* Loại hồ sơ nào là "bắt buộc cho thanh tra" và số ngày cảnh báo cho từng loại.
* Hạn dùng gói dụng cụ sau hấp (mặc định 30 ngày nếu không nhập).
* Giấy phép hành nghề: đang dùng song song với ngày hết hạn trên "Nhân sự lâm sàng" (cron của ``dmag_dental_base``);
  có cần đồng bộ hai chiều?
