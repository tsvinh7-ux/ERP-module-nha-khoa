# HIỆN TRẠNG HỆ THỐNG ODOO BIZAPPS & ĐỐI CHIẾU VỚI DENTAL ERP

> Nguồn: file xuất danh sách phân hệ (`ir.module.module`) do anh/chị cung cấp, ngày 10/10/2026: **1.453 module**, gồm **452 đã cài** và 996 chưa cài.
> Chưa truy cập trực tiếp được `dmagroup.vn` vì chính sách mạng của môi trường cloud chặn domain này. Phần dưới đây dựa hoàn toàn vào file danh sách module.

---

## 1. Tóm tắt nhanh

| Nhóm | Kết luận |
|---|---|
| **Nền Odoo** | Bản Bizapps "Community" nhưng thực tế đã có **gần đủ bộ app Enterprise**: Appointment, Sign, Documents, Studio, Payroll, Knowledge, Helpdesk, Planning, Appraisal, Marketing Automation, Frontdesk, Social, Accounting đầy đủ |
| **Bizapps (133 module)** | Đã có **Zalo OA + ZNS**, **HĐĐT Viettel S-Invoice** (đã cài), HĐĐT VNPT (chưa cài), VNPay, MoMo, SMS FPT, Facebook Messenger, chấm công máy, OKR, địa chỉ VN theo NQ60 |
| **Phát hiện lớn: ACS HMS (79 module, chưa cài)** | Bộ quản lý phòng khám/bệnh viện của Almighty Consulting đã nằm sẵn trong addons, **có cả `acs_hms_dental` và `acs_hms_dental_chart` (sơ đồ răng)**, ICD-10, phiếu đồng ý điện tử, hoa hồng bác sĩ, cổng bệnh nhân, đặt lịch online, màn hình gọi bệnh nhân, X-quang, nhà thuốc |
| **Chưa có** | Không có module **SePay**; không có chữ ký số (CA); không có tích hợp PACS/DICOM |

---

## 2. App nền đã cài, dùng ngay cho nha khoa

| App (tên kỹ thuật) | Trạng thái | Dùng cho |
|---|---|---|
| `appointment`, `appointment_crm`, `appointment_hr`, `website_appointment` | ✅ Đã cài | Đặt lịch bác sĩ/ghế, đặt online, lead từ lịch hẹn |
| `calendar`, `resource`, `planning` | ✅ | Lịch làm việc, ca bác sĩ/phụ tá |
| `frontdesk` | ✅ | Màn hình check-in khách tại sảnh |
| `sign` | ✅ | Phiếu đồng ý điều trị, hợp đồng niềng/implant, biên bản chốt két |
| `documents`, `documents_spreadsheet` | ✅ | Hồ sơ ảnh nhẹ, hồ sơ pháp chế |
| `web_studio` | ✅ | Tùy chỉnh nhỏ cho từng phòng khám |
| `sale_management`, `sale_subscription` | ✅ | Kế hoạch điều trị = báo giá; gói chăm sóc định kỳ (thuê bao) |
| `point_of_sale`, `pos_hr`, `pos_loyalty` | ✅ | Quầy lễ tân thu tiền, bán sản phẩm, tích điểm |
| `loyalty`, `sale_loyalty` | ✅ | Thẻ thành viên, voucher, giới thiệu |
| `account_accountant`, `account_followup`, `l10n_vn`, `account_bank_statement_import*` | ✅ | Kế toán, nhắc nợ, sao kê ngân hàng |
| `stock`, `purchase`, `mrp` | ✅ | Vật tư, mua hàng, labo nội viện (nếu có) |
| `hr`, `hr_contract`, `hr_attendance`, `hr_holidays`, `hr_skills`, `hr_recruitment`, `hr_referral`, `hr_expense` | ✅ | Hồ sơ nhân sự, chứng chỉ/kỹ năng, chấm công |
| `hr_payroll`, `hr_payroll_account` | ✅ | Chạy lương (gắn P1/P2/P3) |
| `hr_appraisal`, `hr_appraisal_skills`, `hr_appraisal_survey` | ✅ | Đánh giá năng lực (P2) |
| `crm`, `marketing_automation`, `mass_mailing`, `sms`, `social`, `social_facebook`, `survey`, `rating`, `im_livechat` | ✅ | CRM, hành trình tự động, khảo sát NPS |
| `helpdesk` | ✅ | Tiếp nhận phàn nàn, bảo hành |
| `knowledge` | ✅ | SOP, phác đồ, kịch bản tư vấn |
| `project`, `timesheet_grid` | ✅ | Ca chỉnh nha/implant dài hạn (tùy chọn) |
| `website`, `website_sale`, `portal` | ✅ | Website, tài khoản bệnh nhân |
| `spreadsheet_dashboard`, `web_cohort`, `web_gantt`, `web_map` | ✅ | Báo cáo, dashboard |
| `maintenance` | ⬜ Chưa cài | Bảo trì thiết bị, kiểm định X-quang (cài khi cần) |
| `whatsapp`, `voip` | ⬜ | Không cần (dùng Zalo, Stringee) |

## 3. Module Bizapps liên quan trực tiếp

| Module | Trạng thái | Dùng cho Dental ERP |
|---|---|---|
| `biz_zalo`, `biz_zalo_common`, `biz_zalo_zns`, `biz_zalo_discuss` | ✅ Đã cài | **Zalo OA + ZNS sẵn có**. Bỏ module `dmag_zalo` dự kiến, hành trình CSKH gọi thẳng ZNS của Bizapps |
| `biz_zalo_crm_lead` | ⬜ | Lead từ Zalo OA vào CRM: nên cài |
| `biz_viettel_sinvoice_v2` | ✅ | **HĐĐT Viettel**: tự phát hành khi tiền về |
| `biz_einvoice_vnpt` | ⬜ | HĐĐT VNPT (cho khách dùng VNPT) |
| `biz_payment_vnpay`, `biz_payment_momo` | ✅ | Cổng thanh toán online (giữ làm phương án phụ) |
| `biz_payment_baokim` | ⬜ | Không cần |
| `biz_sms_fpt` | ✅ | SMS dự phòng khi khách không dùng Zalo |
| `biz_facebook_message`, `biz_facebook_app` | ✅ | Lead/hội thoại Facebook |
| `biz_tiktok` | ⬜ | Lead TikTok (cài khi chạy kênh này) |
| `biz_stringee_call_center(_community)` | ⬜ | **Tổng đài CSKH/telesale**: gọi nhắc lịch, hỏi thăm 24h, ghi âm |
| `biz_citizen_id_card` | ⬜ | **Tạo hồ sơ bệnh nhân từ CCCD**: lễ tân quét CCCD, không gõ tay |
| `biz_okr`, `biz_hr_okr` | ✅ | OKR của Bizapps: **trùng chức năng với OKR Scale của DMAG** (xem mục 6) |
| `biz_kpi_scorecard` | ⬜ | KPI Balanced Scorecard: có thể làm nguồn KPI cho P3 |
| `biz_hr_payslip`, `biz_hrm` | ⬜ | Lương nâng cao / HR VN: cần xem nội dung trước khi chọn làm nền cho 3P |
| `biz_sales_commission_user_partner` | ⬜ | Hoa hồng bán hàng: đối chiếu với `acs_hms_commission` |
| `biz_attendance_device` | ✅ | Chấm công máy |
| `biz_user_roles`, `biz_access_restriction_by_ip` | ⬜ | Phân quyền theo vai trò, giới hạn IP (bảo mật bệnh án) |
| `biz_medical` ("Client Medical") | ⬜ | **Cần xem nội dung**: có thể là bản customize y tế cũ của Bizapps |
| `saas_client` | ✅ | Hệ thống chạy dạng **SaaS nhiều tenant**: thuận lợi để đóng gói từng gói cho từng phòng khám |

## 4. Bộ ACS HMS (Almighty Consulting) có sẵn, chưa cài

| Module | Nội dung | Tương ứng module DMAG dự kiến |
|---|---|---|
| `acs_hms_base`, `acs_hms` | Bệnh nhân, bác sĩ, lượt khám (appointment/encounter), đơn thuốc, chẩn đoán | A2, A3 (một phần), A8 |
| **`acs_hms_dental`**, **`acs_hms_dental_chart`** | Nha khoa (odontology), **sơ đồ răng** | A1, A4 (sơ đồ răng) |
| `acs_hms_icd10` | Danh mục ICD-10 | A1 |
| `acs_hms_consent_form`, `acs_consent_form` | Phiếu đồng ý điện tử | A4 (hoặc dùng Sign) |
| `acs_hms_radiology`, `acs_radiology` | X-quang/chẩn đoán hình ảnh | B1 (một phần) |
| `acs_hms_pharmacy`, `acs_hms_pharmacy_pos` | Nhà thuốc, bán thuốc tại POS | A8 |
| `acs_hms_commission`, `acs_commission` | Hoa hồng bác sĩ | D2 |
| `acs_hms_portal`, `acs_hms_online_appointment`, `acs_website_booking` | Cổng bệnh nhân, đặt lịch online | C4 |
| `acs_hms_next_patient_screen` | Màn hình gọi bệnh nhân tiếp theo | E1 (sảnh chờ) |
| `acs_hms_subscription`, `acs_hms_recurring_procedure` | Gói khám định kỳ, thủ thuật lặp lại | C2, nhắc tái khám |
| `acs_hms_insurance*` | Bảo hiểm | D4 (chuỗi) |
| `acs_hms_survey`, `acs_hms_rating`, `acs_hms_sms` | Khảo sát, đánh giá, SMS | C1 |
| `acs_hms_aesthetic`, `acs_hms_body_chart`, `acs_hms_webcam`, `acs_hms_barcode`, `acs_hms_dashboard`, `acs_hms_documents_preview`, `acs_hms_vital_examination` | Thẩm mỹ, ảnh, webcam, mã vạch BN, dashboard | Hỗ trợ |
| `acs_hms_whatsapp`… | WhatsApp | Không dùng (thay bằng Zalo ZNS) |

### Quyết định cần anh/chị duyệt: có dựng trên ACS HMS hay không?

| Phương án | Ưu | Nhược / rủi ro |
|---|---|---|
| **1. Dựng trên ACS HMS** (`dmag_*` phụ thuộc `acs_hms_dental`) | Có sẵn bệnh nhân, lượt khám, sơ đồ răng, ICD-10, đơn thuốc, hoa hồng, cổng BN. Rút ngắn lõi A1–A4, A8 đáng kể | **Giấy phép**: ACS là module thương mại (thường OPL-1). Cần xác nhận được phép dùng cho **nhiều phòng khám/SaaS bán lại** hay chỉ 1 database. Mô hình dữ liệu kiểu bệnh viện, nặng hơn nhu cầu nha khoa. Phụ thuộc lịch nâng cấp của bên thứ ba. Giao diện vẫn là Odoo chuẩn, nên Lớp trải nghiệm (E1) vẫn phải viết |
| **2. Tự dựng lõi `dmag_*`** (như đề xuất v3) | Sở hữu 100% IP, mô hình gọn đúng nha khoa VN, tự quyết lộ trình, đóng gói bán cho nhiều phòng khám không vướng giấy phép | Tốn công hơn cho phần lõi |
| **3. Lai (khuyến nghị)** | **Cài thử ACS trên staging để đánh giá**: sơ đồ răng, luồng khám, chất lượng code, giấy phép. Nếu giấy phép cho phép SaaS và chất lượng tốt → phương án 1 cho lõi. Nếu không → phương án 2, tham khảo nghiệp vụ từ ACS | Mất thêm 1 bước đánh giá |

## 5. Thanh toán SePay: thị trường đã có gì

Không có module SePay chính thức do SePay phát hành cho Odoo. SePay chỉ ghi Odoo trong danh sách nền tảng có thể **tự tích hợp qua webhook**. Trên Odoo Apps có các module bên thứ ba:

| Module | Bản | Nội dung | Đánh giá |
|---|---|---|---|
| `tangerine_sepay_integration` (Long Duong Nhat) | 14–18 (bản 17: LGPL-3) | Webhook SePay `/webhook/v1/payment/sepay` + QR, xác thực thanh toán (~400 dòng code) | Gọn, giấy phép mở, nhưng nhỏ; **không có POS, không tự phát hành HĐĐT, không chốt két** |
| `d_bank_connector_sepay` | 17 (có phí, ~34 USD) | Đồng bộ giao dịch SePay vào sổ ngân hàng kế toán | Thiên về kế toán, không phải luồng thu tiền tại quầy |
| `d_payment_method_vietqr` | 17 | QR VietQR cơ bản, không webhook | Không đủ |
| `payment_sepay` | **chỉ có bản 19** | Payment provider SePay cho eCommerce | Phải port ngược về 17 |

**Kết luận: cần viết module riêng `dmag_payment_sepay`.** Phạm vi đề xuất:
1. Cấu hình tài khoản SePay theo công ty/chi nhánh (multi-company, phù hợp `saas_client`).
2. Sinh **QR VietQR động** trên POS, hóa đơn, đơn bán, link Zalo; nội dung chuyển khoản chứa **mã thanh toán duy nhất**.
3. **Webhook** có xác thực API key, chống ghi trùng (idempotency theo id giao dịch SePay), ghi log thô.
4. Khớp tự động theo mã + số tiền → ghi nhận thanh toán (POS order / invoice) → **tự phát hành HĐĐT** qua `biz_viettel_sinvoice_v2` (hoặc VNPT).
5. Hàng chờ ngoại lệ: thiếu, thừa, sai nội dung, không khớp; lễ tân/kế toán xử lý tay.
6. Đối soát cuối ngày và **Chốt két 4 bước**; tùy chọn đẩy giao dịch vào sổ ngân hàng kế toán.
7. Thông báo realtime lên màn hình lễ tân khi tiền về.

Có thể tham khảo `tangerine_sepay_integration` (LGPL-3, bản 17) cho phần webhook.

## 6. Hai chỗ trùng cần chốt

1. **OKR**: hệ thống đang cài `biz_okr` + `biz_hr_okr` (Bizapps), trong khi DMAG có bộ **OKR Scale** riêng (repo `OKR-scale`: lõi, CFR, điểm thưởng, portal, theme). **Đã chốt: dùng OKR Scale của DMAG** (đã có hook để KR tự đo) và gỡ hoặc ẩn `biz_okr` để người dùng không thấy hai app OKR.
2. **Hoa hồng**: `acs_hms_commission` / `biz_sales_commission_user_partner` / tự viết `dmag_dental_commission`. Chốt sau khi đánh giá ACS.

## 7. Chữ ký số: khuyến nghị 1–2 nhà cung cấp

| Thứ tự | Nhà cung cấp | Lý do |
|---|---|---|
| **1** | **VNPT SmartCA** | Ký số từ xa trên điện thoại, không cần USB token; VNPT định vị riêng cho ngành y tế (ký bệnh án điện tử, đơn thuốc), có **API tích hợp vào phần mềm y tế** và đang dùng trong VNPT-HIS. Phổ biến nhất ở bệnh viện/phòng khám |
| **2** | **Viettel MySign** | Ký từ xa không cần token/SIM/HSM, có tài liệu API (luồng OTP → cấp quyền ký), đã tích hợp VNeID. Hợp lý nếu phòng khám đang dùng HĐĐT Viettel S-Invoice (cùng hệ Viettel) |

Phương án dự phòng: FPT.eSign (được cấp phép ký số từ xa, mạnh ở ngân hàng/tài chính, ít tài liệu cho y tế).

**Đã chốt: Viettel MySign.** Module `dmag_esign` vẫn viết dạng adapter để có thể thêm nhà cung cấp khác. Trước khi tích hợp cần xin từ nhà cung cấp: **tài liệu API mới nhất, sandbox, bảng giá theo số chứng thư/lượt ký**, và xác nhận đáp ứng yêu cầu ký bệnh án điện tử theo quy định hiện hành.

---

## 8. Việc tiếp theo đề xuất

1. Anh/chị cho phép domain `dmagroup.vn` trong cài đặt mạng của môi trường cloud, và tạo **1 tài khoản thử riêng** (không dùng admin chính), tốt nhất trên **database staging**, để tôi xem trực tiếp mục Ứng dụng/Cài đặt.
2. Trên staging: cài thử `acs_hms_dental` + `acs_hms_dental_chart` để đánh giá (phương án 3 ở mục 4), đồng thời xem nội dung `biz_medical`.
3. Hỏi Almighty/Bizapps về **giấy phép ACS** cho mô hình SaaS bán nhiều phòng khám.
4. Chốt OKR: OKR Scale hay `biz_okr`.
5. Bắt đầu viết `dmag_payment_sepay` (không phụ thuộc quyết định ACS, làm song song được).

Nguồn tham khảo: [tangerine_sepay_integration](https://apps.odoo.com/apps/modules/17.0/tangerine_sepay_integration) · [payment_sepay (v19)](https://apps.odoo.com/apps/modules/19.0/payment_sepay) · [d_bank_connector_sepay](https://apps.odoo.com/apps/modules/17.0/d_bank_connector_sepay) · [d_payment_method_vietqr](https://apps.odoo.com/apps/modules/17.0/d_payment_method_vietqr) · [SePay – Tích hợp](https://sepay.vn/tich-hop.html) · [SePay – Thương mại điện tử](https://sepay.vn/thuong-mai-dien-tu.html) · [VNPT SmartCA cho y tế](https://minhvnpt.com/vnpt-smartca-giai-phap-ky-so-tu-xa-cho-chuyen-doi-so-nganh-y-te) · [VNPT SmartCA (Dân trí)](https://dantri.com.vn/kinh-doanh/go-diem-nghen-cho-ky-voi-vnpt-smartca-20261001172723255.htm) · [Viettel – API ký số](http://viettelsolution.com.vn/san-pham/huong-dan-tich-hop-api-chu-ky-so-vao-ung-dung-thong-qua-webservice-viettel.102.html) · [FPT.eSign](https://fpt-is.com/en/fpt-is-licensed-for-remote-digital-signing-technology-a-trend-inevitable-in-the-digital-era/)
