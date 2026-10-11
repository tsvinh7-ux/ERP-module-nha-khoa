/** @odoo-module **/

import { Component, onMounted, onWillStart, onWillUnmount, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { AiBadge, formatVnd } from "../components/ai_badge";

const SEVERITY = { low: "Thấp", medium: "Trung bình", high: "Cao", critical: "Khẩn" };

/** Hộp thư lễ tân: hội thoại trợ lý chuyển sang người, câu trả lời chờ duyệt, lịch giữ chỗ. */
export class AiInbox extends Component {
    static template = "dmag_ai_customer.AiInbox";
    static components = { AiBadge };
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.logRef = useRef("log");
        this.formatVnd = formatVnd;
        this.SEVERITY = SEVERITY;
        this.state = useState({
            filter: "attention",
            inbox: { conversations: [], counts: {}, mode: "simulate", reply_mode: "approve" },
            thread: null,
            reply: "",
            editing: null,
            editText: "",
        });
        onWillStart(async () => {
            await this.load();
            const first = this.state.inbox.conversations[0];
            if (first) {
                await this.open(first.id);
            }
        });
        onMounted(() => {
            this.timer = setInterval(() => this.refresh(), 20000);
        });
        onWillUnmount(() => clearInterval(this.timer));
    }

    async load() {
        this.state.inbox = await this.orm.call("dmag.ai.conversation", "get_inbox", [this.state.filter]);
    }

    async refresh() {
        await this.load();
        if (this.state.thread) {
            await this.open(this.state.thread.id, false);
        }
    }

    async setFilter(key) {
        this.state.filter = key;
        await this.load();
    }

    async open(id, scroll = true) {
        this.state.thread = await this.orm.call("dmag.ai.conversation", "get_thread", [[id]]);
        if (scroll) {
            setTimeout(() => {
                const el = this.logRef.el;
                if (el) {
                    el.scrollTop = el.scrollHeight;
                }
            }, 0);
        }
    }

    async act(method) {
        await this.orm.call("dmag.ai.conversation", method, [[this.state.thread.id]]);
        await this.refresh();
    }

    async sendReply() {
        const text = this.state.reply.trim();
        if (!text) {
            return;
        }
        await this.orm.call("dmag.ai.conversation", "staff_reply", [[this.state.thread.id], text]);
        this.state.reply = "";
        await this.refresh();
    }

    useSuggestion(text) {
        this.state.reply = text;
    }

    async approve(msg) {
        await this.orm.call("dmag.ai.conversation.message", "action_approve_send", [[msg.id]]);
        this.notification.add("Đã duyệt và gửi câu trả lời của trợ lý.", { type: "success" });
        await this.refresh();
    }

    startEdit(msg) {
        this.state.editing = msg.id;
        this.state.editText = msg.body;
    }

    async saveEdit(msg) {
        await this.orm.call("dmag.ai.conversation.message", "approve_and_edit", [[msg.id], this.state.editText]);
        this.state.editing = null;
        await this.refresh();
    }

    async discard(msg) {
        await this.orm.call("dmag.ai.conversation.message", "action_discard", [[msg.id]]);
        await this.refresh();
    }

    get pendingMessages() {
        return this.state.thread ? this.state.thread.messages.filter((m) => m.state === "pending") : [];
    }

    openVisit(id) {
        return this.action.doAction({ type: "ir.actions.act_window", res_model: "dmag.dental.visit", res_id: id, views: [[false, "form"]], target: "new" });
    }

    openForm() {
        return this.action.doAction({ type: "ir.actions.act_window", res_model: "dmag.ai.conversation", res_id: this.state.thread.id, views: [[false, "form"]], target: "current" });
    }

    openSimulator() {
        return this.action.doAction("dmag_ai_customer.action_dmag_ai_zalo_simulator");
    }

    channelIcon(c) {
        return { zalo: "fa-comment", simulator: "fa-mobile", portal: "fa-globe", web: "fa-globe" }[c] || "fa-comment";
    }

    timeAgo(str) {
        if (!str) {
            return "";
        }
        const d = new Date(str.replace(" ", "T") + "Z");
        const min = Math.round((Date.now() - d.getTime()) / 60000);
        if (min < 1) {
            return "vừa xong";
        }
        if (min < 60) {
            return `${min} phút`;
        }
        if (min < 1440) {
            return `${Math.round(min / 60)} giờ`;
        }
        return d.toLocaleDateString("vi-VN");
    }
}

registry.category("actions").add("dmag_ai_inbox", AiInbox);
