DMAG – Vật tư theo định mức
===========================

Trừ vật tư theo định mức khi hoàn tất thủ thuật, truy xuất serial implant ↔ bệnh nhân, đo giá vốn vật tư.

* **Định mức** ``dmag.service.bom``: mỗi dịch vụ một định mức (riêng phòng khám hoặc dùng chung), dòng vật tư
  gồm số lượng, đơn vị, tính "mỗi răng" hoặc "mỗi lần thủ thuật".
* **Hoàn tất thủ thuật** (ghi đè ``action_done`` qua ``super()``): tính số lượng theo định mức → tạo và xác nhận
  phiếu xuất (quyền hệ thống) loại hoạt động "Tiêu hao lâm sàng" từ kho phòng khám tới địa điểm
  "Tiêu hao lâm sàng" (tự tạo theo công ty), ghi ``dmag.material.usage`` (giá vốn = giá vốn chuẩn × số lượng).
* **Serial / lô**: thủ thuật có trường ``lot_ids``; nếu định mức có vật tư theo serial (trụ implant) phải chọn đủ
  số serial (= số răng × định mức) trước khi hoàn tất; serial đã dùng không dùng lại. Vật tư theo lô phải chọn lô.
  Bàn làm việc bác sĩ: ``add_from_workspace(..., lot_ids=[...])``; ``_workspace_dict`` có ``lot_required``, ``lots``,
  ``material_cost``.
* **Truy xuất implant**: menu "Truy xuất implant" (serial → bệnh nhân, thủ thuật, bác sĩ, ngày); trên serial
  (stock.lot) có bệnh nhân / thủ thuật / ngày dùng.
* **Phát sinh thực tế**: phụ tá ghi vật tư dùng thêm (bắt buộc lý do) → tự xuất kho; **tạo được – không sửa / xóa**
  (chỉ Giám đốc).
* **KPI** ``dmag.material.usage.get_material_kpis(date_from, date_to, company_id=False)`` →
  ``{revenue, material_cost, bom_cost, extra_cost, variance_ratio, material_ratio, lab_cost, cogs_ratio,
  threshold, alert, message, implant_count, top_products[{product_id, name, qty, cost}], currency, company_id,
  date_from, date_to}``. ``cogs_ratio`` = (vật tư + labo nếu cài ``dmag_dental_lab``) / doanh thu;
  ngưỡng ``res.company.dmag_cogs_threshold`` (mặc định 22%).
* Vật tư sắp hết: dùng quy tắc tồn tối thiểu chuẩn của Odoo (menu "Vật tư sắp hết", "Tồn tối thiểu").

Cần xác nhận
------------

* Doanh thu dùng tính tỷ lệ: giá trị thủ thuật hoàn tất theo ngày lượt khám (chưa phải thực thu / doanh thu kế toán).
* Giá vốn theo **giá vốn chuẩn** hiện hành của sản phẩm (không phải FIFO / bình quân thực tế của lô).
* Cho phép xuất âm kho khi chưa nhập đủ (hiện **cho phép** để không chặn ca điều trị; tồn âm hiện trên báo cáo kho).
* Ghi nhận "dùng ít hơn định mức" (hoàn kho) – chưa hỗ trợ, cần Giám đốc điều chỉnh tồn kho.
* Vật tư theo lô (không phải serial): có bắt buộc chọn lô như hiện tại?
