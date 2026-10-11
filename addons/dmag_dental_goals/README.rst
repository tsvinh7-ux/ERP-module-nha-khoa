================================================================
DMAG – Điều hành mục tiêu (Mục tiêu kinh doanh · OKR · KPI)
================================================================

Màn hình **Nha khoa › Điều hành mục tiêu** (Quản lý phòng khám / Giám đốc) – *Bảng điều hành mục tiêu*: mọi con số
đều được đặt cạnh **mục tiêu** do Giám đốc chốt, **tiến độ** theo thời gian và **dự báo cuối kỳ**, để chủ phòng khám
bám đuổi mục tiêu và thấy bức tranh toàn cảnh thay vì đọc số liệu chung chung.

Mục tiêu kinh doanh (``dmag.business.target``)
==============================================

*Nha khoa › Cấu hình › Mục tiêu kinh doanh*. Mỗi dòng: phòng khám, **kỳ** (tháng / quý / năm – ngày bắt đầu tự đưa
về đầu kỳ), **chỉ số**, **giá trị mục tiêu**, bác sĩ (để trống = toàn phòng khám), người phụ trách,
**Mục tiêu (Objective)** để nhóm thành OKR, ghi chú / sáng kiến.

* Quyền: Quản lý được xem và soạn **đề xuất**; chỉ **Giám đốc / Quản lý cấp cao** được **Chốt**. Sau khi chốt, chỉ
  Giám đốc sửa / xóa (nguyên tắc "tạo được – không sửa"). Lễ tân, phụ tá, bác sĩ không xem được.
* Bảng điều hành chỉ dùng mục tiêu **đã chốt**. Xem quý / năm mà chưa đặt mục tiêu quý / năm: chỉ số cộng dồn lấy
  tổng mục tiêu các tháng (đủ cả 3 / 12 tháng), chỉ số tỷ lệ lấy trung bình (nhãn "cộng từ kỳ nhỏ").
* Chưa đặt mục tiêu: chỉ số có **chuẩn DMAG** dùng chuẩn (nhãn "chuẩn DMAG": chốt kế hoạch ≥ 60 %, đến khám ≥ 85 %,
  chờ ≤ 15 phút, công suất ghế chiều ≥ 65 %, NPS ≥ 50, khiếu nại ≤ 2 %, ca bác sĩ phụ ≥ 50 %, giá vốn vật tư + labo
  ≤ ngưỡng công ty / 22 %); chỉ số khác hiện "Chưa đặt mục tiêu" – không tự bịa mục tiêu.

Chỉ số và cách tính
===================

Thực tế tính theo **giờ địa phương**, chỉ trên các phòng khám đang chọn (đa công ty), một hàm cho mỗi chỉ số trong
``dmag.goal.engine`` (``_metric_<khóa>``; RPC ``get_metric_value(metric, date_from, date_to, doctor_id)``).

==========================  =============================================================================
Chỉ số                      Cách tính
==========================  =============================================================================
Doanh thu dịch vụ           Σ thành tiền thủ thuật hoàn tất, theo ngày lượt khám
Thực thu                    Σ nhật ký thu tiền (``dmag_payment_sepay``) theo ngày thu; chưa cài → phiếu thu kế toán
Khách mới                   Lượt khám hoàn tất của khách lần đầu điều trị
Ca implant                  Số trụ: thủ thuật nhóm Implant hoàn tất, tính theo răng
Ca chỉnh nha mới            Khách có thủ thuật chỉnh nha hoàn tất đầu tiên trong kỳ
Tỷ lệ chốt kế hoạch         Kế hoạch được đồng ý / kế hoạch đã tư vấn (ngày lập trong kỳ)
Lợi nhuận gộp               Doanh thu − vật tư tiêu hao − chi phí labo (theo ngày gửi) − hoa hồng hợp lệ
Lịch hẹn → Đến khám         Đến / (đến + không đến)
Được tư vấn                 Khách được tư vấn kế hoạch / khách đã đến
Hoàn tất điều trị           Kế hoạch hoàn thành / kế hoạch đã chốt (cùng nhóm lập trong kỳ)
Tái khám đúng hẹn           Khách cũ: đến / (đến + không đến)
Giới thiệu                  Khách mới có người giới thiệu hoặc nguồn "giới thiệu" / khách mới
Thời gian chờ               TB (giờ lên ghế − giờ check-in)
Công suất ghế sáng / chiều  Phút có lịch trong giờ mở cửa trước / sau 12:00 ÷ (số ghế × phút mở cửa của các ngày
                            làm việc đã qua) – theo Lịch làm việc phòng khám (mặc định 08:00–12:00 / 13:30–20:00)
NPS                         % ủng hộ (9–10) − % không hài lòng (0–6)
Tỷ lệ khiếu nại             Phiếu phàn nàn / lượt hoàn tất
Ca do bác sĩ phụ            Thủ thuật do bác sĩ bậc 1–2 / tổng thủ thuật
Giá vốn vật tư + labo       (Vật tư + labo) / doanh thu
==========================  =============================================================================

Khung "mục tiêu – thực tế – nhịp độ"
====================================

* **% đạt** = thực tế / mục tiêu; **% kỳ đã qua** theo ngày làm việc của **Lịch làm việc phòng khám**
  (``dmag.clinic.schedule``: thứ nghỉ, ngày nghỉ lễ / đột xuất không tính; mặc định thứ Hai – thứ Bảy).
* **Dự báo cuối kỳ** (chỉ số cộng dồn) = thực tế ÷ ngày làm việc đã qua × tổng ngày làm việc của kỳ.
* **Còn thiếu** = mục tiêu − thực tế; **cần thêm / ngày** = còn thiếu ÷ ngày làm việc còn lại.
* **Trạng thái**: *Đúng tiến độ* (dự báo ≥ 100 % mục tiêu) · *Chậm* (90–100 %) · *Nguy cơ* (< 90 %) · *Đã đạt* ·
  *Không đạt* (kỳ đã kết thúc). Chỉ số tỷ lệ so trực tiếp giá trị hiện tại (càng thấp càng tốt: đảo chiều; NPS:
  thiếu ≤ 10 điểm = Chậm).
* **Xu hướng** 6 kỳ gần nhất (điểm rỗng = kỳ đang chạy) và chênh lệch **so với cùng thời điểm kỳ trước**.

Màn hình
========

1. **Mục tiêu kinh doanh** – 7 thẻ north-star: doanh thu, thực thu, khách mới, ca implant, ca chỉnh nha mới,
   tỷ lệ chốt kế hoạch, lợi nhuận gộp (thanh: thực tế · dự báo · vạch mục tiêu · vạch nhịp cần đạt hôm nay).
2. **OKR** – nếu cài ``dmag_okr_dental`` + OKR Scale: Objective → KR (tiến độ, trạng thái, độ tự tin, người phụ
   trách) của chu kỳ trùng kỳ đang xem, chỉ số cầu chì vượt ngưỡng tô đỏ; luôn kèm OKR từ mục tiêu kinh doanh
   (nhóm theo trường *Mục tiêu (Objective)*).
3. **KPI hành trình khách hàng** – phễu Đặt lịch → Đến khám → Được tư vấn → Chốt kế hoạch → Hoàn tất điều trị
   (tỷ lệ chuyển đổi so mục tiêu), tái khám đúng hẹn, giới thiệu; KPI dịch vụ: thời gian chờ, công suất ghế
   sáng / chiều, NPS, khiếu nại, ca bác sĩ phụ, giá vốn.
4. **KPI theo người / bộ phận** – bảng điểm bác sĩ (doanh thu so mục tiêu riêng, dự báo, tỷ lệ chốt, NPS, lượt,
   khách mới, lãi gộp, mục tiêu riêng khác); KPI theo vị trí từ lương 3P (``dmag.kpi.result``) nếu đã cài.
5. **Sức khỏe tài chính & cảnh báo** – thác nước doanh thu → vật tư → labo → hoa hồng → lãi gộp, thực thu /
   doanh thu, công nợ phải thu & quá hạn, giá vốn; cảnh báo (mục tiêu nguy cơ, phễu thấp, công nợ quá hạn, labo
   trễ, phàn nàn chưa xử lý, pháp chế ``get_compliance_status``, cầu chì OKR) – **mỗi cảnh báo có "Việc cần làm"
   và nút mở đúng danh sách**.

Bấm thẻ / dòng → mở chứng từ gốc (lọc đúng kỳ, bác sĩ). Một RPC duy nhất:
``dmag.goal.dashboard.get_goal_dashboard(period_type, date_ref, company_id=False)``.

Kỹ thuật
========

* Phụ thuộc ``dmag_clinic_workspace``; tích hợp mềm (``'model' in env``): ``dmag_payment_sepay``,
  ``dmag_dental_stock``, ``dmag_dental_lab``, ``dmag_dental_commission``, ``dmag_dental_journey``,
  ``dmag_dental_compliance``, ``dmag_hr_3p``, ``dmag_okr_dental`` / OKR Scale.
* Hành động ``dmag_clinic_workspace.action_dmag_owner_cockpit`` (đường dẫn cũ) mở màn hình này
  (thẻ client ``dmag_goal_dashboard``).
* Kiểm thử: ``--test-tags /dmag_dental_goals``.
