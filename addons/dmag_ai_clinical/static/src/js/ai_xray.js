/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { useService } from "@web/core/utils/hooks";
import { Odontogram } from "@dmag_clinic_workspace/odontogram/odontogram";
import { AiConsent, AiMeta, aiCall } from "./ai_utils";

/**
 * AI-06 – Hỗ trợ đọc phim (MINH HỌA): chọn / tải ảnh phim → AI (ảnh) gợi ý vùng nghi ngờ theo răng + độ tin cậy,
 * vẽ khung trên ảnh và tô răng trên sơ đồ. Không phải thiết bị chẩn đoán được cấp phép – bác sĩ quyết định.
 */
export class AiXrayDialog extends Component {
    static template = "dmag_ai_clinical.AiXrayDialog";
    static components = { Dialog, AiMeta, AiConsent, Odontogram };
    static props = {
        visitId: Number,
        chart: Array,
        dentition: { type: String, optional: true },
        locked: { type: Boolean, optional: true },
        onHighlight: Function,
        onChartChanged: Function,
        onSelectTooth: Function,
        close: Function,
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({
            images: [],
            samples: [],
            selected: null,
            result: null,
            consent: null,
            analyzing: false,
            hover: null,
            added: {},
        });
        onWillStart(() => this.loadImages());
    }

    async loadImages() {
        const res = await aiCall(this.orm, this.notification, "ai06_images", [this.props.visitId]);
        if (res) {
            this.state.images = res.images;
            this.state.samples = res.samples;
            if (!this.state.selected && res.images.length) {
                this.state.selected = res.images[0];
            }
        }
    }

    select(img) {
        this.state.selected = img;
        this.state.result = null;
        this.state.consent = null;
    }

    async addSample(sample) {
        const img = await aiCall(this.orm, this.notification, "ai06_add_sample", [this.props.visitId, sample.key]);
        if (img) {
            this.state.images.unshift(img);
            this.select(img);
        }
    }

    async onUpload(ev) {
        const file = ev.target.files && ev.target.files[0];
        ev.target.value = "";
        if (!file) {
            return;
        }
        if (file.size > 15 * 1024 * 1024) {
            this.notification.add("Ảnh quá lớn (tối đa 15 MB).", { type: "warning" });
            return;
        }
        const datas = await new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve(String(reader.result).split(",")[1]);
            reader.onerror = reject;
            reader.readAsDataURL(file);
        });
        const img = await aiCall(this.orm, this.notification, "ai06_upload", [this.props.visitId, file.name, datas, file.type]);
        if (img) {
            this.state.images.unshift(img);
            this.select(img);
        }
    }

    async analyze() {
        if (!this.state.selected) {
            return;
        }
        this.state.analyzing = true;
        this.state.consent = null;
        const res = await aiCall(this.orm, this.notification, "ai06_analyze", [this.props.visitId, this.state.selected.id]);
        this.state.analyzing = false;
        if (!res) {
            return;
        }
        if (res.consent_required) {
            this.state.consent = res;
            return;
        }
        this.state.result = res;
    }

    get findings() {
        return this.state.result ? this.state.result.findings : [];
    }

    /** Răng có vùng nghi bệnh lý / mất răng (không tô các phục hồi cũ). */
    get teeth() {
        return [...new Set(this.findings.filter((f) => f.category !== "existing").map((f) => f.tooth))];
    }

    boxStyle(f) {
        const b = f.box;
        return `left:${b.x * 100}%;top:${b.y * 100}%;width:${b.w * 100}%;height:${b.h * 100}%;--c:${f.color || "#8E4EC6"}`;
    }

    confClass(f) {
        return f.confidence >= 0.8 ? "is-high" : f.confidence >= 0.6 ? "is-mid" : "is-low";
    }

    canAdd(f) {
        return !this.props.locked && !f.on_chart && f.condition_id && (f.scope !== "surface" || f.category !== "finding" || f.surfaces.length);
    }

    async addToChart(f) {
        const ok = await aiCall(this.orm, this.notification, "ai06_add_to_chart", [this.props.visitId, f.tooth, f.condition_id], {
            surfaces: f.surfaces,
        });
        if (ok) {
            f.on_chart = true;
            this.notification.add(`Đã ghi R${f.tooth} – ${f.condition} lên sơ đồ răng (bác sĩ xác nhận).`, { type: "success" });
            await this.props.onChartChanged();
        }
    }

    showOnChart() {
        this.props.onHighlight(this.teeth);
        this.props.close();
    }

    selectTooth(f) {
        this.props.onHighlight(this.teeth);
        this.props.onSelectTooth(f.tooth);
        this.props.close();
    }
}
