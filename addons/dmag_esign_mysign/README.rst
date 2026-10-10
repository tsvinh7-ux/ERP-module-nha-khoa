=================================
DMAG – Ký số Viettel MySign
=================================

Ký số từ xa bệnh án và chứng từ y tế bằng **Viettel MySign**: bác sĩ xác nhận ký trên
ứng dụng MySign trong điện thoại, không cần USB token. Căn cứ: TT 13/2025/TT-BYT Điều 3
(ký, xác nhận điện tử trong hồ sơ bệnh án điện tử bằng chữ ký điện tử hợp pháp).

Chức năng
=========

* **Khung ký số dùng chung**: ``dmag.esign.request`` (hồ sơ ký số: tài liệu, mã băm SHA-256,
  tệp chưa ký, chữ ký rời / PDF đã ký, bác sĩ ký, nhà cung cấp, trạng thái, mã giao dịch,
  thông tin chứng thư, nhật ký) và mixin ``dmag.esign.mixin`` cho mọi module.
* **Nhà cung cấp** ``dmag.esign.provider`` theo phòng khám: ``mysign`` (API thật) hoặc
  ``mock`` (khóa tự ký, chỉ demo / kiểm thử – không có giá trị pháp lý).
* **Bệnh án lượt khám**: bấm "Ký bệnh án" → khóa bệnh án → dựng bản in (mẫu EMR
  ``dmag_dental_emr.action_report_dental_record`` nếu đã cài, nếu không dùng mẫu SOAP của module
  này) → gửi yêu cầu ký MySign → khi ký xong đính tài liệu + chữ ký lên chatter lượt khám, cập nhật
  ``esign_state``. Chưa cấu hình nhà cung cấp thì chỉ khóa bệnh án như cũ (ghi chú trên chatter).
* Nút **"Kiểm tra trạng thái ký"**, **"Gửi lại ký số"**; tác vụ định kỳ 2 phút hỏi trạng thái
  các yêu cầu đang chờ, tự chuyển "Hết hạn" sau thời hạn cấu hình.
* Hồ sơ bác sĩ: tài khoản MySign, credential, serial, hạn chứng thư (cảnh báo sắp hết / hết hạn;
  **chứng thư hết hạn thì chặn ký**).
* Phân quyền: bác sĩ tạo yêu cầu ký cho chính mình, xem hồ sơ ký số; chỉ Giám đốc sửa / xóa,
  cấu hình nhà cung cấp và xem Client ID / Client secret. Quy tắc theo phòng khám (``company_id``).

Dùng từ module khác
===================

::

    class Prescription(models.Model):
        _name = 'dmag.prescription'
        _inherit = ['mail.thread', 'dmag.esign.mixin']   # thêm esign_request_id, esign_state

        def action_sign(self):
            # trả về recordset dmag.esign.request (KHÔNG gắn trực tiếp vào nút bấm)
            self.action_request_esign('dmag_dental_prescription.action_report_prescription',
                                      signer=self.doctor_id)
            return True

        def _dmag_on_esign_done(self, request):
            res = super()._dmag_on_esign_done(request)   # đính chữ ký lên chatter, cập nhật esign_state
            ...                                           # khóa đơn, gửi liên thông đơn thuốc
            return res

Chữ ký: ``action_request_esign(report_ref=None, signer=None, document_name=None, provider=None)``.
Có thể ghi đè ``_dmag_esign_report_ref()``, ``_dmag_esign_signer()``, ``_dmag_esign_document_name()``,
``_dmag_esign_render()``, ``_dmag_on_esign_failed(request)``.

Cài đặt / vận hành
==================

1. **Đăng ký dịch vụ** với Viettel-CA: hợp đồng MySign cho tổ chức (phòng khám) + gói tích hợp
   API ký từ xa (Remote Signing). Yêu cầu tài liệu API bản mới nhất và môi trường thử (UAT).
2. Viettel-CA cấp **địa chỉ API**, **Client ID**, **Client secret**, **Profile / Service ID**.
   Vào *Nha khoa → Cấu hình → Ký số (MySign)*, tạo nhà cung cấp loại "Viettel MySign", nhập các
   giá trị trên (chỉ Giám đốc thấy secret), bấm "Thử kết nối".
3. Mỗi bác sĩ cài ứng dụng **MySign**, đăng ký / kích hoạt chứng thư số cá nhân (eKYC bằng CCCD).
4. *Hồ sơ bác sĩ*: nhập **Tài khoản MySign** (mã người dùng / số CCCD), bấm "Lấy thông tin chứng thư"
   để lưu credential, serial, hạn chứng thư.
5. Bật tác vụ định kỳ "Ký số: kiểm tra trạng thái yêu cầu đang chờ MySign" (mặc định 2 phút).
6. Máy chủ in PDF cần **wkhtmltopdf** (0.12.6 có patch Qt). Thiếu wkhtmltopdf hệ thống băm và ký
   bản HTML của bệnh án (ghi rõ định dạng trên hồ sơ ký).

Chữ ký trong PDF (PAdES)
------------------------

Hiện hệ thống lưu **chữ ký rời** cạnh tài liệu: ``.p7s`` (CMS – nhà cung cấp giả lập) hoặc
``.sig.json`` (chữ ký PKCS#1 trên mã băm SHA-256 + chứng thư + mã giao dịch MySign); chữ ký PKCS#1
được kiểm tra khớp chứng thư trước khi chấp nhận. Muốn chữ ký **nhúng trong PDF** (mở bằng Adobe /
Foxit thấy chữ ký hợp lệ) cần cài trên máy chủ ``pyhanko`` (khuyến nghị) hoặc ``endesive`` và bật
luồng ký 2 pha (chuẩn bị PDF có vùng chữ ký → băm *signed attributes* → MySign ký → nhúng CMS) tại
``dmag.esign.request._dmag_embed_pades()``. Module **không** khai báo cứng các thư viện này.

Cần xác nhận
============

* **Endpoint** (đang mặc định, sửa được trên form nhà cung cấp; logic gom trong
  ``models/mysign_client.py``): ``/vtss/service/ras/v1/login`` (token),
  ``/vtss/service/certificates/info`` (chứng thư), ``/vtss/service/signHash`` (ký hash),
  ``/vtss/service/requests/status`` (trạng thái giao dịch – **chưa tìm thấy tài liệu công khai**).
* **Tên trường payload / response**: ``client_id``, ``client_secret``, ``user_id``, ``profile_id``,
  ``credentialID``, ``hash`` (base64), ``hashAlgo``/``signAlgo`` (OID), ``async``,
  ``transactionId``, ``signatures``, mã trạng thái (``STATUS_MAP``) và mã lỗi.
* MySign trả **PKCS#1** (raw) hay **CMS** cho ký hash; có hỗ trợ ký *signed attributes* cho PAdES.
* **Thư viện PAdES**: ``pyhanko`` hay ``endesive``; chuẩn PAdES-B-LTA (dấu thời gian, OCSP/CRL của
  Viettel-CA) theo yêu cầu lưu trữ dài hạn.
* Thời hạn chờ bác sĩ xác nhận trên điện thoại (mặc định 10 phút) và giới hạn tần suất gọi API.
* Mã người dùng MySign là số CCCD hay mã riêng do Viettel cấp.
