DMAG Clinic Workspace
=====================

Giao diện vận hành cho người không quen Odoo (tablet-first, nhận diện DMAG):

* **Bảng điều phối** (lễ tân): KPI trong ngày, trạng thái ghế, 5 làn hành trình
  (Sắp đến · Đang chờ · Đang điều trị · Chờ thu tiền · Đã xong), đồng hồ chờ cảnh báo đỏ sau 15 phút,
  check-in / mời lên ghế / hoàn tất / thu tiền bằng 1 chạm. Tự làm mới 30 giây.
* **Bàn làm việc bác sĩ**: danh sách bệnh nhân hôm nay, thẻ bệnh nhân với cảnh báo y khoa, 5 tab:
  Sơ đồ răng · Bệnh án · Kế hoạch điều trị · Thủ thuật hôm nay · Lịch sử.
* **Sơ đồ răng chạm** (SVG): răng vĩnh viễn / hỗn hợp / răng sữa, chạm từng mặt răng, bảng tình trạng màu,
  tóm tắt bệnh lý, lớp kế hoạch dạng gạch chéo.
* **Lập kế hoạch từ sơ đồ**: tự gợi ý dịch vụ theo bệnh lý, 2 phương án song song, tổng tiền tức thời.
* **Chế độ tư vấn**: màn hình quay về phía bệnh nhân, 2 phương án đặt cạnh nhau, trả góp/tháng,
  bệnh nhân tự chọn → lập hợp đồng; in bản tóm tắt.
* **Bảng điều hành mục tiêu** (chủ phòng khám): màn hình và mục tiêu kinh doanh nằm ở module
  ``dmag_dental_goals``; module này giữ hành động ``action_dmag_owner_cockpit`` (đường dẫn cũ vẫn mở được).
