/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { money, num, SEVERITY } from "../common/ai_utils";

const STATE_TONE = { new: "is-danger", review: "is-info", closed: "is-ok", dismissed: "" };

/** AI-15 – Cảnh báo bất thường (thống kê tại chỗ) + luồng giải trình / đóng. */
export class AiAnomalyPage extends Component {
    static template = "dmag_ai_insights.AiAnomalyPage";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = useState({ data: null, filter: "open", kind: "", busy: false, notes: {}, open: {}, aiBusy: {} });
        this.money = money;
        this.num = num;
        onWillStart(() => this.load());
    }

    async load() {
        this.state.data = await this.orm.call("dmag.ai.anomaly", "get_anomaly_board", []);
        for (const row of this.state.data.rows) {
            this.state.notes[row.id] = { manager_note: row.manager_note, director_note: row.director_note };
        }
    }

    sev(key) {
        return SEVERITY[key] || SEVERITY.low;
    }

    stateTone(s) {
        return STATE_TONE[s] || "";
    }

    get rows() {
        const rows = this.state.data.rows;
        return rows.filter((r) => (this.state.filter === "open" ? ["new", "review"].includes(r.state) : true)
            && (!this.state.kind || r.kind === this.state.kind));
    }

    get kindsPresent() {
        const seen = new Map();
        for (const r of this.state.data.rows) {
            if (this.state.filter !== "open" || ["new", "review"].includes(r.state)) {
                seen.set(r.kind, (seen.get(r.kind) || 0) + 1);
            }
        }
        return this.state.data.kinds.filter(([k]) => seen.has(k)).map(([k, label]) => ({ key: k, label, count: seen.get(k) }));
    }

    async scan() {
        this.state.busy = true;
        try {
            const n = await this.orm.call("dmag.ai.anomaly", "detect_now", []);
            await this.load();
            this.notification.add(`Đã quét xong: ${n} cảnh báo mới / cập nhật.`, { type: "info" });
        } finally {
            this.state.busy = false;
        }
    }

    async docs(row) {
        const action = await this.orm.call("dmag.ai.anomaly", "action_view_documents", [[row.id]]);
        this.action.doAction(action);
    }

    async narrate(row) {
        this.state.aiBusy[row.id] = true;
        try {
            await this.orm.call("dmag.ai.anomaly", "action_ai_narrative", [[row.id]]);
            await this.load();
            this.state.open[row.id] = true;
        } finally {
            this.state.aiBusy[row.id] = false;
        }
    }

    async step(row, method, field) {
        if (field) {
            await this.orm.call("dmag.ai.anomaly", "set_note", [row.id, field, this.state.notes[row.id][field] || ""]);
        }
        await this.orm.call("dmag.ai.anomaly", method, [[row.id]]);
        await this.load();
    }

    toggle(row) {
        this.state.open[row.id] = !this.state.open[row.id];
    }

    openForm(row) {
        this.action.doAction({ type: "ir.actions.act_window", res_model: "dmag.ai.anomaly", res_id: row.id,
            views: [[false, "form"]], target: "current" });
    }

    fmtDate(iso) {
        if (!iso) {
            return "";
        }
        const [y, m, d] = iso.slice(0, 10).split("-");
        return `${d}/${m}/${y}`;
    }

    lastRun() {
        const v = this.state.data.last_run && this.state.data.last_run.at;
        if (!v) {
            return "chưa chạy";
        }
        return new Date(v.replace(" ", "T") + "Z").toLocaleString("vi-VN", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
    }
}

registry.category("actions").add("dmag_ai_anomalies", AiAnomalyPage);
