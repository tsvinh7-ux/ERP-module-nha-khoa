# NGHIÊN CỨU: THUÊ DỊCH VỤ GIỌNG NÓI (AI-01) VÀ RÀ SOÁT DỰ ÁN NGUỒN MỞ

> Ngày 11/10/2026 · Bổ sung cho [`DE_XUAT_AI.md`](DE_XUAT_AI.md).
> Chỉ đạo của chủ phòng khám: *"thuê đi vì Odoo sau này sẽ chạy online, chú ý kiểm tra xem có thực sự cần không, cũng như quét 1 số bên có public trên GitHub"*.
> Quy ước: **[CẦN XÁC MINH]** = chưa đọc được văn bản / trang gốc. Môi trường nghiên cứu chặn nhiều tên miền `.vn` và một số trang nhà cung cấp, nên phần đó dựa trên kết quả tìm kiếm và ghi rõ nguồn.

## Tóm tắt

| Câu hỏi | Trả lời ngắn |
|---|---|
| Có cần dịch vụ chuyển giọng nói thành chữ (STT) riêng không? | **Có.** Claude API **không nhận âm thanh**, nên phải có bước giọng nói → chữ trước khi gọi Claude. |
| Dùng nhận dạng giọng nói có sẵn trong trình duyệt được không? | **Được cho demo và vài ngày thí điểm, chưa dùng được khi vận hành thật.** Âm thanh đi tới Google mà không có hợp đồng xử lý dữ liệu. Chế độ nghe liên tục hay tự ngắt, chạy kém trên iPad/Safari, không có từ điển chuyên ngành và không có nhật ký. |
| Thuê dịch vụ nào? | **Chính: FPT.AI Speech-to-Text** (hạ tầng trong nước, hợp đồng và hóa đơn VNĐ). **Dự phòng: Google Cloud Speech-to-Text Chirp 3 (vi-VN)**. Chọn chính thức sau khi chạy **thử so sánh 1 tuần** trên ghi âm thật. |
| Chi phí (780 lượt × 5 phút ≈ 3.900 phút/tháng) | FPT.AI khoảng **2,5–3,1 triệu đ/tháng**. Google Chirp 3 thời gian thực khoảng **1,6 triệu đ/tháng**; nếu xử lý theo lô thì khoảng **0,3 triệu đ/tháng**. |
| Dự án GitHub nên dùng | **Học cách làm:** `odoopilot` (LGPL-3, Odoo 17) và `apexive/odoo-llm` (LGPL-3). **Dự phòng tự chạy:** `ViStreamASR` (MIT, chạy được bằng CPU) và `PhoWhisper`. **Không dùng cho thương mại:** dữ liệu nha khoa DENTEX (CC BY-NC-SA), mô hình wav2vec2 tiếng Việt (CC BY-NC). |

---

## 1. Có thực sự cần dịch vụ chuyển giọng nói thành chữ riêng không?

### 1.1 Claude không nhận âm thanh, nên bắt buộc có bước STT

Theo tài liệu API Messages của Anthropic, tin nhắn chỉ nhận các khối `text`, `image`, `document`, `search_result`, `tool_use`/`tool_result`… và **không có khối `audio`**. Phần thị giác chỉ nhận ảnh JPEG/PNG/GIF/WebP ([Messages API](https://platform.claude.com/docs/en/api/messages/create), [Vision](https://platform.claude.com/docs/en/build-with-claude/vision)). Nhiều yêu cầu bổ sung tính năng âm thanh vẫn còn mở trên GitHub tới năm 2026 ([ví dụ](https://claudeissues.com/issue/73566-feature-allow-claude-to-hear-and-process-audio)).

→ Quy trình của AI-01 gồm 3 bước:

**Ghi âm (trình duyệt) → STT → chữ thô → ẩn danh (`dmag_ai_core`) → Claude điền mẫu 16/BV1 → bác sĩ sửa và ký.**

(Gemini và GPT-4o nhận được âm thanh trực tiếp. Tuy nhiên, khi đó **âm thanh thô có tên bệnh nhân sẽ đi ra nước ngoài**, trái với thiết kế "chỉ gửi văn bản đã ẩn danh" ở DE_XUAT_AI mục 0.)

### 1.2 Phương án (a): nhận dạng giọng nói có sẵn trong trình duyệt (Web Speech API, `webkitSpeechRecognition`, `lang='vi-VN'`)

| Tiêu chí | Đánh giá |
|---|---|
| Chi phí | 0 đ |
| Âm thanh đi đâu | Mặc định trên Chrome, âm thanh **được gửi tới máy chủ Google**. Thuộc tính mới `processLocally = true` buộc xử lý ngay trên máy, nhưng danh sách ngôn ngữ chạy tại máy còn hạn chế; chưa thấy xác nhận có vi-VN **[CẦN XÁC MINH]** ([đặc tả và thảo luận W3C](https://tag-github-bot.w3.org/gh/w3ctag/design-reviews/1189), [Edge docs](https://learn.microsoft.com/fi-fi/microsoft-edge/web-platform/speech-recognition-api)) |
| Hợp đồng và trách nhiệm | **Không có** hợp đồng xử lý dữ liệu với Google. Đây là chuyển dữ liệu sức khỏe ra nước ngoài mà không có hồ sơ (xem mục 3) |
| Chế độ nghe liên tục (`continuous`) | Chrome tự dừng sau vài giây im lặng, phải tự bật lại trong `onend` ([issue](https://github.com/WebAudio/web-speech-api/issues/96)) |
| Safari / iPad | Hỗ trợ từ Safari 14.1, nhưng chế độ liên tục **không ổn định trên iOS**: không ra chữ, không dừng micro. Cách khắc phục là "giữ để nói" ([Apple forum](https://developer.apple.com/forums/thread/699881), [bài viết](https://lilting.ch/en/articles/ios-webspeech-api-tips)) |
| Firefox | Không dùng được trong thực tế |
| Từ điển chuyên ngành | Không có (không thể "dạy" các từ như *viêm tủy không hồi phục*, *R36*, *composite*, *chụp sứ*) |
| Độ chính xác tiếng Việt | Chấp nhận được với câu thường; **chưa có số đo cho thuật ngữ nha khoa** |

**Kết luận (a):** dùng **cho demo** ngay (gần như không tốn công: khoảng 50 dòng JS trong widget Odoo) và cho **1–2 bác sĩ thí điểm vài ngày, đọc dữ liệu giả hoặc có đồng ý bằng văn bản**. **Không dùng khi vận hành thật** với hồ sơ bệnh nhân.

### 1.3 Phương án (b): nhà cung cấp Việt Nam

| | FPT.AI STT | Viettel AI (ASR) | VNPT SmartVoice | Zalo AI |
|---|---|---|---|---|
| Kiểu API | REST, gửi tệp âm thanh (POST) ([docs](https://docs.fpt.ai/docs/en/speech/api/speech-to-text)). Gửi liên tục theo luồng / websocket **[CẦN XÁC MINH]** | Có API **[CẦN XÁC MINH kiểu streaming]** ([viettelai.vn](https://viettelai.vn/en/chuyen-giong-noi)) | Nhận cả luồng âm thanh trực tiếp và tệp ([salekit](https://smartvoice.vnpt.vn/en_salekit.pdf)) | **Không thấy API STT công khai**; chỉ có TTS và wrapper không chính thức ([zalo-tts](https://github.com/iconclub/zalo-tts)) |
| Giá | Dùng thử 60 phút/năm. Gói Business: 2.000 phút = 1,4 tr đ; 5.000 phút = 3,1 tr đ; 10.000 phút = 5,4 tr đ (≈540–700 đ/phút) ([bảng giá](https://docs.fpt.ai/docs/en/speech/documentation/stt-pricing)). Một trang cũ ghi theo USD, số liệu không khớp. **[CẦN XÁC MINH gói theo tháng hay trọn gói]** | Không công bố, phải hỏi báo giá | Không công bố, phải hỏi báo giá | – |
| Dữ liệu nằm ở đâu | Việt Nam (theo hợp đồng) **[CẦN XÁC MINH cam kết lưu trữ và xóa]** | Việt Nam | Việt Nam | – |
| Từ chuyên ngành | Tự quảng cáo là nhận đúng tên riêng, ngày tháng, số điện thoại, có kênh "tùy chỉnh theo khách hàng" ([fpt.ai/stt](https://fpt.ai/stt)); **không có số đo y khoa** | **[CẦN XÁC MINH]** | **[CẦN XÁC MINH]** | – |
| SDK | REST đơn giản, gọi thẳng từ Python (`requests`) | REST | REST | – |

### 1.4 Phương án (c): nhà cung cấp quốc tế

| Dịch vụ | vi-VN | Kiểu | Giá tham khảo | Ghi chú |
|---|---|---|---|---|
| **Google Cloud STT v2 – Chirp 3** | **Có** (streaming, gọi đồng bộ, theo lô) ([docs](https://cloud.google.com/speech-to-text/v2/docs/chirp_3-model?hl=en)) | gRPC streaming / REST | ~0,016 USD/phút thời gian thực; theo lô **0,003 USD/phút** ([pricing](https://cloud.google.com/speech-to-text/pricing/)) | Chọn được vùng `asia-southeast1` (Singapore) **[CẦN XÁC MINH vùng GA]**. vi-VN **không có** tách người nói. Từ điển chuyên ngành cho Chirp 3 **[CẦN XÁC MINH]** |
| Azure AI Speech | Có vi-VN | WebSocket SDK (JS/Python) | ~1 USD/giờ thời gian thực (bên thứ ba), theo lô ~0,18 USD/giờ ([Dasha](https://dasha.ai/blog/speech-to-text-pricing)) | Có "phrase list" (tối đa ~500 cụm, áp dụng cho vi-VN **[CẦN XÁC MINH]**) và Custom Speech |
| AWS Transcribe | **Có vi-VN** cả theo lô và streaming; các tính năng phụ cho vi-VN đều "không" ([docs](https://docs.aws.amazon.com/transcribe/latest/dg/supported-languages.html)) | WebSocket / HTTP2 | ~0,024 USD/phút **[CẦN XÁC MINH]** | Đắt nhất trong nhóm |
| OpenAI `gpt-4o-transcribe` / `-mini` / `whisper-1` | Có (đa ngữ) | REST (tệp); có biến thể realtime | 0,006 / 0,003 / 0,006 USD/phút ([tổng hợp](https://costgoat.com/pricing/openai-transcription)) **[CẦN XÁC MINH trang chính thức]** | Có tham số `prompt` để gợi ý thuật ngữ |
| Soniox | Có | WebSocket + REST | ~0,10–0,12 USD/**giờ** ([so sánh](https://soniox.com/compare-stt/soniox-vs-google/vietnamese)) | Tự công bố tỷ lệ lỗi từ (WER) tiếng Việt 1,25% (số của chính hãng). Hỗ trợ ngữ cảnh / thuật ngữ |
| Deepgram Nova-3 | **Chưa xác nhận** vi ([changelog](https://developers.deepgram.com/changelog/2026/8/7)) | WebSocket | – | **[CẦN XÁC MINH]** |
| AssemblyAI | Có trang tiếng Việt ([link](https://www.assemblyai.com/languages/vietnamese)); model hỗ trợ chưa rõ | REST + streaming | 0,15–0,21 USD/giờ; Medical Mode +0,15 USD/giờ ([pricing](https://www.assemblyai.com/pricing.md)) | Medical Mode có hỗ trợ tiếng Việt không: **[CẦN XÁC MINH]** |

Tất cả phương án quốc tế đều là **chuyển dữ liệu (giọng nói của bác sĩ, có thể có tên bệnh nhân) ra nước ngoài**, nên phải có hồ sơ theo Luật 91/2025 (mục 3).

### 1.5 Chi phí tháng cho 3.900 phút (780 lượt × 5 phút; tỷ giá 26.000 đ/USD)

| Dịch vụ | USD/tháng | ≈ VNĐ/tháng |
|---|---|---|
| Web Speech API (trình duyệt) | 0 | 0 |
| **FPT.AI** (2 gói × 2.000 phút, hoặc gói 5.000 phút) | – | **2,8–3,1 tr** (nếu gói không cộng dồn sang tháng sau) |
| Viettel / VNPT | – | báo giá **[CẦN XÁC MINH]** |
| **Google Chirp 3**, thời gian thực | ~62 | ~1,6 tr |
| Google Chirp 3, theo lô (chữ ra sau vài phút) | ~12 | ~0,3 tr |
| OpenAI gpt-4o-transcribe / mini | ~23 / ~12 | ~0,6 / ~0,3 tr |
| Azure thời gian thực | ~65 | ~1,7 tr |
| AWS Transcribe | ~94 | ~2,4 tr |
| Soniox | ~8 | ~0,2 tr |

Thực tế bác sĩ thường chỉ nói 1–2 phút mỗi lượt, nên chi phí thật có thể chỉ bằng **1/3** bảng trên. Phần Claude điền mẫu (~1 tr đ/tháng) đã có trong DE_XUAT_AI mục 4.

### 1.6 Đề xuất thuê

1. **Chính: FPT.AI STT.** Lý do:
   - âm thanh ở **trong nước**, không phát sinh hồ sơ chuyển dữ liệu ra nước ngoài cho phần nhạy cảm nhất;
   - hợp đồng và hóa đơn VAT bằng VNĐ;
   - API REST đơn giản.

   Cách dùng phù hợp với kiểu REST: bác sĩ bấm **Ghi**, nói, bấm **Dừng**; Odoo gửi tệp, khoảng 2–5 giây sau có chữ. Không cần chữ chạy theo thời gian thực.
2. **Dự phòng: Google Cloud STT Chirp 3 (vi-VN).** Có streaming, giá theo lô rất rẻ, SLA doanh nghiệp, chọn được vùng. Chỉ bật khi FPT lỗi hoặc kém, và **sau khi** đã có hồ sơ chuyển dữ liệu ra nước ngoài cùng đồng ý của bệnh nhân.
3. **Thử so sánh 1 tuần trước khi ký:**
   - ghi 30 đoạn đọc bệnh án thật (giọng các bác sĩ, có tiếng máy nha);
   - chạy qua FPT, Viettel, Google Chirp 3, gpt-4o-transcribe, Soniox;
   - đo **tỷ lệ lỗi thuật ngữ nha khoa** (số răng, ký hiệu FDI, tên thủ thuật, mã ICD), không chỉ tỷ lệ lỗi từ (WER) chung.

   Nếu Viettel hoặc VNPT tốt hơn FPT thì đổi nhà cung cấp chính. Nhờ công tắc chọn nguồn trong `dmag_ai_core`, việc đổi không phải sửa nghiệp vụ.
4. **Demo và thí điểm:** dùng ngay **Web Speech API trên Chrome/Edge** làm nguồn `browser` trong `dmag_ai_core`. Mặc định **tắt** khi vận hành thật.
5. Kỹ thuật:
   - ghi âm bằng `MediaRecorder` (webm/opus), gửi về một controller Odoo;
   - lớp `dmag.ai.stt.provider` có các adapter `browser | fpt | viettel | google | openai`;
   - **không lưu âm thanh lâu dài** (xóa sau khi bác sĩ ký, hoặc giữ tối đa N ngày, có mã hóa);
   - ghi nhật ký số phút để tính vào trần chi phí.

Việc tự chạy (LOCAL) không còn phù hợp vì Odoo sẽ chạy trên đám mây. Nếu sau này muốn bớt phụ thuộc nhà cung cấp, `ViStreamASR` chạy được **chỉ bằng CPU** (mục 2.1) và có thể thử trên chính máy chủ Odoo.

---

## 2. Rà soát dự án nguồn mở trên GitHub (số liệu lấy ngày 11/10/2026)

Quy tắc giấy phép với module Odoo LGPL-3:

- **dùng lại được**: MIT, BSD, Apache-2.0, LGPL, MPL-2.0;
- **cẩn trọng**: AGPL-3 (buộc công bố mã khi chạy qua mạng nếu gộp vào module của mình);
- **không dùng cho thương mại**: CC BY-NC / NC-SA.

### 2.1 Nhận dạng giọng nói tiếng Việt

| Dự án | ★ | Hoạt động gần nhất | Giấy phép | Phù hợp | Kết luận |
|---|---|---|---|---|---|
| [VinAIResearch/PhoWhisper](https://github.com/VinAIResearch/PhoWhisper) | 259 | push 11/2024 | BSD-3 (GitHub); README ghi Apache-2.0 **[CẦN XÁC MINH]** | Whisper tinh chỉnh trên 844 giờ tiếng Việt; WER bản large: CommonVoice 8,14 / VIVOS 4,67 ([paper](https://arxiv.org/abs/2406.02555)). Cần GPU để chạy nhanh | **Dự phòng tự chạy** (máy GPU thuê theo giờ), không dùng ngay |
| [nguyenvulebinh/ViStreamASR](https://github.com/nguyenvulebinh/ViStreamASR) | 64 | 10/2026 | **MIT** | Nhận dạng liên tục, độ trễ ~640 ms, **chạy CPU** (RTF ~0,34, ≥5 GB RAM), cài bằng `pip` | **Thử trong đợt so sánh**: phương án tự chạy rẻ nhất trên máy chủ đám mây |
| [dangvansam/viet-asr](https://github.com/dangvansam/viet-asr) | 179 | – | Apache-2.0 | QuartzNet 13M tham số, kiến trúc cũ | Tránh |
| [vietai/ASR](https://github.com/vietai/ASR) | 105 | 2021 | – | wav2vec2 | Chỉ để học |
| `nguyenvulebinh/wav2vec2-base-vietnamese-250h` (HF) | – | – | **CC BY-NC 4.0** ([model card](https://huggingface.co/nguyenvulebinh/wav2vec2-base-vietnamese-250h)) | – | **Tránh** (cấm thương mại) |
| [Vietnamese Open ASR Leaderboard](https://vietaudio-team-vietnamese-asr-leaderboard.hf.space/) | – | 2026 | – | Có các mô hình parakeet-ctc-0.6b-Vietnamese (NVIDIA), PhoWhisper, Qwen3-ASR | Dùng để chọn mô hình nếu tự chạy |
| [huuquyet/PhoWhisper-next](https://github.com/huuquyet/PhoWhisper-next) | 8 | 09/2025 | MIT | PhoWhisper chạy **ngay trong trình duyệt** (Transformers.js/ONNX) | Học: hướng xử lý trên máy bác sĩ, âm thanh không rời máy (máy yếu sẽ chậm) |

### 2.2 Module AI / LLM cho Odoo

| Dự án | ★ | Odoo | Giấy phép | Kết luận |
|---|---|---|---|---|
| [arunrajiah/odoopilot](https://github.com/arunrajiah/odoopilot) | 21 | **17.0** và 18.0 (beta) | **LGPL-3** | **Học và có thể dùng lại từng phần**: đã có client Anthropic, chuyển giọng nói Whisper, vòng gọi công cụ chạy theo quyền người dùng Odoo, **nhật ký từng thao tác AI**, xác nhận Có/Không trước khi ghi dữ liệu. Rất gần ý tưởng `dmag_ai_core`. Dự án nhỏ, đang beta |
| [apexive/odoo-llm](https://github.com/apexive/odoo-llm) | 219 | 16.0, 18.0, 19.0; **17.0 chỉ có nhánh `17.0-backport-migration`** | **LGPL-3** | **Học kiến trúc** (`llm`, `llm_anthropic`, `llm_tool`, `llm_assistant`). Đưa về Odoo 17 tốn công, 49 issue đang mở |
| [OCA/ai](https://github.com/OCA/ai) | 56 | chỉ thấy 19.0 (`ai_tool`) | AGPL-3 (mặc định repo) | Theo dõi; chưa dùng |
| [ivnvxd/mcp-server-odoo](https://github.com/ivnvxd/mcp-server-odoo) | 402 | 16.0+ (cần module MCP phía Odoo) | MPL-2.0 | Tùy chọn cho AI-13: cho Claude đọc Odoo qua MCP, phân quyền theo từng model. **Chỉ chế độ có module, không dùng chế độ "YOLO"** |
| [erpipe-org/mcp-odoo](https://github.com/erpipe-org/mcp-odoo) | 421 | – | **[CẦN XÁC MINH]** | So sánh với mục trên |
| [thespino/odoogpt](https://github.com/thespino/odoogpt) | 23 | 16.0 | – | Tránh (cũ, chỉ OpenAI) |

### 2.3 AI nha khoa (AI-06, AI-19)

| Dự án | ★ | Giấy phép | Kết luận |
|---|---|---|---|
| [ibrahimethemhamamci/DENTEX](https://github.com/ibrahimethemhamamci/DENTEX) (MICCAI 2023) | 121 | Mã nguồn MIT; **dữ liệu CC BY-NC-SA 4.0** | Chỉ học / nghiên cứu: 1.005 phim toàn cảnh có nhãn (sâu răng, sâu sâu, tổn thương chóp, răng ngầm), đánh số FDI. **Không dùng thương mại** |
| [HierarchicalDet](https://github.com/ibrahimethemhamamci/HierarchicalDet) | 110 | **[CẦN XÁC MINH]** | Học |
| [SerdarHelli/Segmentation-of-Teeth…U-Net](https://github.com/SerdarHelli/Segmentation-of-Teeth-in-Panoramic-X-ray-Image-Using-U-Net) | 168 | **[CẦN XÁC MINH]** | Học |
| [Zzz512/MLUA](https://github.com/Zzz512/MLUA) (phân vùng sâu răng) | 43 | **[CẦN XÁC MINH]** | Học |
| [KitwareMedical/SlicerCBCTToothSegmentation](https://github.com/KitwareMedical/SlicerCBCTToothSegmentation), [DCBIA-OrthoLab/SlicerDentalModelSeg](https://github.com/DCBIA-OrthoLab/SlicerDentalModelSeg) | 38 / 89 | **[CẦN XÁC MINH]** | Công cụ cho bác sĩ chỉnh nha (3D Slicer), không phải module ERP |
| Tufts Dental Database (các repo chuyển định dạng [Tufts2COCO](https://github.com/li-pengcheng/Tufts2COCO)) | – | dữ liệu dùng cho nghiên cứu **[CẦN XÁC MINH]** | Học |
| Thiết kế nụ cười (smile design) | – | – | Không tìm thấy dự án nguồn mở đủ tốt → thuê nhà cung cấp chuyên ngành (giữ nguyên DE_XUAT_AI) |

→ **Không tự huấn luyện mô hình đọc phim để dùng thật.** Dữ liệu công khai đều cấm thương mại, và phần mềm chẩn đoán nhiều khả năng là trang thiết bị y tế (mục 3). Giữ hướng "nhà cung cấp đã được cấp phép".

### 2.4 CCCD và Zalo OA

| Mục | Kết quả | Kết luận |
|---|---|---|
| Đọc QR CCCD | Chỉ có các repo cá nhân 0–1★ ([vonguyendang/cccd-qr-excel](https://github.com/vonguyendang/cccd-qr-excel), [lequocvan/QR_Code_Scanner](https://github.com/lequocvan/QR_Code_Scanner)…), không có thư viện chuẩn | **Tự viết** (khoảng 30 dòng): tách chuỗi bằng dấu `\|` theo thứ tự `Số định danh\|Số CMND cũ\|Họ tên\|NgàySinh ddmmyyyy\|Giới tính\|Địa chỉ\|Ngày cấp`. Thứ tự này **[CẦN XÁC MINH]** trên thẻ thật, nhất là thẻ căn cước mẫu 2024 (có thể khác). Quét bằng camera: `html5-qrcode` hoặc `@zxing/library` (Apache-2.0); máy quét cầm tay thì nhận như bàn phím, không cần thư viện |
| Zalo OA | SDK PHP chính thức [zaloplatform/zalo-php-sdk](https://packagist.org/packages/zaloplatform/zalo-php-sdk) (v4.0.4, 12/2023); không có SDK Python chính thức. Có SDK cộng đồng: npm `zalo-sdk`, `@warriorteam/redai-zalo-sdk`, [TheOwlOps/ChannelHub](https://github.com/TheOwlOps/ChannelHub) | **Gọi thẳng REST OA/ZNS từ Odoo (Python)**, tham khảo SDK PHP. **Tránh** thư viện tự động hóa **tài khoản Zalo cá nhân** (vi phạm điều khoản Zalo, dễ bị khóa) |

---

## 3. Lưu ý pháp lý (Việt Nam)

| Văn bản | Nội dung liên quan | Ảnh hưởng tới lựa chọn |
|---|---|---|
| **Luật Bảo vệ dữ liệu cá nhân số 91/2025/QH15**, thông qua 26/6/2025, **hiệu lực 01/01/2026** ([LuatVietnam](https://luatvietnam.vn/legal-updates/the-latest-law-on-personal-data-protection-and-the-guiding-documents-892-106778-article.html), [tóm tắt](https://datatech.apolatlegal.com/?p=557)) | Dữ liệu sức khỏe là dữ liệu nhạy cảm; áp dụng cả với tổ chức nước ngoài xử lý dữ liệu người Việt. Vi phạm về chuyển dữ liệu ra nước ngoài bị phạt tới **5% doanh thu**, vi phạm khác tối đa **3 tỷ đ** (theo trang tổng hợp) **[CẦN XÁC MINH điều khoản]** | Âm thanh và chữ thô có tên bệnh nhân **nên ở trong nước** → ưu tiên FPT/Viettel. Gửi ra Google/OpenAI phải có hồ sơ và đồng ý |
| **Nghị định 356/2025/NĐ-CP** (ban hành 31/12/2025, hiệu lực 01/01/2026), **thay thế NĐ 13/2023** ([EY](https://www.ey.com/vi_vn/technical/tax/tax-and-law-updates/nghi-dinh-so-356-2025-nd-cp-quy-dinh-chi-tiet-mot-so-dieu-va-bien-phap-thi-hanh-luat-bao-ve-du-lieu-ca-nhan), [Luật Việt An](https://luatvietan.vn/diem-moi-cua-nghi-dinh-356-2025-so-voi-nghi-dinh-13-2023-ve-huong-dan-bao-ve-du-lieu-ca-nhan.html)) | Có hồ sơ chuyển dữ liệu xuyên biên giới và hồ sơ đánh giá tác động, **cập nhật định kỳ 6 tháng** (Điều 20 theo bài phân tích) **[CẦN XÁC MINH]**. "Tình trạng sức khỏe" được hiểu rộng hơn hồ sơ bệnh án. Miễn trừ cho doanh nghiệp nhỏ **[CẦN XÁC MINH]** | Cần 2 hồ sơ: (1) đánh giá tác động xử lý (cho mọi phương án); (2) chuyển dữ liệu ra nước ngoài (cho Claude và nhà cung cấp STT quốc tế). Ký **hợp đồng bên xử lý dữ liệu** với FPT/Viettel. **Web Speech API gửi âm thanh tới Google không có hợp đồng**, nên không dùng với dữ liệu thật |
| **Luật Trí tuệ nhân tạo số 134/2025/QH15**, thông qua 10/12/2025, **hiệu lực 01/3/2026**, 8 chương 35 điều ([Đại biểu Nhân dân](https://daibieunhandan.vn/quoc-hoi-thong-qua-luat-tri-tue-nhan-tao-10399959.html), [VnEconomy](https://vneconomy.vn/luat-tri-tue-nhan-tao-se-co-hieu-luc-tu-ngay-132026.htm)); Nghị định hướng dẫn **142/2026/NĐ-CP** (30/4/2026) **[CẦN XÁC MINH]** | Quản lý theo mức rủi ro, chặt hơn với y tế; bắt buộc gắn nhãn nội dung do AI tạo hoặc sửa. Danh mục hệ thống rủi ro cao trong y tế **[CẦN XÁC MINH]** | AI-01: bệnh án ghi "có hỗ trợ AI" và tên người duyệt (đã có trong thiết kế). AI-06 (đọc phim) nhiều khả năng thuộc **rủi ro cao** |
| **NĐ 98/2021/NĐ-CP** về trang thiết bị y tế, sửa đổi bởi **NĐ 07/2023/NĐ-CP** ([VCCI](https://vanban.vcci.com.vn/nghi-dinh-982021nd-cp-ve-quan-ly-trang-thiet-bi-y-te), [NĐ 07/2023](https://luatvietan.vn/nghi-dinh-07-2023-nd-cp-quan-ly-trang-thiet-bi-y-te.html)) | Điều 2 định nghĩa trang thiết bị y tế **bao gồm phần mềm** dùng cho chẩn đoán, theo dõi, điều trị ([tài liệu Sở Y tế Trà Vinh](https://syt.travinh.gov.vn:443/SiteFolders/syt/4923/2022/Tai%20lieu%20on%20chuyen%20nganh%20%20trang%20thiet%20bi%20y%20te%20nam%202022.pdf)). Một nguồn tổng hợp lại nói phần mềm được loại trừ khỏi một số quy định, hai nguồn mâu thuẫn **[CẦN XÁC MINH]**. Có luật hoặc nghị định mới thay NĐ 98 trong 2025–2026 không: **[CẦN XÁC MINH]** | STT và điền mẫu bệnh án **không** nhằm chẩn đoán → không phải trang thiết bị y tế. **AI-06 / AI-19** chỉ dùng sản phẩm **đã có số lưu hành** |

`DE_XUAT_AI.md` mục 3 đang ghi "NĐ 13/2023; Luật BVDLCN 2025 [CẦN XÁC MINH số hiệu]". Nên cập nhật thành **Luật 91/2025/QH15 + NĐ 356/2025/NĐ-CP (thay NĐ 13/2023)** và bổ sung **Luật Trí tuệ nhân tạo 134/2025/QH15**. Cần luật sư xác nhận trước khi vận hành thật.

---

## 4. Khuyến nghị cuối cùng

1. **Có cần dịch vụ STT riêng?** **Có.** Claude không nhận âm thanh. Nhưng **chưa cần thuê ngay**:
   - **demo và thí điểm** (1–2 bác sĩ, vài ngày, dữ liệu giả hoặc có đồng ý bằng văn bản): dùng **Web Speech API của Chrome/Edge**, 0 đ, đủ để bác sĩ cảm nhận lợi ích;
   - **không dùng** trên iPad/Safari, và **không dùng khi vận hành thật**.
2. **Thuê khi vận hành thật:**
   - **chính: FPT.AI Speech-to-Text** (trong nước, ≈ **2,5–3,1 tr đ/tháng** cho 3.900 phút; thực tế có thể ít hơn);
   - **dự phòng: Google Cloud STT Chirp 3 vi-VN** (≈ 0,3–1,6 tr đ/tháng), chỉ bật khi có hồ sơ chuyển dữ liệu ra nước ngoài.

   Trước khi ký hợp đồng, **thử so sánh 1 tuần** (FPT, Viettel, Google, OpenAI, Soniox) trên 30 đoạn đọc bệnh án thật, chấm theo lỗi thuật ngữ nha khoa.
3. **Dự án GitHub:**
   - **học và dùng lại có chọn lọc** `odoopilot` (LGPL-3, Odoo 17) cho `dmag_ai_core`;
   - **tham khảo kiến trúc** `apexive/odoo-llm` (LGPL-3);
   - **thử** `ViStreamASR` (MIT, CPU) như phương án tự chạy không cần GPU;
   - giữ `PhoWhisper` làm dự phòng dài hạn;
   - CCCD và Zalo OA: **tự viết** (đơn giản), tham khảo SDK PHP chính thức của Zalo;
   - **không dùng** DENTEX, Tufts, wav2vec2-vi (giấy phép phi thương mại) cho sản phẩm.
4. **Việc cần anh/chị quyết:**
   - (a) đồng ý dùng trình duyệt cho demo và thí điểm;
   - (b) cho phép liên hệ FPT.AI và Viettel AI lấy báo giá và hợp đồng bên xử lý dữ liệu;
   - (c) cho phép mở tài khoản Google Cloud làm dự phòng;
   - (d) giao luật sư xác minh các mục **[CẦN XÁC MINH]** ở phần 3.
