/** @odoo-module **/

import { Component, onMounted, onWillStart, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { AiBadge, formatVnd, summarizeTool, TOOL_LABELS } from "../components/ai_badge";

const DEMO_SCRIPT = [
    "Chào phòng khám",
    "Cạo vôi răng giá bao nhiêu ạ?",
    "Cho em đặt lịch cạo vôi chiều nay",
    "Mấy giờ mở cửa vậy?",
    "Răng em sưng to và chảy máu không cầm",
];

/** AI-07 – Mô phỏng Zalo OA: chủ phòng khám đóng vai khách, xem AI gọi công cụ thật và lịch xuất hiện trên bảng điều phối. */
export class ZaloSimulator extends Component {
    static template = "dmag_ai_customer.ZaloSimulator";
    static components = { AiBadge };
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.inputRef = useRef("input");
        this.logRef = useRef("log");
        this.TOOL_LABELS = TOOL_LABELS;
        this.summarizeTool = summarizeTool;
        this.formatVnd = formatVnd;
        this.DEMO_SCRIPT = DEMO_SCRIPT;
        this.state = useState({
            thread: null,
            status: { mode: "simulate" },
            sending: false,
            text: "",
            persona: "new",
            query: "",
            results: [],
            board: [],
        });
        onWillStart(async () => {
            this.state.status = await this.orm.call("dmag.ai", "get_ai_status", []);
            await this.start();
            await this.loadBoard();
        });
        onMounted(() => this.scroll());
    }

    get chatMessages() {
        return this.state.thread ? this.state.thread.messages : [];
    }

    get botTurns() {
        return this.chatMessages.filter((m) => m.role === "bot").slice().reverse();
    }

    get lastQuick() {
        const bots = this.chatMessages.filter((m) => m.role !== "customer");
        const last = bots[bots.length - 1];
        const lastAll = this.chatMessages[this.chatMessages.length - 1];
        return last && lastAll && lastAll.id === last.id ? last.quick || [] : [];
    }

    get totalEstimate() {
        return this.state.thread ? this.state.thread.estimated_cost_vnd : 0;
    }

    get totalCost() {
        return this.state.thread ? this.state.thread.cost_vnd : 0;
    }

    get liveMode() {
        return this.state.status.mode === "live";
    }

    scroll() {
        const el = this.logRef.el;
        if (el) {
            el.scrollTop = el.scrollHeight;
        }
    }

    async start(partner) {
        this.state.thread = await this.orm.call("dmag.ai.conversation", "simulator_start", [], {
            partner_id: partner ? partner.id : false,
        });
        this.state.persona = partner ? partner.name : "new";
        this.state.results = [];
        this.state.query = "";
        setTimeout(() => this.scroll(), 0);
    }

    async searchPatient(ev) {
        this.state.query = ev.target.value;
        this.state.results = this.state.query.length >= 2
            ? await this.orm.call("dmag.workspace", "search_patients", [this.state.query, 5])
            : [];
    }

    async send(text) {
        text = (text || this.state.text || "").trim();
        if (!text || this.state.sending) {
            return;
        }
        this.state.sending = true;
        this.state.text = "";
        if (this.inputRef.el) {
            this.inputRef.el.value = "";
        }
        // hiện ngay tin của khách
        this.state.thread.messages.push({ id: "tmp", role: "customer", body: text, time: "", state: "received", trace: [], quick: [] });
        setTimeout(() => this.scroll(), 0);
        try {
            this.state.thread = await this.orm.call("dmag.ai.conversation", "simulator_send", [[this.state.thread.id], text]);
            const booked = this.state.thread.visits.length;
            if (booked) {
                await this.loadBoard();
            }
        } finally {
            this.state.sending = false;
            setTimeout(() => {
                this.scroll();
                this.inputRef.el && this.inputRef.el.focus();
            }, 0);
        }
    }

    onKey(ev) {
        if (ev.key === "Enter") {
            ev.preventDefault();
            this.send();
        }
    }

    async loadBoard() {
        const board = await this.orm.call("dmag.dental.visit", "get_frontdesk_board", []);
        this.state.board = board.visits.filter((v) => ["draft", "confirmed"].includes(v.state));
    }

    isNew(visit) {
        return this.state.thread && this.state.thread.visits.some((v) => v.id === visit.id);
    }

    timeOf(visit) {
        const d = new Date(visit.start.replace(" ", "T") + "Z");
        return d.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
    }

    openFrontDesk() {
        return this.action.doAction("dmag_clinic_workspace.action_dmag_frontdesk");
    }

    openInbox() {
        return this.action.doAction("dmag_ai_customer.action_dmag_ai_inbox");
    }

    openVisit(id) {
        return this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "dmag.dental.visit",
            res_id: id,
            views: [[false, "form"]],
            target: "new",
        });
    }

    async confirmVisit(visit) {
        await this.orm.call("dmag.dental.visit", "action_confirm", [[visit.id]]);
        this.notification.add(`Lễ tân đã xác nhận ${visit.name} – hệ thống gửi ZNS xác nhận (mẫu đã duyệt).`, { type: "success" });
        this.state.thread = await this.orm.call("dmag.ai.conversation", "get_thread", [[this.state.thread.id]]);
        await this.loadBoard();
    }

    toolMeta(step) {
        return TOOL_LABELS[step.tool] || { icon: "fa-wrench", label: step.tool };
    }

    stringify(value) {
        return JSON.stringify(value);
    }
}

registry.category("actions").add("dmag_ai_zalo_simulator", ZaloSimulator);
