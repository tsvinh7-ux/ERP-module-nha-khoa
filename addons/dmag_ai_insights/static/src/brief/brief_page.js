/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { money } from "../common/ai_utils";

/** AI-14 – Bản tin điều hành hằng tuần. */
export class AiBriefPage extends Component {
    static template = "dmag_ai_insights.AiBriefPage";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = useState({ data: null, busy: false });
        this.money = money;
        onWillStart(() => this.load());
    }

    async load(id = false) {
        this.state.data = await this.orm.call("dmag.ai.brief", "get_brief_screen", [id]);
    }

    async generate() {
        this.state.busy = true;
        try {
            const id = await this.orm.call("dmag.ai.brief", "generate_from_screen", []);
            await this.load(id);
            this.notification.add("Đã soạn bản tin và gửi thông báo cho Giám đốc.", { type: "success" });
        } finally {
            this.state.busy = false;
        }
    }

    openForm() {
        const cur = this.state.data.current;
        this.action.doAction({ type: "ir.actions.act_window", res_model: "dmag.ai.brief", res_id: cur.id,
            views: [[false, "form"]], target: "current" });
    }

    fmtDate(iso) {
        if (!iso) {
            return "";
        }
        const [y, m, d] = iso.slice(0, 10).split("-");
        return `${d}/${m}/${y}`;
    }

    nextRun() {
        const v = this.state.data.next_run;
        if (!v) {
            return "";
        }
        const dt = new Date(v.replace(" ", "T") + "Z");
        return dt.toLocaleString("vi-VN", { weekday: "long", day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
    }

    changeTone(m) {
        if (!m.change) {
            return "is-flat";
        }
        const up = m.change.startsWith("+");
        return up ? "is-up" : "is-down";
    }
}

registry.category("actions").add("dmag_ai_brief", AiBriefPage);
