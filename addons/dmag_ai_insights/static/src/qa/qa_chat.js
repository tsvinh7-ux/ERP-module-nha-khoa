/** @odoo-module **/

import { Component, onMounted, onWillStart, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { money, renderMd } from "../common/ai_utils";

const TOOL_LABELS = {
    get_goal_dashboard: "Bảng điều hành",
    metric: "Chỉ số",
    compare_periods: "So sánh kỳ",
    list_top: "Xếp hạng",
    drill_records: "Chứng từ",
};

/** AI-13 – khung hỏi đáp số liệu (dùng trong ngăn kéo trên Bảng điều hành và trang riêng). */
export class AiQaChat extends Component {
    static template = "dmag_ai_insights.AiQaChat";
    static props = { compact: { type: Boolean, optional: true }, onClose: { type: Function, optional: true },
        initialQuestion: { type: String, optional: true } };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.scroller = useRef("scroller");
        this.input = useRef("input");
        this.state = useState({ messages: [], question: "", busy: false, ctx: null, openTrace: {} });
        this.renderMd = renderMd;
        this.money = money;
        onWillStart(async () => {
            this.state.ctx = await this.orm.call("dmag.ai.qa", "get_qa_context", []);
        });
        onMounted(() => {
            if (this.props.initialQuestion) {
                this.ask(this.props.initialQuestion);
            } else if (this.input.el) {
                this.input.el.focus();
            }
        });
    }

    toolLabel(name) {
        return TOOL_LABELS[name] || name;
    }

    history() {
        return this.state.messages
            .filter((m) => !m.error)
            .map((m) => ({ role: m.role, content: m.role === "user" ? m.text : m.answer.text }));
    }

    async ask(q) {
        const question = (q || this.state.question || "").trim();
        if (!question || this.state.busy) {
            return;
        }
        const history = this.history();
        this.state.messages.push({ role: "user", text: question, id: Date.now() });
        this.state.question = "";
        this.state.busy = true;
        this.scrollDown();
        try {
            const answer = await this.orm.call("dmag.ai.qa", "ask", [question, history]);
            this.state.messages.push({ role: "assistant", answer, id: Date.now() + 1 });
        } catch (e) {
            const msg = (e.data && e.data.message) || e.message || "Lỗi không xác định";
            this.state.messages.push({ role: "assistant", error: true, answer: { text: msg }, id: Date.now() + 1 });
        } finally {
            this.state.busy = false;
            this.scrollDown();
        }
    }

    onKey(ev) {
        if (ev.key === "Enter" && !ev.shiftKey) {
            ev.preventDefault();
            this.ask();
        }
    }

    scrollDown() {
        setTimeout(() => {
            if (this.scroller.el) {
                this.scroller.el.scrollTop = this.scroller.el.scrollHeight;
            }
        }, 30);
    }

    openLink(link) {
        this.action.doAction(link.action);
    }

    toggleTrace(id) {
        this.state.openTrace[id] = !this.state.openTrace[id];
    }

    clear() {
        this.state.messages = [];
    }

    inputText(t) {
        return typeof t === "string" ? t : JSON.stringify(t);
    }

    traceInput(input) {
        if (!input) {
            return "";
        }
        return Object.entries(input)
            .filter(([, v]) => v !== null && v !== undefined && v !== "")
            .map(([k, v]) => `${k}=${v}`)
            .join(", ");
    }
}

/** Trang riêng "Hỏi đáp số liệu". */
export class AiQaPage extends Component {
    static template = "dmag_ai_insights.AiQaPage";
    static components = { AiQaChat };
    static props = ["*"];
}

registry.category("actions").add("dmag_ai_qa", AiQaPage);
