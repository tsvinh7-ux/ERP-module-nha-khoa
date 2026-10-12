/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const SOURCE_ICONS = {
    script: "fa-book", pricelist: "fa-tags", schedule: "fa-clock-o", rotation: "fa-users", clinic: "fa-map-marker",
    care_plan: "fa-heart", document: "fa-file-text-o", inbox: "fa-inbox", manual: "fa-pencil",
};
const MODE_LABELS = {
    grounded: "Tự động – chỉ trả lời từ dữ liệu đã nạp",
    script: "Tự động theo kịch bản đã duyệt",
    approve: "Nhân viên duyệt mọi câu",
    auto: "Tự động hoàn toàn",
};
const SAMPLES = ["Chủ nhật có làm việc không?", "Răng sứ Zirconia bảo hành bao lâu?", "Có xuất hóa đơn VAT cho công ty không?",
    "Phòng khám có nhận bảo hiểm Bảo Việt không?"];

/** "Dữ liệu đã nạp": trợ lý Zalo chỉ trả lời từ kho tri thức này (số mục theo nguồn, lần nạp cuối, thử hỏi). */
export class KbOverview extends Component {
    static template = "dmag_ai_customer.KbOverview";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.SOURCE_ICONS = SOURCE_ICONS;
        this.MODE_LABELS = MODE_LABELS;
        this.SAMPLES = SAMPLES;
        this.state = useState({ data: null, question: "", result: null, asking: false, refreshing: false });
        onWillStart(() => this.load());
    }

    async load() {
        this.state.data = await this.orm.call("dmag.ai.knowledge", "get_kb_overview", []);
    }

    async refresh() {
        this.state.refreshing = true;
        try {
            const res = await this.orm.call("dmag.ai.knowledge", "action_refresh_all", []);
            this.notification.add(`Đã nạp lại ${res.master} mục dữ liệu gốc và ${res.scripts} kịch bản đã duyệt.`, { type: "success" });
            await this.load();
        } finally {
            this.state.refreshing = false;
        }
    }

    async ask(text) {
        const q = (text || this.state.question || "").trim();
        if (!q) {
            return;
        }
        this.state.question = q;
        this.state.asking = true;
        try {
            this.state.result = await this.orm.call("dmag.ai.knowledge", "try_question", [q]);
        } finally {
            this.state.asking = false;
        }
    }

    onKey(ev) {
        if (ev.key === "Enter") {
            this.ask();
        }
    }

    async approve(entry) {
        await this.orm.call("dmag.ai.knowledge", "action_approve", [[entry.id]]);
        this.notification.add(`Đã duyệt “${entry.name}” – trợ lý được dùng nội dung này.`, { type: "success" });
        await this.load();
    }

    openSource(code) {
        return this.action.doAction({
            type: "ir.actions.act_window", name: "Kho tri thức trợ lý", res_model: "dmag.ai.knowledge",
            views: [[false, "list"], [false, "form"]], domain: [["source_type", "=", code]], target: "current",
        });
    }

    openEntry(id) {
        return this.action.doAction({ type: "ir.actions.act_window", res_model: "dmag.ai.knowledge", res_id: id, views: [[false, "form"]], target: "current" });
    }

    openList() {
        return this.action.doAction("dmag_ai_customer.action_dmag_ai_knowledge");
    }

    newDocument() {
        return this.action.doAction({ type: "ir.actions.act_window", res_model: "dmag.ai.knowledge.document", views: [[false, "form"]], target: "current" });
    }

    openGaps() {
        return this.action.doAction("dmag_ai_customer.action_dmag_ai_inbox", { additionalContext: { dmag_inbox_filter: "gaps" } });
    }

    openSimulator() {
        return this.action.doAction("dmag_ai_customer.action_dmag_ai_zalo_simulator");
    }

    fmt(dt) {
        if (!dt) {
            return "chưa nạp";
        }
        const d = new Date(dt.replace(" ", "T") + "Z");
        return d.toLocaleString("vi-VN", { hour: "2-digit", minute: "2-digit", day: "2-digit", month: "2-digit" });
    }

    get openGapCount() {
        return (this.state.data.gaps || []).filter((g) => g.state === "open").length;
    }
}

registry.category("actions").add("dmag_ai_kb_overview", KbOverview);
