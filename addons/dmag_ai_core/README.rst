==========================
DMAG – Trợ lý AI (nền tảng)
==========================

Cổng gọi AI dùng chung cho mọi tính năng AI của DMAG Dental ERP (AI-00 trong ``docs/DE_XUAT_AI.md``).

Chế độ
======
* **Giả lập** (mặc định): không gọi AI thật, không tốn phí – mỗi tính năng trả kết quả mẫu dựng từ dữ liệu thật
  của Odoo. Nhật ký vẫn ghi *chi phí ước tính nếu chạy thật*.
* **Claude API**: nhập khóa API tại *Nha khoa → Cấu hình → Trợ lý AI → Cài đặt AI* (chỉ Giám đốc). Cần thư viện
  ``anthropic`` trên máy chủ (``pip install anthropic``).

Bảo vệ dữ liệu
==============
* Ẩn danh trước khi gửi: họ tên, SĐT, CCCD, email, địa chỉ bệnh nhân được thay bằng mã ``[BN_1]``, ``[SĐT_1]``…,
  ghép lại khi nhận kết quả; công cụ (tool) nhận lại giá trị thật ở phía Odoo.
* Tính năng có dữ liệu bệnh nhân đòi hỏi bệnh nhân **đồng ý hỗ trợ bằng AI** (trường trên hồ sơ, có thời điểm).
* Nhật ký ``dmag.ai.log`` (ai, khi nào, tính năng, hồ sơ, token, chi phí, nội dung đã ẩn danh) – không sửa/xóa.
* Trần chi phí tháng: vượt trần → tạm dừng tới đầu tháng sau.

Dùng trong module khác
======================
.. code-block:: python

    res = self.env['dmag.ai'].run(
        'AI-04', system='Tóm tắt hồ sơ…', user=noi_dung, patient=partner, record=visit,
        schema={...},                       # tùy chọn: JSON schema → res['data']
        tools=[...], tool_handlers={...},   # tùy chọn: AI tra/ghi Odoo qua hàm được phép
        simulate=lambda: {'text': '…', 'data': {...}})
    res['text'], res['data'], res['simulated'], res['cost_vnd'], res['estimated_cost_vnd']

Mô hình mặc định Claude Opus 5.5 (chọn được Sonnet 5.5 / Haiku 5.5 cho từng tính năng), suy luận thích ứng,
bộ nhớ đệm cho hướng dẫn hệ thống, ``fallbacks="default"`` khi AI từ chối.
