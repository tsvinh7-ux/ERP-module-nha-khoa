DMAG – Khách hàng thân thiết
============================

Loyalty "chăm sóc, không ép mua" cho phòng khám nha khoa (thiết kế mục 5.2 – ``docs/DE_XUAT_DENTAL_ERP.md``).
Chỉ phụ thuộc ``dmag_dental_clinic`` – **không** cần app Loyalty của Odoo (giữ nhẹ cho bản CE).

Chức năng
---------

* **Hạng thành viên** ``dmag.loyalty.tier``: Thành viên → Bạc → Vàng → Kim cương. Ngưỡng theo
  *thực thu 12 tháng* và / hoặc *điểm gắn bó 12 tháng* (tái khám đúng hẹn, giới thiệu, khảo sát),
  điều kiện "một trong hai" / "cả hai". Quyền lợi: ưu tiên giờ đẹp, miễn phí phim kiểm tra,
  bảo hành mở rộng (tháng), quà sinh nhật, màu thẻ.
* **Tài khoản thành viên** trên bệnh nhân: hạng, điểm khả dụng, thực thu 12 tháng / tích lũy
  (từ các khoản thu khách hàng đã ghi sổ – ``account.payment``, đọc bằng quyền hệ thống).
  Xét hạng hằng đêm (cron) và ngay khi thanh toán.
* **Ví gia đình** (cấu hình công ty ``dmag_loyalty_family_pool``): bệnh nhân cùng ``dental_family_id``
  dùng chung hạng (xét trên tổng thực thu / gắn bó của cả nhà) và chung số dư điểm.
* **Sổ điểm** ``dmag.loyalty.ledger`` chỉ ghi thêm (không sửa / xóa), khóa ``source_key`` duy nhất
  để lũy đẳng. Lý do: thanh toán, tái khám đúng hẹn, giới thiệu, khảo sát / NPS, đổi điểm, điều chỉnh.
  Điều chỉnh tay chỉ Giám đốc / Quản lý cấp cao.
* **Quy tắc tích điểm** theo công ty (tab "Khách hàng thân thiết" trên công ty): 1 điểm / 10.000 ₫ thực thu,
  +50 tái khám đúng hẹn (± 14 ngày quanh ngày hẹn suy ra từ ``recall_months`` của dịch vụ lần trước),
  +200 người giới thiệu / +100 người được giới thiệu, +20 khảo sát.
* **Điểm móc hành trình**: ``_dmag_journey_event('paid')`` → tích điểm theo *từng khoản thu*
  (``payment:<id>`` – thu nhiều lần thì mỗi lần một bút toán, bắn lại sự kiện không cộng trùng),
  thưởng giới thiệu 2 chiều khi lượt khám của người được giới thiệu đã thanh toán đủ (mỗi bên 1 lần),
  xét lại hạng. ``_dmag_journey_event('done')`` → thưởng tái khám đúng hẹn.
* **Voucher** ``dmag.loyalty.voucher``: đổi điểm (trừ điểm ngay, giữ chỗ), trên ngưỡng điểm cần Quản lý duyệt,
  từ chối / hủy thì hoàn điểm. Voucher quà tặng (số tiền hoặc %) do Quản lý phát hành và duyệt; voucher % vượt
  ``dmag_max_discount`` cần Giám đốc. Áp vào lượt khám bằng ``visit.dmag_apply_voucher(code)``: thêm dòng giảm giá
  vào đơn bán của lượt (quyền hệ thống), dùng một lần, khóa dòng ``FOR UPDATE`` chống áp trùng.
* **Cầu chì y đức**: voucher hiệu lực tối thiểu 7 ngày (ràng buộc) – không có ưu đãi "chỉ hôm nay";
  mọi ưu đãi hiển thị minh bạch trong tài khoản bệnh nhân.
* **Gói chăm sóc định kỳ** ``dmag.care.plan`` (giá, thời hạn tháng, quyền lợi: dịch vụ × số lần) và thuê bao
  ``dmag.care.subscription`` (kích hoạt → sinh quyền lợi + đơn bán + hóa đơn; ``register_payment`` tại quầy có tích điểm).
  ``visit.dmag_use_care_entitlement(procedure_id)``: thủ thuật về 0 đồng, ghi ``dmag.care.usage``, trừ quyền lợi.
* **Dữ liệu tổng hợp** ``res.partner.get_loyalty_summary(partner_id)`` cho giao diện nội bộ / cổng bệnh nhân / app.

Phân quyền ("tạo được – không sửa")
-----------------------------------

* Lễ tân: xem hạng, sổ điểm, voucher; đổi điểm; áp voucher / quyền lợi gói; tạo & kích hoạt thuê bao.
  Không sửa voucher / thuê bao đã phát hành, không ghi sổ điểm tay.
* Quản lý phòng khám: cấu hình hạng, gói; phát hành voucher quà tặng; duyệt / từ chối voucher.
* Giám đốc / Quản lý cấp cao: điều chỉnh điểm, hủy voucher / thuê bao, sửa chứng từ.
* Record rule theo ``company_id``.

API cho module khác
-------------------

::

    partner._dmag_loyalty_recompute()                    # xét lại hạng (cả gia đình nếu dùng chung)
    partner.dmag_loyalty_award_survey(source=nps_record)  # +điểm khảo sát, lũy đẳng theo nguồn
    env['dmag.loyalty.ledger']._dmag_earn(partner, 'recall', 50, source=visit, key='recall:%s' % visit.id)
    env['dmag.loyalty.voucher'].create_from_points(partner_id, points)
    visit.dmag_apply_voucher('DMXXXXXXXX')   # -> {'voucher', 'amount', 'amount_due'}
    visit.dmag_use_care_entitlement(procedure_id)   # -> {'usage_id', 'remaining'}
    env['res.partner'].get_loyalty_summary(partner_id)
    # -> {partner, currency, pooled, family, members[], tier{}, points, own_points, point_value, min_redeem,
    #     paid_12m, engagement_12m, lifetime_paid, next_tier{..., missing_paid, missing_points, progress},
    #     tiers[], vouchers[], subscriptions[{entitlements[]}], ledger[], updated_at}

Tương thích app Loyalty của Odoo (tùy chọn)
-------------------------------------------

Module không phụ thuộc ``loyalty``/``sale_loyalty``. Nếu phòng khám đã dùng chương trình / phiếu của Odoo,
có thể viết module cầu nối ``dmag_dental_loyalty_odoo`` (phụ thuộc mềm): ánh xạ ``dmag.loyalty.voucher`` ↔
``loyalty.card`` (mã, số dư) và dùng ``sale.order._apply_program_reward`` thay cho dòng giảm giá; sổ điểm
DMAG vẫn là nguồn chuẩn cho hạng / ví gia đình.

Cần xác nhận
------------

* Ngưỡng hạng mặc định (Bạc 5 tr / 150 điểm, Vàng 15 tr / 400, Kim cương 40 tr / 800 – điều kiện "một trong hai").
* Tỷ lệ tích điểm, giá trị quy đổi (1 điểm = 1.000 ₫), ngưỡng duyệt (1.000 điểm), hạn voucher mặc định (90 ngày).
* Voucher hết hạn: hiện **không** hoàn điểm – có muốn hoàn điểm / gia hạn không?
* Hoàn tiền (refund) hiện không trừ điểm tự động – Giám đốc điều chỉnh tay; có cần trừ tự động?
* Voucher đổi từ điểm không bị giới hạn bởi ``dmag_max_discount`` (đã là quyền lợi khách tích lũy) – xác nhận.
* Thuế GTGT của gói chăm sóc trả trước (sản phẩm chung "Gói chăm sóc định kỳ" để trống thuế) – kế toán xác nhận;
  doanh thu nhận trước có cần phân bổ theo lượt dùng không.
* Thưởng giới thiệu khi lượt khám đầu tiên **đã thanh toán đủ** – hay khi đạt mức chi tiêu tối thiểu?
* Tái khám đúng hẹn: sai lệch ± 14 ngày; khi có ``dmag_dental_journey`` nên dùng ngày hẹn tái khám của hành trình.
