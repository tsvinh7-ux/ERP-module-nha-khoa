# Hướng dẫn phát triển DMAG Dental ERP (cho mọi module `dmag_*`)

## Môi trường thử
- Odoo 17 source: `/tmp/odoo17`; Python: `/tmp/venv17/bin/python`; PostgreSQL local (user `odoo`/`odoo`). Nếu PostgreSQL tắt: `service postgresql start`.
- Config mẫu `/tmp/odoo.conf` (addons_path = `/tmp/odoo17/addons,/home/user/ERP-module-nha-khoa/addons`).
- Chạy test (mỗi người dùng **tên DB và cổng riêng** để không đụng nhau):
  ```bash
  cd /tmp && /tmp/venv17/bin/python /tmp/odoo17/odoo-bin -c /tmp/odoo.conf -d <db_riêng> \
    -i <module> --test-tags /<module> --stop-after-init --http-port=<cổng_riêng>
  ```
- Bản Community thuần, **không** có Appointment/Sign/Documents/Payroll Enterprise – module phải cài được trên CE; tích hợp các app Bizapps viết thành module cầu nối riêng, phụ thuộc mềm.

## Quy ước
- Mã nguồn tiếng Anh, **nhãn / thông báo tiếng Việt** trực tiếp trong code (sản phẩm cho thị trường VN).
- Odoo 17: `invisible="..."`/`readonly="..."` biểu thức, `<tree>`, OWL 2, `/** @odoo-module **/`.
- Tiền tố `dmag_`, author `DMAG – Dental Management & Analytics Group`, license `LGPL-3`, version `17.0.1.0.0`, category `Healthcare/Dental`, icon copy từ `dmag_dental_base/static/description/icon.png`.
- Mỗi module có `README.rst`, `security/ir.model.access.csv`, record rule theo `company_id`, tests (`post_install`, `-at_install`).
- Không sửa file của module khác. Cần điểm móc thì `_inherit` và gọi `super()`.

## Nguyên tắc phân quyền "tạo được – không sửa" (BẮT BUỘC)
- Nhóm (thấp → cao): `dmag_dental_base.group_dmag_receptionist` < `group_dmag_assistant` < `group_dmag_doctor` < `group_dmag_manager` < `group_dmag_director` (Giám đốc / Quản lý cấp cao).
- Helper: `from odoo.addons.dmag_dental_base.models.dmag_access import is_director, check_director, check_discount, is_workflow`.
- Nhân viên **tạo** chứng từ; sau khi có hiệu lực (xác nhận / hoàn tất / ký / ghi sổ) **không sửa, không xóa** – chỉ `is_director()`. Thao tác theo luồng chạy với `with_context(dmag_workflow=True)`.
- Lễ tân / bác sĩ **không** có quyền Bán hàng / Kế toán. Đơn bán, hóa đơn, thanh toán được tạo bằng `sudo()` bên trong nghiệp vụ nha khoa, có ghi chatter.
- Giá lấy theo bảng giá; giảm giá ≤ `company.dmag_max_discount` (vượt → Giám đốc).

## API lõi sẵn có (dmag_dental_clinic)
- `dmag.dental.visit`: trạng thái `draft/confirmed/arrived/in_chair/done/cancel/no_show`; `_dmag_journey_event(event)` với event ∈ booked, confirmed, arrived, in_chair, done, cancelled, no_show, signed, paid; `_dmag_esign_request()` (khi ký bệnh án); `_dmag_on_invoices_posted(moves)` (phát hành HĐĐT); `register_payment(method, amount, reference)` với method ∈ cash/transfer/card; `_create_and_post_invoices()`; `_get_open_invoices()`; `amount_due`, `payment_status`; `get_visit_workspace()` trả dict cho giao diện bác sĩ (module khác có thể mở rộng bằng `super()` và thêm khóa mới); `get_frontdesk_board()`.
- `dmag.dental.procedure` (thủ thuật), `dmag.treatment.plan/option/line`, `dmag.dental.chart.entry`, `dmag.dental.practitioner` (bác sĩ: `user_id`, `license_number`, `scope_ids`, `clinical_level_id`), `res.partner` (bệnh nhân: `is_patient`, `patient_code`, `citizen_id`, `birthdate`, `age`, `gender`, `guardian_id`, `allergy`, `patient_alert_ids`, `zalo_phone`, `dental_family_id`, `referrer_id`, `customer_source_id`), `product.template` (dịch vụ: `is_dental_service`, `warranty_months`, `recall_months`, `aftercare_note`, `dental_vat_regime`).
- Công ty: `dmag_facility_code` (mã cơ sở KCB 5 ký tự), `dmag_license_number`, `dmag_max_discount`.

## Căn cứ pháp lý
Xem `docs/PHAP_LY_NHA_KHOA.md`.
