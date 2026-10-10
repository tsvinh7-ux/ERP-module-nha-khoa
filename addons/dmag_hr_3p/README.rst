=============================================
DMAG – Ngạch bậc P/M & Lương 3P (bản demo)
=============================================

Thu nhập = **P1 (Vị trí) + P2 (Năng lực) + P3 (Kết quả)**. Module dựng cấu trúc dữ liệu ngạch
**P (chuyên môn)** và **M (quản lý)**, hồ sơ vị trí, đánh giá năng lực, KPI và **bảng đầu vào lương
3P** theo tháng. Không phụ thuộc ``hr_payroll`` (Enterprise): bảng được xuất CSV/XLSX để
Payroll Bizapps nhập làm khoản thu nhập (thuế TNCN, bảo hiểm vẫn do Payroll tính).

Chức năng
=========
* ``dmag.job.grade``: bậc P1…P6 / M1…M4, khung P1 tối thiểu / chuẩn / tối đa.
* ``dmag.job.position.profile`` (theo ``hr.job``): bậc được phép, bậc khởi điểm, tiêu chí P2
  (``dmag.competency`` + trọng số; tiêu chí lâm sàng gợi ý điểm theo **bậc lâm sàng** hoặc
  **giấy phép & phạm vi hành nghề**), bộ KPI P3 (``dmag.kpi.definition``: trọng số, mục tiêu,
  chiều đánh giá, nguồn dữ liệu ``manual | nps | retention | wait_time | revenue | okr_score | commission``),
  mức chuẩn P2, P3, thưởng OKR tối đa.
* Hồ sơ nhân viên (tab *Lương 3P*): ngạch, bậc, P1 (mặc định = mức chuẩn của bậc, phải nằm trong khung),
  lịch sử đánh giá năng lực → hệ số P2.
* ``dmag.competency.assessment``: chấm 1–5 theo tiêu chí, **hệ số P2 = điểm bình quân có trọng số /
  điểm chuẩn** (mặc định 3,0 – cấu hình ở công ty). Đã chốt → chỉ Giám đốc sửa.
* ``dmag.kpi.result``: kết quả KPI tháng; nguồn tự động không cho sửa tay (chống "làm đẹp số").
  % hoàn thành áp trần (mặc định 120%); KPI "càng thấp càng tốt" tính = mục tiêu / thực tế.
* ``dmag.pay3p.sheet`` (tháng, phòng khám): **Nháp → Quản lý đã soát → Giám đốc đã duyệt → Đã xuất**.
  Sau khi Giám đốc duyệt **chỉ Giám đốc được sửa / mở lại**.

Công thức dòng lương
====================
* P1 = ``dmag_p1_amount`` của nhân viên.
* P2 = mức P2 chuẩn của vị trí × hệ số P2 (đánh giá đã chốt gần nhất ≤ cuối tháng; chưa có → 1,0).
* P3 = mức P3 chuẩn × điểm KPI (%) + hoa hồng/thủ thuật phí (từ ``dmag_dental_commission`` nếu cài –
  phụ thuộc mềm) + thưởng OKR (thưởng tối đa × min(điểm OKR / 70%, 1) – điểm OKR lấy từ OKR Scale nếu cài)
  + điều chỉnh (âm khi khấu trừ do vi phạm cầu chì y đức).

Đặc tả cột xuất cho Payroll
===========================

CSV UTF-8 có BOM hoặc XLSX; dòng 1 là mã cột (XLSX có thêm dòng 2 là tên tiếng Việt).

=================  ===================================================
Mã cột             Nội dung
=================  ===================================================
PERIOD             Kỳ lương ``YYYY-MM``
COMPANY            Phòng khám
EMP_CODE           Mã nhân viên (Badge ID / ``barcode`` của nhân viên; trống → ``NV<id>``)
EMP_NAME           Họ tên
JOB                Chức danh
TRACK              Ngạch P / M
GRADE              Mã bậc (P1…, M1…)
DMAG_P1            P1 – Lương vị trí
DMAG_P2_COEF       Hệ số năng lực P2
DMAG_P2            P2 – Lương năng lực
DMAG_P3_KPI_SCORE  Điểm KPI (%)
DMAG_P3_KPI        P3 – Thưởng KPI
DMAG_P3_COMM       P3 – Hoa hồng / thủ thuật phí
DMAG_P3_OKR        P3 – Thưởng OKR
DMAG_P3_ADJ        P3 – Điều chỉnh
DMAG_P3            P3 – Tổng lương kết quả
DMAG_3P_TOTAL      Tổng thu nhập 3P
=================  ===================================================

Trên Payroll Bizapps: tạo *Loại đầu vào* (Other Input Type) với mã ``DMAG_P1``, ``DMAG_P2``,
``DMAG_P3`` (hoặc chi tiết ``DMAG_P3_KPI``/``DMAG_P3_COMM``/``DMAG_P3_OKR``) và quy tắc lương
``result = inputs.DMAG_P1.amount`` … rồi nhập file theo ``EMP_CODE`` + ``PERIOD``.

Nạp khung P/M chuẩn (không sửa code)
====================================
Dữ liệu đi kèm là **dữ liệu mẫu – sẽ thay bằng khung P/M chuẩn của DMAG** (cờ *Dữ liệu mẫu*).
Khi DMAG chốt khung, dùng *Nhập* (Import) chuẩn của Odoo trên từng danh mục:

1. *Ngạch bậc & khung P1*: ``code, name, track (P/M), level, wage_min, wage_mid, wage_max``.
2. *Tiêu chí năng lực*: ``code, name, basis, level_1..level_5``.
3. *Hồ sơ vị trí*: ``job_id`` (tên chức danh), ``track``, ``grade_ids`` (mã bậc, phân cách dấu phẩy),
   ``default_grade_id``, ``p2_base, p3_base, okr_bonus_base``,
   ``competency_line_ids/competency_id``, ``competency_line_ids/weight``,
   ``kpi_ids/name, kpi_ids/weight, kpi_ids/target, kpi_ids/direction, kpi_ids/data_source, kpi_ids/scope``.
4. Sau đó lưu trữ (archive) các bản ghi mẫu.

Phân quyền
==========
* Menu *Nha khoa › Nhân sự 3P* cho **Quản lý phòng khám** (module gán thêm nhóm *Nhân viên: Cán bộ*
  cho nhóm Quản lý để đọc hồ sơ nhân viên).
* Quản lý: soát bảng, nhập KPI tay, đánh giá năng lực. Giám đốc: duyệt, sửa sau duyệt, mở lại.

Cần xác nhận
============
* Khung P/M chuẩn của DMAG: số bậc từng ngạch, khung P1, mức P2/P3 chuẩn, tiêu chí & thang điểm.
* Cách quy đổi điểm năng lực → hệ số P2 (hiện tuyến tính, điểm chuẩn 3/5 = 1,0) và trần KPI 120%.
* Công thức thưởng OKR (ngưỡng 70% nhận đủ) và có cộng hoa hồng vào P3 hay trả riêng.
* Mã nhân viên dùng khi nhập Payroll (Badge ID hay mã khác) và mã Loại đầu vào trên Payroll Bizapps.
* Có cho Quản lý phòng khám quyền *Nhân viên: Cán bộ* hay tách nhóm HR riêng.
