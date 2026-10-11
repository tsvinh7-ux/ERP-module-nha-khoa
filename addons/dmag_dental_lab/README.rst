DMAG – Labo
===========

Phiếu gửi labo cho phục hình gia công ngoài (mão/cầu sứ, abutment, hàm tháo lắp, khay chỉnh nha, máng…).

* Đối tác labo: đánh dấu "Là labo nha khoa" trên liên hệ, thời gian gia công chuẩn để gợi ý hạn trả.
* Phiếu labo: bệnh nhân, lượt khám lấy dấu, dòng kế hoạch, răng, màu răng (Vita), vật liệu,
  lấy dấu thường / scan (mã file), chỉ định, đính kèm ảnh/STL.
* Luồng: Nháp → Đã gửi → Labo đang làm → Đang thử (thử sườn / thử sứ) → Đã nhận → Đã gắn;
  nhánh **Làm lại** (lý do, trách nhiệm, tự mở phiếu mới) và **Hủy**.
* Gửi labo → tự sinh và xác nhận **đơn mua** (quyền hệ thống) cho chi phí labo → hóa đơn nhà cung cấp, công nợ labo.
* Trễ hạn: cờ ``is_late`` (tìm kiếm được), cron hằng ngày tạo việc nhắc cho bác sĩ / người lập phiếu.
* Phân quyền "tạo được – không sửa": phụ tá / bác sĩ tạo và gửi phiếu; sau khi gửi chỉ Giám đốc sửa chi phí,
  labo, hủy phiếu. Trạng thái chỉ đổi qua nút quy trình.
* KPI cho Bảng điều hành mục tiêu: ``dmag.lab.order.get_lab_kpis(date_from, date_to, company_id=False)`` →
  ``{lab_cost, revenue, lab_cost_ratio (%), threshold, alert, order_count, open_count, late_count,
  remake_count, on_time_rate, currency, company_id, date_from, date_to}``.

Cần xác nhận
------------

* Doanh thu dùng để tính % labo: hiện là giá trị thủ thuật đã hoàn tất theo ngày lượt khám (chưa phải thực thu /
  doanh thu kế toán). Chi phí labo ghi nhận theo **ngày gửi**; có nên ghi theo ngày nhận / hóa đơn labo?
* Ngưỡng cảnh báo dùng chung "Giá vốn ≤ 22%" (lấy từ ``dmag_cogs_threshold`` nếu cài ``dmag_dental_stock``)
  hay đặt ngưỡng riêng cho labo?
* Đơn mua labo không áp thuế mặc định – kế toán xác nhận thuế GTGT đầu vào của labo.
* Làm lại do lỗi labo: có tạo đơn mua mới (0 đồng) hay giữ nguyên đơn cũ?
