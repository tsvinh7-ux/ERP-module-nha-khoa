/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { money, num, pct } from "../common/ai_utils";

const STATE_META = {
    live: { icon: "fa-bolt", tone: "live" },
    simulate: { icon: "fa-flask", tone: "sim" },
    local: { icon: "fa-server", tone: "local" },
    off: { icon: "fa-power-off", tone: "off" },
    not_installed: { icon: "fa-puzzle-piece", tone: "off" },
};
const SOURCE_ICON = { local: "fa-server", api_vn: "fa-flag", api_llm: "fa-cloud", hybrid: "fa-random" };

/** Trung tâm AI – 20 tính năng AI-00 … AI-19 theo vai trò, trạng thái, chi phí, nút "Thử ngay". */
export class AiHub extends Component {
    static template = "dmag_ai_insights.AiHub";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({ data: null, audience: "all", query: "", hoverBar: null });
        this.money = money;
        this.num = num;
        this.pct = pct;
        onWillStart(() => this.load());
    }

    async load() {
        this.state.data = await this.orm.call("dmag.ai.hub", "get_hub", []);
    }

    stateMeta(s) {
        return STATE_META[s] || STATE_META.off;
    }

    sourceIcon(s) {
        return SOURCE_ICON[s] || "fa-cloud";
    }

    get groups() {
        const d = this.state.data;
        const q = (this.state.query || "").toLowerCase().trim();
        return d.audiences
            .filter((a) => a.visible && (this.state.audience === "all" || this.state.audience === a.key))
            .map((a) => ({
                ...a,
                features: d.features.filter((f) => f.audience === a.key && f.visible
                    && (!q || `${f.code} ${f.name} ${f.what} ${f.example}`.toLowerCase().includes(q))),
            }))
            .filter((g) => g.features.length);
    }

    get counts() {
        const fs = this.state.data.features.filter((f) => f.visible);
        return {
            total: fs.length,
            active: fs.filter((f) => f.active && f.module_ready).length,
            local: fs.filter((f) => f.source === "local").length,
            llm: fs.filter((f) => ["api_llm", "hybrid"].includes(f.source)).length,
        };
    }

    get budgetPct() {
        const d = this.state.data;
        return d.budget ? Math.min(100, (100 * d.spent) / d.budget) : 0;
    }

    get projectedPct() {
        const d = this.state.data;
        return d.budget ? Math.min(100, (100 * d.projected) / d.budget) : 0;
    }

    /** Thanh ngang: chi phí ước tính nếu chạy thật theo tính năng (tháng này) – một chuỗi, nhãn ở đầu thanh. */
    get costBars() {
        const fs = this.state.data.features.filter((f) => f.estimated > 0 || f.cost > 0)
            .map((f) => ({ code: f.code, name: f.name, value: f.estimated, usage: f.usage,
                live: f.live_calls, cost: f.cost, estimated: f.estimated }))
            .sort((a, b) => b.value - a.value)
            .slice(0, 8);
        const max = Math.max(1, ...fs.map((f) => f.value));
        return fs.map((f) => ({ ...f, w: Math.max(1.5, (100 * f.value) / max) }));
    }

    async tryNow(f) {
        const action = await this.orm.call("dmag.ai.hub", "open_target", [f.code]);
        if (action) {
            this.action.doAction(action);
        }
    }

    openSettings() {
        this.action.doAction("dmag_ai_core.action_dmag_ai_settings");
    }

    openLogs() {
        this.action.doAction("dmag_ai_core.action_dmag_ai_log");
    }

    openFeatures() {
        this.action.doAction("dmag_ai_core.action_dmag_ai_feature");
    }
}

registry.category("actions").add("dmag_ai_hub", AiHub);
