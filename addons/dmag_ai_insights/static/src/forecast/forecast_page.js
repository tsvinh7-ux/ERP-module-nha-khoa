/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { money, num, pct } from "../common/ai_utils";
import { AiForecastChart } from "./forecast_chart";

const MAT_STATUS = {
    critical: { label: "Sắp hết", tone: "bad", icon: "fa-exclamation-triangle" },
    low: { label: "Không đủ 30 ngày", tone: "warn", icon: "fa-clock-o" },
    ok: { label: "Đủ dùng", tone: "good", icon: "fa-check-circle" },
};

/** AI-16 – màn hình Dự báo doanh thu & vật tư. */
export class AiForecastPage extends Component {
    static template = "dmag_ai_insights.AiForecastPage";
    static components = { AiForecastChart };
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.state = useState({ data: null, showAll: false, hoverBar: null });
        this.money = money;
        this.num = num;
        this.pct = pct;
        onWillStart(() => this.load());
    }

    async load() {
        this.state.data = await this.orm.call("dmag.ai.forecast", "get_forecast", []);
    }

    matStatus(key) {
        return MAT_STATUS[key] || MAT_STATUS.ok;
    }

    get materials() {
        const rows = this.state.data.materials.rows || [];
        return this.state.showAll ? rows : rows.slice(0, 8);
    }

    /** Cột doanh thu 6 tháng gần nhất + tháng này (dự báo) – một chuỗi, nhãn ở đỉnh cột. */
    get history() {
        const d = this.state.data;
        const items = d.history.map((h) => ({ label: h.month, value: h.value, kind: "actual" }));
        items.push({ label: "Tháng này", value: d.revenue.total, low: d.revenue.low, high: d.revenue.high, kind: "forecast" });
        items.push({ label: "Tháng sau", value: d.next_month.total, low: d.next_month.low, high: d.next_month.high, kind: "forecast" });
        const W = 520;
        const H = 190;
        const pad = { l: 8, r: 8, t: 22, b: 26 };
        const max = Math.max(1, ...items.map((i) => Math.max(i.value || 0, i.high || 0))) * 1.05;
        const band = (W - pad.l - pad.r) / items.length;
        const bw = Math.min(24, band * 0.5);
        const y = (v) => H - pad.b - (v / max) * (H - pad.t - pad.b);
        const bars = items.map((it, i) => {
            const x = pad.l + i * band + (band - bw) / 2;
            const top = y(it.value || 0);
            return { ...it, i, x, w: bw, top, h: Math.max(1, H - pad.b - top), cx: x + bw / 2,
                hiY: it.high ? y(it.high) : null, loY: it.low !== undefined ? y(it.low) : null };
        });
        return { W, H, pad, bars, base: H - pad.b };
    }

    barPath(b) {
        const r = Math.min(4, b.w / 2, b.h);
        const x0 = b.x;
        const x1 = b.x + b.w;
        const y0 = b.top;
        const y1 = b.top + b.h;
        return `M${x0},${y1} L${x0},${y0 + r} Q${x0},${y0} ${x0 + r},${y0} L${x1 - r},${y0} Q${x1},${y0} ${x1},${y0 + r} L${x1},${y1} Z`;
    }
}

registry.category("actions").add("dmag_ai_forecast", AiForecastPage);
