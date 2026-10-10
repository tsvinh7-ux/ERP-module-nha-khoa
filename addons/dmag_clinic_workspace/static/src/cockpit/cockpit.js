/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { formatMoney } from "../js/utils";

const compactFmt = new Intl.NumberFormat("vi-VN", { notation: "compact", maximumFractionDigits: 1 });

/** Buồng lái chủ phòng khám – chỉ số điều hành, mục tiêu DMAG, cảnh báo pháp chế. */
export class OwnerCockpit extends Component {
    static template = "dmag_clinic_workspace.OwnerCockpit";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.formatMoney = formatMoney;
        this.state = useState({ data: null, range: "month", hover: null });
        onWillStart(() => this.load());
    }

    async setRange(range) {
        this.state.range = range;
        await this.load();
    }

    async load() {
        const today = new Date();
        const pad = (n) => String(n).padStart(2, "0");
        const iso = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
        let from = new Date(today.getFullYear(), today.getMonth(), 1);
        if (this.state.range === "week") {
            from = new Date(today);
            from.setDate(today.getDate() - 6);
        } else if (this.state.range === "quarter") {
            from = new Date(today.getFullYear(), Math.floor(today.getMonth() / 3) * 3, 1);
        }
        this.state.data = await this.orm.call("dmag.workspace", "get_owner_cockpit", [iso(from), iso(today)]);
    }

    compact(v) {
        return compactFmt.format(v || 0);
    }

    pct(v) {
        return `${(v || 0).toFixed(0)}%`;
    }

    /** Chỉ số so với mục tiêu: trả về trạng thái đạt / cần chú ý. */
    get scorecards() {
        const k = this.state.data.kpis;
        const t = this.state.data.targets;
        const cards = [
            { key: "afternoon", label: "Công suất ghế buổi chiều", value: this.pct(k.afternoon_utilization), target: `≥ ${t.afternoon_utilization}%`, ok: k.afternoon_utilization >= t.afternoon_utilization, ratio: k.afternoon_utilization / 100 },
            { key: "associate", label: "Ca do bác sĩ phụ đảm nhận", value: this.pct(k.associate_share), target: `≥ ${t.associate_share}%`, ok: k.associate_share >= t.associate_share, ratio: k.associate_share / 100 },
            { key: "plan", label: "Tỷ lệ đồng thuận kế hoạch", value: this.pct(k.plan_acceptance), target: `≥ ${t.plan_acceptance}%`, ok: k.plan_acceptance >= t.plan_acceptance, ratio: k.plan_acceptance / 100 },
            { key: "wait", label: "Thời gian chờ trung bình", value: `${(k.avg_wait || 0).toFixed(0)} phút`, target: `≤ ${t.avg_wait} phút`, ok: k.avg_wait <= t.avg_wait, ratio: Math.min(1, (k.avg_wait || 0) / (t.avg_wait * 2)) },
        ];
        const material = this.state.data.extras.material;
        if (material && material.ratio !== undefined) {
            cards.push({ key: "material", label: "Giá vốn vật tư / doanh thu", value: this.pct(material.ratio), target: `≤ ${t.material_ratio}%`, ok: material.ratio <= t.material_ratio, ratio: material.ratio / 100 });
        }
        return cards;
    }

    get chart() {
        const series = this.state.data.series;
        const W = 720;
        const H = 220;
        const pad = { l: 44, r: 8, t: 12, b: 26 };
        const max = Math.max(1, ...series.map((s) => s.revenue));
        const step = (W - pad.l - pad.r) / Math.max(1, series.length);
        const barW = Math.max(2, Math.min(28, step - 2));
        const y = (v) => pad.t + (H - pad.t - pad.b) * (1 - v / max);
        const ticks = [0, 0.5, 1].map((f) => ({ y: y(max * f), label: this.compact(max * f) }));
        const bars = series.map((s, i) => {
            const x = pad.l + i * step + (step - barW) / 2;
            const top = y(s.revenue);
            const h = H - pad.b - top;
            const d = s.date.slice(8, 10) + "/" + s.date.slice(5, 7);
            return { i, x, top, h, w: barW, label: d, value: s.revenue, showLabel: series.length <= 10 || i % Math.ceil(series.length / 8) === 0 };
        });
        return { W, H, pad, bars, ticks, base: H - pad.b };
    }

    maxOf(list, key) {
        return Math.max(1, ...list.map((x) => x[key]));
    }
}

registry.category("actions").add("dmag_owner_cockpit", OwnerCockpit);
