===============================================
DMAG – Dữ liệu demo & giả lập tích hợp
===============================================

Module ``dmag_dental_demo`` biến **một cơ sở dữ liệu thật** (Odoo 17 Bizapps, thường cài **không có dữ liệu
demo của Odoo**) thành môi trường demo / kiểm thử khép kín cho toàn bộ DMAG Dental ERP – giống cách
``social_demo`` của Odoo làm cho ứng dụng Mạng xã hội. Chủ phòng khám cài vào là bấm thử được mọi màn hình:
Bảng điều phối, Bàn làm việc bác sĩ, Chế độ tư vấn, Bảng điều hành mục tiêu, thu tiền QR, đơn thuốc, ký số, labo, kho,
hoa hồng, lương 3P…

.. warning::
   Chỉ cài trên cơ sở dữ liệu dùng để **demo / đào tạo / kiểm thử**. Không dùng cơ sở dữ liệu ở chế độ demo
   để khám chữa bệnh thật.

Cài đặt làm gì?
===============

Dữ liệu được sinh bằng ``post_init_hook`` (Python, chạy lại được), **không** dùng tệp dữ liệu XML demo nên chạy
được cả khi cơ sở dữ liệu cài ``--without-demo``. Mọi chứng từ đi qua **nghiệp vụ thật** của các module
(đặt lịch → xác nhận → check-in → lên ghế → sơ đồ răng → thủ thuật → hoàn tất → ký bệnh án → hóa đơn → thu tiền
tiền mặt / thẻ / chuyển khoản SePay giả lập → tích điểm, hoa hồng, thẻ bảo hành, trừ vật tư, phiếu labo, đơn thuốc
liên thông giả lập, tin ZNS giả lập, khảo sát NPS…) theo đúng thứ tự thời gian – đồng hồ hệ thống được "đóng
băng" tại từng thời điểm (thư viện ``freezegun`` có sẵn trong requirements của Odoo) nên giờ check-in, hóa đơn,
thanh toán, chatter đều khớp thực tế. Hạt giống ngẫu nhiên cố định nên mỗi lần sinh cho cùng một bộ dữ liệu
(tương đối theo ngày hôm nay). Thời gian sinh khoảng 2–3 phút.

1. **Thông tin pháp lý phòng khám** (chỉ điền khi còn trống, không ghi đè giá trị đã khai): mã cơ sở KCB
   ``79999``, số giấy phép hoạt động, người chịu trách nhiệm chuyên môn, địa chỉ, điện thoại; giảm giá tối đa 10 %.
2. **Tích hợp chạy giả lập**: Zalo ZNS chế độ ``mock`` (OA demo); liên thông Đơn thuốc quốc gia chế độ
   ``mock`` (mã liên thông cơ sở + bác sĩ); nhà cung cấp ký số **giả lập** xếp đầu danh sách (không có giá trị
   pháp lý); SePay: ngân hàng ``MBBank``, tài khoản ``0000000000``, chủ tài khoản ``NHA KHOA DMAG DEMO``, API key
   ngẫu nhiên, bật **Chế độ demo** (nút "Giả lập khách chuyển khoản").
3. **Người dùng demo** (mật khẩu ``demo``) gắn hồ sơ nhân sự lâm sàng, nhân viên (hr.employee), ngạch bậc 3P.
4. **Danh mục**: 4 ghế, 25 dịch vụ nha khoa có giá VNĐ (khám, X-quang, CBCT, cạo vôi, nha chu, trám, nội nha,
   nhổ răng khôn, implant Hàn Quốc / Thụy Sĩ, mão sứ, veneer, tẩy trắng – **thẩm mỹ chịu thuế**, chỉnh nha mắc
   cài / khay trong…), dịch vụ y tế tự gán thuế **KCT**; vật tư + định mức (composite, trâm NiTi, thuốc tê, trụ
   implant theo serial…) có tồn kho đầu kỳ; 11 thuốc nha khoa + 4 đơn thuốc mẫu; 3 labo.
5. **Chính sách mẫu** (tên có chữ "(mẫu)" để nhận biết): hoa hồng **đang bật** – bác sĩ 10 % thực thu thủ thuật,
   phụ tá 50.000 đ/ca, tư vấn 3 % kế hoạch đã thu, lễ tân 1 %, người giới thiệu 5 %; hạng thành viên giữ mặc định
   của module (1 điểm / 10.000 đ); gói chăm sóc năm; bảo hành / nhắc tái khám theo dịch vụ; hồ sơ pháp chế
   (giấy phép, bức xạ, kiểm định – một số **sắp hết hạn**, một **đã hết hạn**), thiết bị, mẻ tiệt khuẩn; khung 3P
   dùng dữ liệu mẫu của ``dmag_hr_3p``.
6. **40 bệnh nhân** (CCCD 12 số, ngày sinh, giới, đồng ý xử lý dữ liệu; 3 gia đình có chủ hộ, trẻ dưới 6 tuổi
   có người giám hộ, cảnh báo dị ứng / tim mạch / chống đông, nguồn khách và người giới thiệu); một bệnh nhân có
   tài khoản cổng ``/my/dental``.
7. **Lịch sử 60 ngày** (~4–7 lượt / ngày làm việc): hoàn tất + ký + thu đủ (đa số), thu một phần / trả góp,
   không đến, hủy lịch; kế hoạch điều trị 2 phương án (đã chốt / đang cân nhắc, cầu chì bác sĩ thứ hai cho
   mão sứ / veneer); đơn thuốc phát hành mã 14 ký tự và liên thông giả lập; NPS; phiếu labo (có phiếu trễ hạn);
   vật tư tiêu hao; thẻ bảo hành; điểm và hạng thành viên. **Hôm nay**: bảng điều phối đủ trạng thái (đã đặt,
   đã xác nhận, đã đến, đang điều trị, hoàn tất chờ thu tiền); vài ngày tới có lịch hẹn.
8. Bảng lương 3P **tháng trước – Giám đốc đã duyệt**, tháng này – nháp; bảng kê hoa hồng tháng trước đã chốt.
9. OKR: nếu đã cài ``dmag_okr_dental`` + OKR Scale thì tạo thêm chu kỳ / mục tiêu / KR mẫu.
10. **Mục tiêu kinh doanh** (``dmag_dental_goals``) do Giám đốc demo đặt và chốt: tháng trước, tháng này, quý, năm
    (doanh thu, thực thu, lợi nhuận gộp, khách mới, ca implant, ca chỉnh nha mới, tỷ lệ chốt, thời gian chờ, NPS,
    tỷ lệ đến khám), mức mục tiêu = thực tế tháng trước của dữ liệu demo + 10–20 %; mục tiêu riêng từng bác sĩ
    (doanh thu chia theo tỷ trọng, tỷ lệ chốt, ca implant / chỉnh nha); nhóm theo 3 Objective ("Tăng trưởng doanh
    thu bền vững", "Mở rộng dịch vụ giá trị cao", "Trải nghiệm không đau, không chờ"); một đề xuất của Quản lý cho
    tháng sau đang chờ Giám đốc chốt. Mở **Nha khoa › Điều hành mục tiêu** bằng ``giamdoc.demo``.

Tài khoản demo
==============

==================  =========  ==============================================
Đăng nhập           Mật khẩu   Vai trò
==================  =========  ==============================================
``letan.demo``      ``demo``   Lễ tân / thu ngân
``tuvan.demo``      ``demo``   Tư vấn viên (nhóm lễ tân)
``phuta.demo``      ``demo``   Phụ tá / điều dưỡng
``bacsi.demo``      ``demo``   Bác sĩ bậc 3 (implant, phẫu thuật, phục hình)
``bacsi2.demo``     ``demo``   Bác sĩ bậc 2 (chỉnh nha, răng trẻ em)
``quanly.demo``     ``demo``   Quản lý phòng khám
``giamdoc.demo``    ``demo``   Giám đốc / Quản lý cấp cao
``benhnhan.demo``   ``demo``   Bệnh nhân – cổng ``/my/dental``
==================  =========  ==============================================

Người dùng demo nhận thông báo trong Odoo (không gửi email); email phát sinh trong lúc sinh dữ liệu bị xóa.

Nhận biết chế độ demo
=====================

* Biểu tượng đỏ **"CHẾ ĐỘ DEMO"** trên thanh trên cùng (mọi người dùng nội bộ) – bấm để mở màn hình
  *Dữ liệu demo*.
* Menu **Nha khoa › ⚠ CHẾ ĐỘ DEMO** và **Nha khoa › Cấu hình › Dữ liệu demo** (Quản lý / Giám đốc): tình trạng,
  số lượng bản ghi, tài khoản demo, nút **"Tạo lại dữ liệu demo"** (Quản lý trở lên – xóa dữ liệu demo cũ rồi
  sinh lại, chỉ đụng bản ghi do module sinh ra) và **"Xóa dữ liệu demo"** (Giám đốc).
* Tham số hệ thống ``dmag.demo_mode = 1`` – module khác có thể đọc (ví dụ hiện băng rôn trên Bàn làm việc):
  ``env['dmag.demo'].is_demo_mode()`` hoặc RPC ``dmag.demo.get_demo_status()``.

Gỡ dữ liệu demo
===============

**Ứng dụng → DMAG – Dữ liệu demo & giả lập tích hợp → Gỡ cài đặt.** ``uninstall_hook`` xóa toàn bộ bản ghi có
external id ``dmag_dental_demo.gen_*`` (mọi bản ghi do bộ sinh tạo ra: bệnh nhân, lượt khám, hóa đơn, thanh toán,
đơn thuốc, kho, labo, người dùng demo…), khôi phục giá trị cấu hình cũ đã sao lưu (công ty, SePay, đơn thuốc quốc
gia, Zalo) và tắt ``dmag.demo_mode``. Dữ liệu thật nhập tay trong lúc demo **không** bị xóa – nhưng chứng từ thật
tham chiếu tới dữ liệu demo (ví dụ lượt khám thật của bệnh nhân demo) sẽ giữ lại bản ghi demo đó.

Nếu cơ sở dữ liệu chưa có hệ thống tài khoản, module nạp ``l10n_vn`` (hoặc bộ chung) trước khi sinh dữ liệu – phần
cấu hình kế toán này được giữ lại khi gỡ.

Lưu ý: chứng từ đã khóa theo nguyên tắc "tạo được – không sửa" (hóa đơn đã ghi sổ, sổ điểm, nhật ký truy cập, kho)
được xóa ở mức cơ sở dữ liệu vì đây là dữ liệu mẫu; số thứ tự chứng từ (mã lượt khám, số hóa đơn…) không quay lại.

Kỹ thuật
========

* ``generator/generator.py`` – ``DemoGenerator``; ``generator/purge.py`` – ``DemoPurger``;
  ``generator/data.py`` – dữ liệu mẫu tĩnh (tên, dịch vụ, giá, thuốc, chính sách).
* Gắn external id bằng "mốc id": trước khi sinh lấy ``max(id)`` từng bảng; sau khi sinh mọi bản ghi mới do
  quyền hệ thống / người dùng demo tạo đều được gắn ``gen_*`` (trừ bảng kỹ thuật như ``mail.message``,
  ``account.move.line`` – tự xóa theo bản ghi cha).
* Điểm móc chỉ có hiệu lực trong ngữ cảnh demo: bỏ qua thời hạn lưu trữ bệnh án khi **xóa dữ liệu demo**
  (``dmag_demo_purge``); bệnh án demo cũ hơn 7 ngày chỉ khóa, không dựng PDF ký số (cài nhanh hơn).
* Kiểm thử: ``--test-tags /dmag_dental_demo`` (đăng nhập lễ tân / bác sĩ demo qua RPC, tạo lại idempotent…).
