/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

const NEW_LINE = (drug) => ({
    drug_id: drug.id,
    drug_name: drug.name,
    unit: drug.unit,
    dose_unit: drug.dose_unit || drug.unit,
    dose_per_time: drug.default_dose_per_time || 1,
    times_per_day: drug.default_times_per_day || 2,
    days: drug.default_days || 5,
    timing: drug.default_timing || "after_meal",
    route: drug.route,
    usage_note: "",
});

/**
 * Kê đơn thuốc trên màn hình bác sĩ (TT 26/2025): đơn mẫu 1 chạm, tên thuốc theo tên chung + hàm lượng,
 * tự soạn cách dùng, phát hành → khóa + liên thông Hệ thống đơn thuốc quốc gia.
 * Chỉ hiển thị khi đã cài module dmag_dental_prescription.
 */
export class RxPanel extends Component {
    static template = "dmag_clinic_workspace.RxPanel";
    static props = { visitId: Number, prescriptions: Array, locked: Boolean, onChanged: Function };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({ catalog: null, draft: null, search: "", saving: false, result: null });
        onWillStart(async () => {
            this.state.catalog = await this.orm.call("dmag.dental.visit", "get_rx_catalog", []);
            const draft = this.props.prescriptions.find((p) => p.state === "draft");
            if (draft) {
                this.editDraft(draft);
            }
        });
    }

    get timings() {
        return this.state.catalog ? this.state.catalog.timings : [];
    }

    get drugResults() {
        const q = this.state.search.trim().toLowerCase();
        if (!q || !this.state.catalog) {
            return [];
        }
        return this.state.catalog.drugs
            .filter((d) => `${d.name} ${d.inn_name || ""} ${d.brand_name || ""}`.toLowerCase().includes(q))
            .slice(0, 8);
    }

    newDraft() {
        this.state.draft = { id: false, advice: "", re_exam_days: 0, weight: 0, companion_name: "", lines: [] };
        this.state.result = null;
    }

    editDraft(p) {
        this.state.draft = {
            id: p.id,
            advice: p.advice || "",
            re_exam_date: p.re_exam_date || false,
            weight: p.weight || 0,
            companion_name: p.companion_name || "",
            is_under_72_months: p.is_under_72_months,
            lines: p.lines.map((l) => ({ ...l })),
        };
    }

    applyTemplate(t) {
        if (!this.state.draft) {
            this.newDraft();
        }
        const drugs = this.state.catalog.drugs;
        for (const tl of t.lines) {
            const drug = drugs.find((d) => d.id === tl.drug_id);
            if (drug) {
                this.state.draft.lines.push({ ...NEW_LINE(drug), ...tl, drug_name: drug.name });
            }
        }
        if (t.advice && !this.state.draft.advice) {
            this.state.draft.advice = t.advice;
        }
        if (t.re_exam_days) {
            this.state.draft.re_exam_days = t.re_exam_days;
        }
    }

    addDrug(drug) {
        if (!this.state.draft) {
            this.newDraft();
        }
        this.state.draft.lines.push(NEW_LINE(drug));
        this.state.search = "";
    }

    removeLine(line) {
        const lines = this.state.draft.lines;
        lines.splice(lines.indexOf(line), 1);
    }

    /** Thuốc kê theo đơn vị đóng gói (chai, tuýp…) khác đơn vị liều (ml, g…): số lượng nhập tay. */
    isPack(line) {
        return (line.dose_unit || "").trim().toLowerCase() !== (line.unit || "").trim().toLowerCase();
    }

    qtyOf(line) {
        if (this.isPack(line)) {
            return Math.max(1, Math.ceil(Number(line.quantity) || 1));
        }
        const q = Number(line.dose_per_time || 0) * Number(line.times_per_day || 0) * Number(line.days || 0);
        return Math.ceil(q);
    }

    /** TT 26/2025: số lượng thuốc < 10 viết thêm số 0 phía trước. */
    qtyLabel(line) {
        return String(this.qtyOf(line)).padStart(2, "0");
    }

    _payload() {
        const d = this.state.draft;
        return {
            id: d.id || undefined,
            advice: d.advice,
            re_exam_days: Number(d.re_exam_days) || 0,
            weight: Number(d.weight) || 0,
            companion_name: d.companion_name,
            lines: d.lines.map((l) => ({
                drug_id: l.drug_id,
                quantity: this.qtyOf(l),
                dose_per_time: Number(l.dose_per_time),
                times_per_day: Number(l.times_per_day),
                days: Number(l.days),
                timing: l.timing,
                route: l.route,
                usage_note: l.usage_note || "",
            })),
        };
    }

    async save() {
        this.state.saving = true;
        try {
            const res = await this.orm.call("dmag.dental.visit", "save_prescription_from_workspace", [[this.props.visitId], this._payload()]);
            this.editDraft(res);
            await this.props.onChanged();
            return res;
        } finally {
            this.state.saving = false;
        }
    }

    async issue() {
        const saved = await this.save();
        this.state.saving = true;
        try {
            const res = await this.orm.call("dmag.dental.visit", "issue_prescription", [[this.props.visitId], saved.id]);
            this.state.result = res;
            this.state.draft = null;
            const msg = res.send_status === "sent" ? "đã liên thông Hệ thống đơn thuốc quốc gia" : res.send_status === "queued" ? "đang chờ gửi liên thông" : "liên thông lỗi – sẽ tự gửi lại";
            this.notification.add(`Đã phát hành đơn ${res.code} – ${msg}`, { type: res.send_status === "error" ? "warning" : "success" });
            await this.props.onChanged();
        } finally {
            this.state.saving = false;
        }
    }

    stateClass(p) {
        return { draft: "is-plan-draft", issued: "is-plan-presented", sent: "is-plan-accepted", send_error: "is-plan-cancel", replaced: "is-plan-cancel", cancelled: "is-plan-cancel" }[p.state] || "";
    }
}
