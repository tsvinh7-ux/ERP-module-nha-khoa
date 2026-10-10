# DMAG DENTAL ERP — ĐỀ XUẤT KIẾN TRÚC v2

> **Trạng thái:** bản nháp chờ phê duyệt, chưa viết code.
> **Nền tảng:** Odoo 17 Community bản Bizapps đã customize (có sẵn Kế toán VN, Hóa đơn điện tử, Lương, Appointment, Sign, Documents, Studio…).
> **Chủ sở hữu sản phẩm:** CT TNHH Dental Management & Analytics Group (DMAG), định vị *Nền tảng Vận hành & Tăng trưởng Nha khoa*.
> **Nguồn tham chiếu:** tài liệu DMAG trên Drive (Q-Summit 2026, OKRs Nha khoa – bản mẫu, Bộ phân độ OKR v1.0, JD Lễ tân/Bác sĩ/Điều dưỡng/KTV, thư mục Pháp luật Nha khoa) và repo `tsvinh7-ux/OKR-scale` (đã có `okr_scale*` và `dmag_brand_theme`).

---

## 0. Định vị sản phẩm rút ra từ tài liệu DMAG

Dental ERP không phải "phần mềm quản lý phòng khám" thông thường. Đây là **hệ điều hành** để bác sĩ chủ **chuyển giao năng lực vào tổ chức** (thông điệp Q-Summit). Mọi tính năng phải phục vụ 4 mục tiêu đo được:

| Mục tiêu | Chỉ số ERP phải tự đo (không nhập tay) | Nguồn |
|---|---|---|
| Tuân thủ "3 lằn ranh đỏ" | Bệnh án điện tử chuẩn; 100% doanh thu có HĐĐT; giấy phép, phạm vi hành nghề, bức xạ, chất thải còn hiệu lực | Q-Summit, TT 13/2025/TT-BYT, NĐ 70/2025 |
| Dòng tiền minh bạch | Két cuối ngày khớp 100% (tiền mặt + POS + chuyển khoản so với phần mềm) | Q-Summit, "Chốt két 4 bước" |
| Năng suất vận hành | Công suất ghế buổi chiều ≥ 65%; giá vốn vật tư & labo ≤ 22% doanh thu; bác sĩ phụ đảm nhận ≥ 50% số ca | Q-Summit, KR 90 ngày |
| Trải nghiệm & tăng trưởng | NPS sau điều trị; điểm đau sau thủ thuật; thời gian chờ; tỷ lệ đồng thuận kế hoạch điều trị; doanh thu từ khách giới thiệu | OKRs Nha khoa – bản mẫu |

Các chỉ số trên hiển thị tại Buồng lái Chủ phòng khám và là nguồn tự đo cho OKR. Quy mô phòng khám (số ghế, doanh thu, số cơ sở) là cơ sở **đóng gói ERP** (mục 10).

---

## 1. Nguyên tắc: tận dụng tối đa nền Bizapps, không dựng lại

| App Bizapps có sẵn | Dùng cho nha khoa | Phần cần bổ sung (chỉ mở rộng, không viết lại) |
|---|---|---|
| **Contacts** | Hồ sơ bệnh nhân, gia đình, labo, nhà cung cấp | Trường y khoa, cảnh báo, mã BN, nhóm gia đình |
| **Appointment** | Đặt lịch online & tại quầy | Resource = bác sĩ + ghế; thời lượng theo dịch vụ; luật xếp lịch xen ca khó/dễ; trạng thái ghế; hàng chờ |
| **Calendar / Resource** | Lịch làm việc bác sĩ theo ca, chi nhánh | Liên kết phạm vi hành nghề |
| **Sales** | Kế hoạch điều trị = báo giá nhiều phương án | Dòng gắn răng/mặt răng/giai đoạn; mẫu in "Bản tóm tắt bệnh án mini" |
| **POS** | Quầy lễ tân: thu tiền, bán sản phẩm chăm sóc răng | Nạp kế hoạch điều trị vào POS, QR động, chốt két |
| **Invoicing/Accounting + HĐĐT Bizapps** | Thu tiền, công nợ, hóa đơn điện tử | Tự phát hành HĐĐT khi tiền về; thu theo tiến độ, trả góp |
| **Sign** | Phiếu đồng ý điều trị, cam kết, hợp đồng chỉnh nha/implant | Mẫu văn bản nha khoa, ký trên tablet tại ghế |
| **Documents** | Lưu ảnh nhẹ, phiếu, hồ sơ pháp chế | Thư mục tự động theo bệnh nhân / lần khám |
| **Studio** | Phòng khám tự chỉnh nhỏ (trường, báo cáo) | Khóa vùng lõi để nâng cấp không vỡ |
| **Inventory / Purchase** | Vật tư, implant, labo | Định mức theo dịch vụ, serial implant, phiếu labo |
| **Employees / Attendance / Time Off / Payroll Bizapps** | Nhân sự, chấm công, lương | Cấu phần lương 3P (mục 6) |
| **CRM / Email / SMS / Survey / Marketing** | Lead, CSKH, khảo sát | Hành trình 3 chặng, Zalo ZNS (mục 5) |
| **Loyalty** | Chương trình khách hàng thân thiết | Hạng thành viên, ví gia đình, giới thiệu (mục 5) |
| **Website / Portal** | Đặt lịch, tài khoản bệnh nhân | Trang "Hồ sơ răng của tôi", API cho app sau này |
| **Maintenance** | Thiết bị, ghế, autoclave, máy X-quang | Lịch kiểm định bức xạ |
| **OKR Scale (DMAG)** + `dmag_brand_theme` | OKR, CFR, điểm thưởng nội bộ | Cầu nối KR tự đo từ dữ liệu nha khoa |

> ✅ Đã đối chiếu với danh sách 1.453 module thực tế của hệ thống: xem **[HIEN_TRANG_BIZAPPS.md](HIEN_TRANG_BIZAPPS.md)**. Đã có sẵn Zalo OA/ZNS, HĐĐT Viettel, Appointment, Sign, Documents, Studio, Payroll, Helpdesk, Knowledge, Frontdesk… Có thêm bộ **ACS HMS** (gồm `acs_hms_dental`, sơ đồ răng) chưa cài, **cần anh/chị quyết định có dựng lõi trên ACS hay không**.

---

## 2. Kiến trúc 3 lớp

```
┌──────────────────────────────────────────────────────────────────────────┐
│  LỚP 3 · TRẢI NGHIỆM (DMAG Clinic Workspace – OWL, tablet-first)         │
│  Bàn làm việc Bác sĩ · Bảng điều phối Lễ tân · Chế độ Tư vấn · Buồng lái │
│  Chủ PK · Cổng/App Bệnh nhân (qua API)                                   │
├──────────────────────────────────────────────────────────────────────────┤
│  LỚP 2 · NGHIỆP VỤ NHA KHOA (addons dmag_*)                              │
│  EMR · Sơ đồ răng · Kế hoạch điều trị · Labo · Định mức · Hành trình KH  │
│  · Loyalty · 3P · OKR nha khoa · Pháp chế                                │
├──────────────────────────────────────────────────────────────────────────┤
│  LỚP 1 · NỀN BIZAPPS (có sẵn – chỉ kế thừa)                              │
│  Contacts · Appointment · Sales · POS · Accounting · HĐĐT · Sign ·       │
│  Documents · Inventory · Purchase · HR · Payroll · CRM · Loyalty · Portal│
└──────────────────────────────────────────────────────────────────────────┘
          ▲ Zalo OA/ZNS · Cổng thanh toán/ngân hàng · PACS/thiết bị ảnh · Chữ ký số
```

Bác sĩ và lễ tân **làm việc 100% ở Lớp 3**. Lớp 1–2 là giao diện Odoo chuẩn, dành cho kế toán, kho, quản lý và admin.

---

## 3. Danh sách module đề xuất (tiền tố `dmag_`)

### A. Lõi nha khoa
| # | Module | Chức năng chính | Kế thừa |
|---|---|---|---|
| A1 | `dmag_dental_base` | Danh mục răng FDI (người lớn, trẻ em, hỗn hợp), mặt răng, tình trạng, ICD-10 K00–K14; chi nhánh, phòng, ghế; **phạm vi hành nghề** từng người; **cây phân cấp lâm sàng** Bậc 1–3; vai trò & phân quyền | `base`, `hr` |
| A2 | `dmag_dental_patient` | Hồ sơ bệnh nhân, tiền sử, dị ứng, cảnh báo đỏ, nguồn khách, người giới thiệu, **nhóm gia đình**, người giám hộ, đồng ý xử lý dữ liệu cá nhân | `res.partner` |
| A3 | `dmag_dental_appointment` | Mở rộng Appointment: bác sĩ + ghế + dịch vụ + thời lượng; **luật xếp lịch** (không chồng 2 ca implant/phẫu thuật cùng khung, xen ca nhẹ để lấp ghế); lấp **ghế trống buổi chiều**; check-in, hàng chờ, **đồng hồ thời gian chờ** | `appointment`, `calendar`, `resource` |
| A4 | `dmag_dental_emr` | **Bệnh án điện tử theo TT 13/2025**: phiếu khám, **sơ đồ răng tương tác**, chẩn đoán, tiến trình từng lần (SOAP), chỉ định và kết quả cận lâm sàng, **chữ ký số** bác sĩ, khóa hồ sơ, nhật ký truy cập, xuất bệnh án; phiếu đồng ý qua **Sign** | `sign`, `documents` |
| A5 | `dmag_dental_treatment` | Kế hoạch điều trị **2+ phương án**, chia giai đoạn theo răng; bệnh nhân tự chọn → báo giá/đơn hàng; **Bản tóm tắt bệnh án mini** (in màu/gửi Zalo) kèm **lộ trình chi phí theo tháng & trả góp**; theo dõi % hoàn thành; **cầu chì y đức**: ca bọc sứ/mài cùi bắt buộc bác sĩ thứ hai duyệt | `sale` |
| A6 | `dmag_dental_service` | Danh mục dịch vụ: thời lượng chuẩn, **định mức vật tư (BOM)**, bậc lâm sàng tối thiểu, giá theo chi nhánh/hạng thành viên, chính sách bảo hành | `product`, `pricelist` |
| A7 | `dmag_dental_billing` | Thu theo tiến độ, đặt cọc, trả góp, công nợ; **QR động kèm số tiền qua SePay**; **đối soát ngân hàng tự động bằng webhook SePay** → **tự phát hành HĐĐT** (qua HĐĐT Bizapps); **Chốt két 4 bước** có biên bản bàn giao | `account`, `pos`, HĐĐT Bizapps |
| A7a | `dmag_payment_sepay` | **Viết mới** (thị trường chưa có bản Odoo 17 đầy đủ): QR động, webhook, khớp tự động, hàng chờ ngoại lệ, kích hoạt HĐĐT `biz_viettel_sinvoice_v2` | `payment`, `point_of_sale`, `account` |
| A4a | `dmag_esign` | Ký số từ xa **Viettel MySign** (đã chọn), viết dạng adapter | `sign` |
| A8 | `dmag_dental_prescription` | Đơn thuốc theo TT 52/2017 & TT 04/2022, mẫu đơn theo thủ thuật, in/gửi Zalo, sẵn sàng **liên thông đơn thuốc quốc gia** | model mới |

### B. Vận hành lâm sàng
| # | Module | Chức năng chính |
|---|---|---|
| B1 | `dmag_dental_imaging` | **Tích hợp thiết bị/PACS, không lưu file gốc**: chỉ lưu metadata (Study/Series UID, loại phim, răng, ngày, máy) + ảnh thu nhỏ + **deep-link mở viewer**; ánh xạ vào bệnh án theo răng/lần khám. Chuẩn kết nối: DICOMweb (QIDO/WADO) nếu thiết bị hỗ trợ, hoặc thư mục giám sát / link viewer của hãng. Camera trong miệng chụp trực tiếp lên màn hình tư vấn |
| B2 | `dmag_dental_lab` | Phiếu gửi labo (màu răng, vật liệu, hạn), trạng thái, thử sườn, trễ hạn, chi phí labo → công nợ, % labo/doanh thu |
| B3 | `dmag_dental_stock` | Trừ vật tư theo định mức khi hoàn tất thủ thuật, lô/hạn dùng, **serial implant ↔ bệnh nhân**, chênh lệch định mức – thực tế, **COGS ≤ 22%** |
| B4 | `dmag_dental_warranty` | Thẻ bảo hành điện tử implant/sứ/chỉnh nha, hiển thị trong tài khoản bệnh nhân |
| B5 | `dmag_dental_compliance` | **Hồ sơ pháp chế**: giấy phép hoạt động, giấy phép hành nghề (5 năm, phạm vi), giấy phép bức xạ, kiểm định X-quang/CBCT, hợp đồng chất thải y tế, PCCC; cảnh báo trước hạn; "sẵn sàng thanh tra" 1 click |

### C. Khách hàng & tăng trưởng (chi tiết mục 5)
| # | Module | Chức năng chính |
|---|---|---|
| C1 | `dmag_dental_journey` | **CRM hành trình Trước – Trong – Sau**, kịch bản tự động theo sự kiện, bảng việc CSKH, NPS, xử lý phàn nàn |
| C2 | `dmag_dental_loyalty` | Hạng thành viên, điểm, **ví gia đình**, giới thiệu 2 chiều, gói chăm sóc định kỳ trả trước, quyền lợi theo hạng |
| C3 | ~~`dmag_zalo`~~ → dùng **`biz_zalo_zns`** có sẵn | Chỉ bổ sung mẫu tin nha khoa + gắn sự kiện hành trình; cài thêm `biz_zalo_crm_lead` |
| C4 | `dmag_patient_portal` | **Tài khoản bệnh nhân** (portal hôm nay, app sau này): lịch hẹn, nội dung khám từng lần, kế hoạch điều trị, đơn thuốc, lời dặn, ảnh trước/sau, hóa đơn, bảo hành, điểm/hạng; **REST API** dùng chung cho app |

### D. Con người & quản trị (chi tiết mục 6)
| # | Module | Chức năng chính |
|---|---|---|
| D1 | `dmag_hr_3p` | Khung ngạch bậc **P (chuyên môn) & M (quản lý)** cho từng vị trí; Lương 3P: P1 vị trí, P2 năng lực, P3 kết quả (OKR + KPI + hoa hồng); gắn vào hồ sơ nhân viên → đẩy vào **Payroll Bizapps**. Làm bản demo trước, nạp khung chuẩn sau |
| D2 | `dmag_dental_commission` | Thủ thuật phí bác sĩ/phụ tá, hoa hồng tư vấn, telesale, lễ tân (sản phẩm 8–10%, chốt dịch vụ 1–2%); tính trên **thực thu**; tự hủy khi vi phạm cầu chì y đức |
| D3 | `dmag_okr_dental` | Cầu nối với **OKR Scale** của DMAG (đã chốt; ẩn/gỡ `biz_okr` để tránh 2 app OKR): KR **tự cập nhật** từ dữ liệu nha khoa qua hook `_compute_progress_by_method`; **chỉ số sức khỏe/cầu chì**: tỷ lệ phàn nàn > 2%/tháng, hủy hợp đồng niềng 30 ngày > 5%, đánh giá 1–2 sao > 3/tháng |
| D4 | `dmag_dental_chain` | Chuỗi đa chi nhánh: hồ sơ bệnh nhân dùng chung, kho/giá/doanh thu theo chi nhánh, chuyển bệnh nhân, mua hàng tập trung, báo cáo hợp nhất; bảo hiểm tư nhân (tùy chọn) |

### E. Lớp trải nghiệm (chi tiết mục 4)
| # | Module | Chức năng chính |
|---|---|---|
| E1 | `dmag_clinic_workspace` | Ứng dụng OWL toàn màn hình, tối ưu tablet và màn hình cảm ứng: Bàn làm việc Bác sĩ, Bảng điều phối Lễ tân, Chế độ Tư vấn, Buồng lái Chủ phòng khám; dùng màu nhận diện DMAG (`#11346A` navy, `#178BEC` xanh) từ `dmag_brand_theme` |

Tổng cộng **23 module mới** (số này sẽ giảm nếu chọn dựng trên ACS HMS) cùng 7 module OKR Scale/brand theme đã có.

---

## 4. Giao diện cho bác sĩ: "ít chạm, đúng việc, đẹp như app"

Nguyên tắc UX: bác sĩ **không bao giờ thấy menu Odoo**. Mỗi thao tác lâm sàng tối đa **3 chạm**. Thiết kế cho găng tay và tablet đặt cạnh ghế: nút lớn, chữ lớn, có chế độ tối.

| Màn hình | Người dùng | Nội dung |
|---|---|---|
| **Bàn làm việc Bác sĩ** | Bác sĩ, phụ tá | Danh sách bệnh nhân hôm nay theo giờ và trạng thái; thẻ cảnh báo đỏ (dị ứng, tim mạch, thai kỳ); chạm vào bệnh nhân mở **Hồ sơ 1 trang**: sơ đồ răng ở giữa, lịch sử bên trái, phim/ảnh bên phải |
| **Sơ đồ răng tương tác** | Bác sĩ | Chạm răng → chạm mặt răng → chọn tình trạng/chỉ định từ **phác đồ mẫu**; lớp hiển thị: hiện trạng / kế hoạch / đã làm; xem lại theo dòng thời gian |
| **Ghi bệnh án nhanh** | Bác sĩ, phụ tá | Mẫu SOAP theo thủ thuật (nhổ, nội nha, implant…) tự điền sẵn; **nhập giọng nói** tiếng Việt (tùy chọn); phụ tá ghi vật tư; bác sĩ ký số 1 chạm |
| **Chế độ Tư vấn** (Tư vấn đồng thuận 2 bước) | Bác sĩ, tư vấn viên | Màn hình hướng về bệnh nhân: **ảnh camera trong miệng/phim** → **2 phương án** đặt cạnh nhau (ưu nhược, thời gian, chi phí, trả góp) → bệnh nhân chọn → **ký Sign trên tablet** → tạo lịch và đơn |
| **Bảng điều phối Lễ tân** | Lễ tân | Sơ đồ ghế theo trạng thái (trống / đang làm / sắp xong / vệ sinh); hàng chờ có **đồng hồ đếm phút** (đỏ khi > 15 phút); check-in bằng SĐT/QR; thu tiền, QR động, chốt két ngay trên màn hình |
| **Buồng lái Chủ phòng khám** | Chủ, quản lý | Doanh thu/thực thu, két ngày, công suất ghế theo khung giờ, COGS, % ca bác sĩ phụ, NPS, OKR xanh/vàng/đỏ, cảnh báo pháp chế |

Kỹ thuật: OWL 2 client actions, cập nhật thời gian thực qua bus (`bus.bus`), dùng được như PWA (cài lên tablet như app), API dùng chung với app bệnh nhân sau này.

---

## 5. CRM Trước – Trong – Sau & Loyalty

### 5.1 Hành trình khách hàng (mỗi điểm chạm là một sự kiện tự động trong `dmag_dental_journey`)

**TRƯỚC khi đến**
| Điểm chạm | Kênh | Nội dung |
|---|---|---|
| Lead vào | FB / TikTok / Zalo / Web / Hotline / Giới thiệu | Tự tạo lead, gắn nguồn/chiến dịch (đo CAC), chia telesale, kịch bản tư vấn |
| Đặt lịch thành công | ZNS | Xác nhận lịch: giờ, bác sĩ, chi nhánh, bản đồ, nút "Đổi lịch" |
| Trước 1 ngày | ZNS | Nhắc lịch, kèm **video 90 giây "quy trình không đau"** (theo OKR mẫu) cho ca thủ thuật |
| Trước 2 giờ | ZNS | Nhắc lần cuối; link **khai báo sức khỏe trước** để rút ngắn thời gian chờ |
| Không đến | Bảng việc CSKH | Tự tạo việc gọi lại, đề xuất giờ trống buổi chiều |

**TRONG khi ở phòng khám**
| Điểm chạm | Kênh | Nội dung |
|---|---|---|
| Check-in | Quầy / QR | ZNS **"Chào mừng [Tên] đến với [Nha khoa]"**; màn hình sảnh hiện tên và thời gian chờ dự kiến (tùy chọn) |
| Chờ | Hệ thống | Đồng hồ chờ; quá 15 phút thì báo lễ tân xin lỗi hoặc mời nước |
| Khám & tư vấn | Chế độ Tư vấn | Bản tóm tắt bệnh án mini; 2 phương án; ký đồng ý |
| Trước khi rời ghế | Tablet phụ tá | Hỏi **điểm đau 0–10** (KR 1.2) |
| Thanh toán | Quầy | QR động → tiền về → **HĐĐT tự phát hành**, gửi kèm Zalo |

**SAU khi về**
| Thời điểm | Kênh | Nội dung |
|---|---|---|
| Ngay sau khi về | ZNS | **Lời cảm ơn** + link **"Nội dung khám hôm nay"** trong tài khoản: chẩn đoán, việc đã làm, đơn thuốc, **lời dặn sau thủ thuật**, lịch hẹn tiếp |
| +24 giờ | Gọi điện / Zalo | Hỏi thăm, hỏi lại điểm đau (ca xâm lấn); bất thường → báo bác sĩ |
| +48 giờ | ZNS | **NPS 1 câu**. Điểm 9–10: mời đánh giá Google và giới thiệu. Điểm ≤ 6: mở phiếu phàn nàn cho Trưởng CSKH |
| Theo chu kỳ dịch vụ | ZNS + bảng việc | **Nhắc tái khám**: cạo vôi 6 tháng, chỉnh nha theo tháng, implant 1/3/6/12 tháng, bảo hành |
| Sinh nhật / dịp lễ | ZNS | Lời chúc + quà theo hạng |
| Thẻ bảo hành | Tài khoản | Thẻ bảo hành điện tử, nhắc trước khi hết hạn |

Bảng điều khiển hành trình hiển thị: tỷ lệ đến hẹn, no-show, NPS, tỷ lệ tái khám, doanh thu từ khách giới thiệu, CAC theo kênh.

### 5.2 Loyalty: chăm sóc, không ép mua

| Thành phần | Thiết kế |
|---|---|
| **Hạng thành viên** | Thành viên → Bạc → Vàng → Kim cương, xét theo **thực thu 12 tháng** và **mức độ gắn bó** (đúng lịch tái khám, giới thiệu) |
| **Điểm thưởng** | Tích theo thực thu; thưởng thêm khi tái khám đúng hẹn, giới thiệu thành công, hoàn thành khảo sát |
| **Ví gia đình** | Thành viên trong nhóm gia đình dùng chung hạng và điểm, phù hợp mô hình "cả nhà cùng chăm răng" |
| **Giới thiệu 2 chiều** | Người giới thiệu và người được giới thiệu cùng nhận quà; theo dõi doanh thu giới thiệu (KR 2.3) |
| **Gói chăm sóc định kỳ** | Thuê bao năm trả trước (ví dụ 2 lần khám + cạo vôi + X-quang): khách cam kết quay lại, phòng khám có dòng tiền ổn định và lấp ghế chiều |
| **Quyền lợi theo hạng** | Ưu tiên giờ đẹp, miễn phí phim kiểm tra, bảo hành mở rộng, quà sinh nhật |
| **Cầu chì y đức** | Không có ưu đãi kiểu "chỉ hôm nay" ép ký; mọi ưu đãi hiển thị minh bạch trong tài khoản |

Xây trên **Loyalty có sẵn** của Odoo/Bizapps (chương trình, phiếu, điểm), bổ sung hạng, ví gia đình, thuê bao và quy tắc theo hành vi.

---

## 6. Nhân sự: Lương 3P + OKR + KPI

```
Thu nhập = P1 (Vị trí) + P2 (Năng lực) + P3 (Kết quả)
```

| Thành phần | Nguồn dữ liệu trong ERP |
|---|---|
| **P1 – Vị trí** | Khung lương theo chức danh/bậc (Bác sĩ, Điều dưỡng/Phụ tá, Lễ tân điều phối, KTV, Tư vấn, Quản lý PK) |
| **P2 – Năng lực** | **Bậc lâm sàng** 1–3 (cây phân cấp Q-Summit) gắn với **phạm vi hành nghề**, chứng chỉ, đào tạo, thâm niên. Bậc quyết định dịch vụ được phép nhận trên lịch |
| **P3 – Kết quả** | (a) **OKR**: điểm KR cá nhân/khối lấy từ OKR Scale; (b) **KPI vận hành** theo JD (ví dụ Lễ tân: dữ liệu 20%, điều phối 20%, retention 25%, doanh số 20%, hài lòng 15%); (c) **Hoa hồng/thủ thuật phí** theo thực thu |

Nguyên tắc (theo OKR mẫu DMAG):
- OKR **đạt ~70% là thành công**. P3 không phạt khi chưa đạt 100%, chỉ khấu trừ khi **vi phạm cầu chì y đức**.
- KR **tự cập nhật** từ dữ liệu (NPS, thời gian chờ, điểm đau, ca niềng mới, tỷ lệ chốt, doanh thu giới thiệu, CAC, công suất ghế…). Không ai phải nhập tay, nên không ai "làm đẹp số".
- Check-in tuần (OKR Scale đã có) hiển thị cả **bản đồ tự tin** và **interlock** giữa các khối.
- Bảng lương 3P đẩy thẳng vào **Payroll Bizapps**, không viết lại phần tính thuế TNCN và bảo hiểm.

**Cách làm: demo trước, nạp chuẩn sau.**
1. Dựng cấu trúc dữ liệu **ngạch P (chuyên môn) và M (quản lý)**: ngạch → bậc → khung P1, tiêu chí P2, bộ chỉ tiêu P3 cho từng vị trí. Bản demo dùng dữ liệu mẫu từ các JD hiện có (Bác sĩ, Điều dưỡng, Lễ tân, KTV).
2. Khi DMAG chuẩn hóa xong hệ P/M cho từng vị trí, chỉ cần **nạp khung chuẩn** (import), không sửa code.
3. Gán ngạch/bậc vào **hồ sơ nhân viên**. Ứng dụng lương Bizapps đọc P1/P2/P3 như các khoản thu nhập, chạy bảng lương như hiện nay.

---

## 7. Thanh toán & hóa đơn (lễ tân can thiệp được bán hàng)

1. Lễ tân mở đơn từ lịch hẹn hoặc kế hoạch điều trị trên **POS / Bảng điều phối**. Lễ tân được thêm sản phẩm bán lẻ và áp ưu đãi trong hạn mức được phân quyền.
2. Khách thanh toán bằng **QR động VietQR do SePay sinh** (có sẵn số tiền và **mã thanh toán** trong nội dung chuyển khoản), quẹt thẻ POS hoặc tiền mặt.
3. SePay theo dõi tài khoản ngân hàng của phòng khám và gọi **webhook** khi có tiền vào. ERP khớp giao dịch theo mã thanh toán + số tiền (chống ghi trùng, ghi thiếu/thừa thì đưa vào hàng chờ xử lý), rồi **tự ghi nhận thanh toán và tự phát hành HĐĐT** qua HĐĐT Bizapps, rồi gửi hóa đơn qua Zalo/email.
   - Kết nối thanh toán viết theo dạng **adapter**: SePay là mặc định, đổi sang nhà cung cấp khác không phải sửa nghiệp vụ.
4. Cuối ca: **Chốt két 4 bước**: tiền mặt + POS + chuyển khoản khớp 100% phần mềm, lễ tân và thu ngân ký biên bản bàn giao (Sign), chênh lệch được cảnh báo về Buồng lái chủ phòng khám.

---

## 8. Hình ảnh & thiết bị: ánh xạ, không lưu file nặng

- Bệnh án lưu **tham chiếu** (UID, link viewer, ảnh thu nhỏ, răng liên quan, người chụp, thời điểm), **không lưu DICOM gốc**.
- Mức tích hợp theo thiết bị: (1) **DICOMweb/PACS**: truy vấn và mở ảnh trực tiếp; (2) **phần mềm hãng có deep-link**: mở đúng ca từ hồ sơ; (3) **thư mục xuất ảnh**: agent nhỏ tại phòng khám đọc metadata và đẩy liên kết lên ERP.
- Camera trong miệng: chụp ngay trong Chế độ Tư vấn; chỉ lưu ảnh JPEG nén (Documents).

---

## 9. Tuân thủ pháp lý

Làm chuẩn, không chạy theo hạn; mỗi phần đều kiểm thử tại phòng khám thí điểm trước khi mở rộng:
- EMR đạt yêu cầu TT 13/2025/TT-BYT: **chữ ký số** (adapter, chọn nhà cung cấp CA giá tốt và API thuận tiện sau), lưu trữ, phân quyền, nhật ký truy cập, khóa và sửa có vết, xuất bệnh án.
- Đơn thuốc: TT 52/2017 và TT 04/2022.
- HĐĐT: dùng tích hợp sẵn của Bizapps (NĐ 70/2025).
- Bảo vệ dữ liệu cá nhân: đồng ý của bệnh nhân, che dữ liệu nhạy cảm theo vai trò.
- Phạm vi hành nghề: **chặn xếp lịch/chỉ định ngoài phạm vi** giấy phép của bác sĩ.

> Các yêu cầu kỹ thuật chi tiết sẽ được đối chiếu với văn bản gốc trong *Thư mục Pháp luật Nha khoa* trước khi chốt đặc tả EMR.

---

## 10. Đóng gói ERP theo 5 phân khúc quy mô (DMAG)

| Gói | Phân khúc (Q-Summit) | Đặc điểm khách | Module trong gói |
|---|---|---|---|
| **DMAG Nền tảng** | PK1 · Xây nền · 1–2 ghế · < 200 tr/tháng (~4.200 PK) | Thiếu khách, tiền két lẫn ví cá nhân | A1–A4, A6–A8, B5, C3 (nhắc lịch cơ bản), E1 (Lễ tân + Bác sĩ) |
| **DMAG Khởi sắc** | PK2 · 2–4 ghế · 250–550 tr/tháng (~1.300 PK) | Rò rỉ két, lo rủi ro thuế | + A5, B2, B3, B4, C1, C2 cơ bản, D2 |
| **DMAG Tăng trưởng ★** | PK3 · Chạm trần · 4–7 ghế · 0,6–1,3 tỷ (~650 PK) | Chủ ngồi ghế 50–60 giờ/tuần, COGS > 25% | + B1, C1–C4 đầy đủ, D1 (3P), D3 (OKR), Chế độ Tư vấn, Buồng lái |
| **DMAG Doanh nghiệp** | PK4 · 6–10+ ghế · 1,4–2,5 tỷ (~220 PK) | Bị chuỗi ép giá vốn | + P&L theo ghế/bác sĩ, mua hàng tập trung qua liên minh DMAG, Studio, API mở |
| **DMAG Chuỗi** | PK5 · 2–10+ cơ sở · > 2,5 tỷ (~100 cơ sở) | Quản trị đa điểm, bài toán định giá | + D4, tổng đài CSKH tập trung, báo cáo hợp nhất, định giá doanh nghiệp |

Mỗi gói là một **module meta** (ví dụ `dmag_pack_growth`) chỉ khai báo `depends`. Khi lên gói chỉ cần cài thêm, dữ liệu giữ nguyên.

---

## 11. Lộ trình: làm chuẩn, thử nghiệm từng giai đoạn

Không ấn định ngày. Mỗi giai đoạn chỉ đóng khi **chạy thật tại phòng khám thí điểm** và đạt tiêu chí nghiệm thu, rồi mới sang giai đoạn sau.

| Giai đoạn | Phạm vi | Tiêu chí nghiệm thu tại phòng khám thí điểm |
|---|---|---|
| **GĐ 1 – Vận hành lõi** | A1–A4, A6, A7 (SePay + HĐĐT), A8, B5, E1 (Bàn làm việc Bác sĩ + Bảng điều phối Lễ tân), C3 (nhắc lịch ZNS) | Một ngày phòng khám chạy trọn trên ERP: hẹn → check-in → khám → thu tiền → HĐĐT → chốt két khớp 100% |
| **GĐ 2 – Trải nghiệm & tăng trưởng** | A5, B1–B4, C1, C2, C4, Chế độ Tư vấn | Hành trình Trước–Trong–Sau chạy tự động; NPS, tái khám đo được |
| **GĐ 3 – Con người & quản trị** | D1 (demo P/M + 3P → nạp khung chuẩn), D2, D3, Buồng lái | Bảng lương 3P chạy song song 1 kỳ, khớp với cách tính hiện tại |
| **GĐ 4 – Quy mô** | D4, gói Doanh nghiệp/Chuỗi, API cho app bệnh nhân | Thí điểm thêm 1 phòng khám ở phân khúc khác |
---

## 12. Còn cần anh/chị cung cấp hoặc xác nhận

0. **ACS HMS**: khuyến nghị tự dựng lõi `dmag_*`, chỉ dùng ACS làm tham khảo. Xem [DANH_GIA_ACS_HMS.md](DANH_GIA_ACS_HMS.md).

1. **Quyền xem hệ thống Odoo Bizapps đang chạy** (tài khoản dùng thử riêng) và/hoặc danh sách addons, source.
2. **Tài khoản SePay** (môi trường thử) để dựng QR động + webhook.
3. **Danh sách thiết bị/phần mềm hình ảnh** khi đã rõ, chưa cần ngay (GĐ 2).
4. **Nhà cung cấp chữ ký số** khi đã chọn, hệ thống viết sẵn adapter.
5. **Phòng khám thí điểm** cho GĐ 1.
6. Khung ngạch bậc **P/M** và 3P chuẩn: chưa cần, GĐ 3 dựng bản demo trước.
