/** @odoo-module **/

import { Component, onWillUnmount, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { useService } from "@web/core/utils/hooks";
import { AiConsent, AiMeta, aiCall, aiErrorMessage } from "./ai_utils";

export const STT_PROVIDERS = [
    ["simulate", "Giả lập (bản đọc mẫu)"],
    ["browser", "Trình duyệt (Web Speech)"],
    ["fpt", "FPT.AI"],
    ["viettel", "Viettel AI"],
];

/** AI-01 – hộp thoại duyệt từng mục: hiện tại ↔ AI gợi ý, chấp nhận từng mục / tất cả. */
export class AiDictationReview extends Component {
    static template = "dmag_ai_clinical.AiDictationReview";
    static components = { Dialog, AiMeta };
    static props = { result: Object, visitId: Number, onApplied: Function, close: Function };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({
            rows: this.props.result.rows.map((r) => ({ ...r })),
            icd: this.props.result.icd.map((d) => ({ ...d })),
            saving: false,
        });
    }

    get textRows() {
        return this.state.rows.filter((r) => r.kind === "text");
    }

    get numRows() {
        return this.state.rows.filter((r) => r.kind !== "text");
    }

    rowsFor(row) {
        return Math.min(6, Math.max(1, Math.ceil(String(row.suggested || "").length / 62)));
    }

    get selectedCount() {
        return this.state.rows.filter((r) => r.accept).length + this.state.icd.filter((d) => d.accept && !d.already).length;
    }

    get allSelected() {
        return this.state.rows.every((r) => r.accept);
    }

    toggleAll() {
        const value = !this.allSelected;
        this.state.rows.forEach((r) => (r.accept = value));
        this.state.icd.forEach((d) => (d.accept = value && !d.already));
    }

    async apply() {
        const values = {};
        for (const row of this.state.rows) {
            if (row.accept) {
                values[row.key] = row.kind === "text" ? row.suggested : Number(row.suggested);
            }
        }
        const diagnosisIds = this.state.icd.filter((d) => d.accept && !d.already).map((d) => d.id);
        if (!Object.keys(values).length && !diagnosisIds.length) {
            this.notification.add("Chưa chọn mục nào để áp dụng.", { type: "warning" });
            return;
        }
        this.state.saving = true;
        const res = await aiCall(this.orm, this.notification, "ai01_apply", [this.props.visitId, values, diagnosisIds], {
            log_id: this.props.result.log_id || false,
        });
        this.state.saving = false;
        if (res) {
            this.notification.add(`Đã ghi ${res.applied.length} mục vào bệnh án (bác sĩ duyệt). Bệnh án vẫn chưa ký.`, {
                type: "success",
            });
            await this.props.onApplied();
            this.props.close();
        }
    }
}

/**
 * AI-01 – Ghi bệnh án bằng giọng nói: micro → chữ (trình duyệt / FPT.AI / Viettel AI / giả lập)
 * → AI điền mẫu 16/BV1 → bác sĩ duyệt từng mục.
 */
export class AiDictation extends Component {
    static template = "dmag_ai_clinical.AiDictation";
    static components = { AiConsent };
    static props = {
        visitId: Number,
        locked: Boolean,
        status: Object,
        onApplied: Function,
        onCheck: { type: Function, optional: true },
        showCheck: { type: Boolean, optional: true },
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.dialog = useService("dialog");
        this.PROVIDERS = STT_PROVIDERS;
        this.state = useState({
            provider: this.props.status.stt_provider || "simulate",
            recording: false,
            transcript: "",
            interim: "",
            seconds: 0,
            busy: false,
            uploading: false,
            consent: null,
            expanded: false,
        });
        this.recognition = null;
        this.recorder = null;
        this.timer = null;
        this.typing = null;
        onWillUnmount(() => this.cleanup());
    }

    get providerLabel() {
        return (STT_PROVIDERS.find((p) => p[0] === this.state.provider) || [])[1] || "";
    }

    get wordCount() {
        return this.state.transcript.split(/\s+/).filter(Boolean).length;
    }

    get timeText() {
        const s = this.state.seconds;
        return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
    }

    cleanup() {
        clearInterval(this.timer);
        clearInterval(this.typing);
        if (this.recognition) {
            this.recognition.onend = null;
            try {
                this.recognition.stop();
            } catch {
                // đã dừng
            }
        }
        if (this.recorder && this.recorder.state !== "inactive") {
            this.recorder.onstop = null;
            this.recorder.stop();
        }
        if (this.stream) {
            this.stream.getTracks().forEach((t) => t.stop());
        }
    }

    _startTimer() {
        this.state.seconds = 0;
        clearInterval(this.timer);
        this.timer = setInterval(() => (this.state.seconds += 1), 1000);
    }

    _append(text) {
        const t = (text || "").trim();
        if (t) {
            this.state.transcript = this.state.transcript ? `${this.state.transcript.replace(/\s+$/, "")} ${t}` : t;
        }
    }

    async toggleRecord() {
        if (this.state.recording) {
            return this.stop();
        }
        this.state.expanded = true;
        const p = this.state.provider;
        if (p === "simulate") {
            return this.startSimulated();
        }
        if (p === "browser") {
            return this.startBrowser();
        }
        return this.startRecorder();
    }

    async startSimulated() {
        const res = await aiCall(this.orm, this.notification, "ai01_sample_transcript", [this.props.visitId]);
        if (!res) {
            return;
        }
        const words = res.text.split(/\s+/);
        this.state.recording = true;
        this._startTimer();
        let i = 0;
        const base = this.state.transcript ? `${this.state.transcript} ` : "";
        this.typing = setInterval(() => {
            i += 2;
            const done = words.slice(0, Math.max(0, i - 4)).join(" ");
            this.state.transcript = base + done;
            this.state.interim = words.slice(Math.max(0, i - 4), i).join(" ");
            if (i >= words.length + 4) {
                this.stop();
            }
        }, 70);
    }

    startBrowser() {
        const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (!SR) {
            this.notification.add("Trình duyệt không hỗ trợ nhận dạng giọng nói – dùng Chrome / Edge, hoặc chọn FPT.AI / Viettel AI.", {
                type: "warning",
            });
            return;
        }
        const rec = new SR();
        rec.lang = "vi-VN";
        rec.continuous = true;
        rec.interimResults = true;
        rec.onresult = (ev) => {
            let interim = "";
            for (let i = ev.resultIndex; i < ev.results.length; i++) {
                const text = ev.results[i][0].transcript;
                if (ev.results[i].isFinal) {
                    this._append(text);
                } else {
                    interim += text;
                }
            }
            this.state.interim = interim;
        };
        rec.onerror = (ev) => {
            if (ev.error !== "no-speech") {
                this.notification.add(`Nhận dạng giọng nói lỗi: ${ev.error === "not-allowed" ? "chưa cho phép dùng micro" : ev.error}`, {
                    type: "danger",
                });
                this.stop();
            }
        };
        rec.onend = () => {
            // Chrome tự dừng sau một quãng im lặng – nói tiếp thì bật lại
            if (this.state.recording) {
                try {
                    rec.start();
                } catch {
                    this.stop();
                }
            }
        };
        this.recognition = rec;
        rec.start();
        this.state.recording = true;
        this._startTimer();
    }

    async startRecorder() {
        if (!navigator.mediaDevices || !window.MediaRecorder) {
            this.notification.add("Trình duyệt không ghi âm được (cần HTTPS và quyền micro).", { type: "warning" });
            return;
        }
        try {
            this.stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        } catch (e) {
            this.notification.add(`Không mở được micro: ${aiErrorMessage(e)}`, { type: "danger" });
            return;
        }
        const chunks = [];
        const recorder = new MediaRecorder(this.stream);
        recorder.ondataavailable = (ev) => ev.data.size && chunks.push(ev.data);
        recorder.onstop = () => {
            this.stream.getTracks().forEach((t) => t.stop());
            this.upload(new Blob(chunks, { type: recorder.mimeType || "audio/webm" }));
        };
        this.recorder = recorder;
        recorder.start();
        this.state.recording = true;
        this._startTimer();
    }

    async upload(blob) {
        this.state.uploading = true;
        try {
            const form = new FormData();
            form.append("csrf_token", odoo.csrf_token);
            form.append("visit_id", this.props.visitId);
            form.append("provider", this.state.provider);
            form.append("audio", blob, "ghi_am.webm");
            const resp = await fetch("/dmag_ai_clinical/stt", { method: "POST", body: form });
            const data = await resp.json();
            if (data.ok) {
                this._append(data.text);
            } else {
                this.notification.add(data.error, { type: "danger", title: "Nhận dạng giọng nói" });
            }
        } catch (e) {
            this.notification.add(`Không gửi được âm thanh: ${aiErrorMessage(e)}`, { type: "danger" });
        } finally {
            this.state.uploading = false;
        }
    }

    stop() {
        this.state.recording = false;
        clearInterval(this.timer);
        clearInterval(this.typing);
        if (this.state.interim) {
            this._append(this.state.interim);
            this.state.interim = "";
        }
        if (this.recognition) {
            this.recognition.onend = null;
            this.recognition.stop();
            this.recognition = null;
        }
        if (this.recorder && this.recorder.state !== "inactive") {
            this.recorder.stop();
        }
    }

    clear() {
        this.stop();
        this.state.transcript = "";
        this.state.consent = null;
    }

    async structure() {
        if (this.state.recording) {
            this.stop();
        }
        this.state.busy = true;
        this.state.consent = null;
        const res = await aiCall(this.orm, this.notification, "ai01_structure", [this.props.visitId, this.state.transcript]);
        this.state.busy = false;
        if (!res) {
            return;
        }
        if (res.consent_required) {
            this.state.consent = res;
            return;
        }
        if (!res.rows.length && !res.icd.length) {
            this.notification.add("AI không tìm thấy nội dung mới so với bệnh án hiện tại.", { type: "info" });
            return;
        }
        this.dialog.add(AiDictationReview, { result: res, visitId: this.props.visitId, onApplied: this.props.onApplied });
    }
}
