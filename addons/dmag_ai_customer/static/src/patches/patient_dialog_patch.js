/** @odoo-module **/

import { onWillUnmount, useRef, useState } from "@odoo/owl";
import { loadJS } from "@web/core/assets";
import { patch } from "@web/core/utils/patch";
import { NewPatientDialog } from "@dmag_clinic_workspace/dialogs/patient_dialog";
import { parseCccdQr, SAMPLE_CCCD_QR } from "./cccd_parser";

const JSQR_URL = "/dmag_ai_customer/static/lib/jsqr/jsQR.js";

/** AI-10 – "Quét CCCD": camera (BarcodeDetector / jsQR) hoặc ảnh / dán chuỗi QR → điền hồ sơ. Tại chỗ, không AI. */
patch(NewPatientDialog.prototype, {
    setup() {
        super.setup(...arguments);
        this.cccd = useState({ open: false, raw: "", error: "", scanning: false, info: null, existing: null, engine: "" });
        this.state.street = "";
        this.cccdVideo = useRef("cccdVideo");
        this.cccdCanvas = useRef("cccdCanvas");
        onWillUnmount(() => this.stopCamera());
    },

    toggleCccd() {
        this.cccd.open = !this.cccd.open;
        if (!this.cccd.open) {
            this.stopCamera();
        }
    },

    useSampleCccd() {
        this.cccd.raw = SAMPLE_CCCD_QR;
        this.applyCccd(SAMPLE_CCCD_QR, "Chuỗi mẫu");
    },

    async applyCccd(raw, engine = "Dán chuỗi") {
        this.cccd.error = "";
        let data;
        try {
            data = parseCccdQr(raw || this.cccd.raw);
        } catch (e) {
            this.cccd.error = e.message;
            return;
        }
        this.stopCamera();
        Object.assign(this.state, {
            name: data.name,
            citizen_id: data.citizen_id,
            birthdate: data.birthdate || this.state.birthdate,
            gender: data.gender || this.state.gender,
            street: data.address,
        });
        this.cccd.info = data;
        this.cccd.engine = engine;
        try {
            const server = await this.orm.call("dmag.ai.cccd", "parse_qr", [raw || this.cccd.raw]);
            this.cccd.existing = server.existing;
        } catch {
            this.cccd.existing = null;
        }
        this.notification.add(`Đã điền thông tin từ CCCD (${engine}). Kiểm tra lại và nhập số điện thoại.`, { type: "success" });
    },

    async ensureJsQR() {
        if (!window.jsQR) {
            await loadJS(JSQR_URL);
        }
        return window.jsQR;
    },

    async startCamera() {
        this.cccd.error = "";
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            this.cccd.error = "Trình duyệt không cho dùng camera (cần HTTPS). Hãy chọn ảnh hoặc dán chuỗi QR.";
            return;
        }
        try {
            this.stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } });
        } catch (e) {
            this.cccd.error = "Không mở được camera: " + e.message;
            return;
        }
        this.cccd.scanning = true;
        await new Promise((r) => setTimeout(r, 0));
        const video = this.cccdVideo.el;
        video.srcObject = this.stream;
        await video.play();
        let detector = null;
        if ("BarcodeDetector" in window) {
            try {
                const formats = await window.BarcodeDetector.getSupportedFormats();
                if (formats.includes("qr_code")) {
                    detector = new window.BarcodeDetector({ formats: ["qr_code"] });
                }
            } catch {
                detector = null;
            }
        }
        const jsQR = detector ? null : await this.ensureJsQR();
        const engine = detector ? "Camera · BarcodeDetector" : "Camera · jsQR";
        const tick = async () => {
            if (!this.cccd.scanning) {
                return;
            }
            let text = null;
            if (detector) {
                const codes = await detector.detect(video).catch(() => []);
                text = codes.length ? codes[0].rawValue : null;
            } else if (video.videoWidth) {
                const canvas = this.cccdCanvas.el;
                canvas.width = video.videoWidth;
                canvas.height = video.videoHeight;
                const ctx = canvas.getContext("2d", { willReadFrequently: true });
                ctx.drawImage(video, 0, 0);
                const img = ctx.getImageData(0, 0, canvas.width, canvas.height);
                const code = jsQR(img.data, img.width, img.height, { inversionAttempts: "dontInvert" });
                text = code ? code.data : null;
            }
            if (text && text.includes("|")) {
                this.cccd.raw = text;
                await this.applyCccd(text, engine);
                return;
            }
            this.raf = requestAnimationFrame(tick);
        };
        this.raf = requestAnimationFrame(tick);
    },

    stopCamera() {
        if (this.cccd) {
            this.cccd.scanning = false;
        }
        if (this.raf) {
            cancelAnimationFrame(this.raf);
        }
        if (this.stream) {
            this.stream.getTracks().forEach((t) => t.stop());
            this.stream = null;
        }
    },

    async scanImage(ev) {
        const file = ev.target.files && ev.target.files[0];
        if (!file) {
            return;
        }
        this.cccd.error = "";
        const url = URL.createObjectURL(file);
        const img = new Image();
        img.src = url;
        await img.decode();
        let text = null;
        let engine = "Ảnh · jsQR";
        if ("BarcodeDetector" in window) {
            try {
                const detector = new window.BarcodeDetector({ formats: ["qr_code"] });
                const codes = await detector.detect(img);
                if (codes.length) {
                    text = codes[0].rawValue;
                    engine = "Ảnh · BarcodeDetector";
                }
            } catch {
                text = null;
            }
        }
        if (!text) {
            const jsQR = await this.ensureJsQR();
            const canvas = this.cccdCanvas.el;
            const scale = Math.min(1, 1600 / Math.max(img.width, img.height));
            canvas.width = Math.round(img.width * scale);
            canvas.height = Math.round(img.height * scale);
            const ctx = canvas.getContext("2d", { willReadFrequently: true });
            ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
            const data = ctx.getImageData(0, 0, canvas.width, canvas.height);
            const code = jsQR(data.data, data.width, data.height);
            text = code ? code.data : null;
        }
        URL.revokeObjectURL(url);
        ev.target.value = "";
        if (!text) {
            this.cccd.error = "Không tìm thấy mã QR trong ảnh. Chụp rõ, đủ sáng, chỉ khung mã QR góc trên bên phải CCCD.";
            return;
        }
        this.cccd.raw = text;
        await this.applyCccd(text, engine);
    },

    useExistingCccd() {
        this.props.onCreated(this.cccd.existing);
        this.props.close();
    },

    /** Ghi đè để gửi thêm địa chỉ (từ CCCD) – còn lại giữ nguyên nghiệp vụ tạo nhanh của dmag_clinic_workspace. */
    async save(force = false) {
        this.state.saving = true;
        try {
            const res = await this.orm.call("dmag.workspace", "quick_create_patient", [{
                name: this.state.name,
                phone: this.state.phone,
                birthdate: this.state.birthdate || false,
                gender: this.state.gender || false,
                citizen_id: this.state.citizen_id || false,
                source_id: Number(this.state.source_id) || false,
                allergy: this.state.allergy || false,
                alert_ids: this.state.alert_ids,
                consent: this.state.consent,
                street: this.state.street || false,
                force,
            }]);
            if (res.duplicate) {
                this.state.duplicate = res.duplicate;
                return;
            }
            this.notification.add(`Đã tạo hồ sơ ${res.name} (${res.code})`, { type: "success" });
            this.props.onCreated(res);
            this.props.close();
        } finally {
            this.state.saving = false;
        }
    },
});
