/** @odoo-module **/

import { Component, onWillStart, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const intFmt = new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 0 });
const dec1Fmt = new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 1 });
const dec2Fmt = new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 2 });

const STATUS = {
    on_track: { tone: "good", icon: "fa-check-circle" },
    achieved: { tone: "good", icon: "fa-trophy" },
    behind: { tone: "warn", icon: "fa-clock-o" },
    at_risk: { tone: "bad", icon: "fa-exclamation-triangle" },
    missed: { tone: "bad", icon: "fa-times-circle" },
    no_target: { tone: "muted", icon: "fa-bullseye" },
    no_data: { tone: "muted", icon: "fa-minus-circle" },
    not_started: { tone: "muted", icon: "fa-hourglass-start" },
};
const OKR_STATUS = {
    on_track: { label: "Đúng tiến độ", tone: "good" },
    achieved: { label: "Đã đạt", tone: "good" },
    at_risk: { label: "Chậm", tone: "warn" },
    off_track: { label: "Nguy cơ", tone: "bad" },
};
const SOURCE_LABEL = { target: "Giám đốc đặt", derived: "cộng từ kỳ nhỏ", dmag: "chuẩn DMAG" };

/** Tiền rút gọn kiểu Việt: 1,25 tỷ · 450,5 tr · 85.000 ₫ */
export function moneyShort(v) {
    if (v === null || v === undefined) {
        return "–";
    }
    const a = Math.abs(v);
    if (a >= 1e9) {
        return `${dec2Fmt.format(v / 1e9)} tỷ`;
    }
    if (a >= 1e6) {
        return `${dec1Fmt.format(v / 1e6)} tr`;
    }
    return `${intFmt.format(Math.round(v))} ₫`;
}

/** Bảng điều hành mục tiêu – Mục tiêu kinh doanh · OKR · KPI. Một RPC cho cả màn hình. */
export class GoalDashboard extends Component {
    static template = "dmag_dental_goals.GoalDashboard";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.root = useRef("root");
        this.state = useState({
            data: null, periodType: "month", dateRef: false, companyId: false, loading: false,
            hoverWf: null, openEmp: {},
        });
        this.moneyShort = moneyShort;
        onWillStart(() => this.load());
    }

    async load() {
        this.state.loading = true;
        try {
            this.state.data = await this.orm.call("dmag.goal.dashboard", "get_goal_dashboard",
                [this.state.periodType, this.state.dateRef, this.state.companyId]);
        } finally {
            this.state.loading = false;
        }
    }

    // ------------------------------------------------------------ controls
    async setPeriodType(type) {
        this.state.periodType = type;
        this.state.dateRef = false;
        await this.load();
    }
    async shift(dir) {
        const p = this.state.data.period;
        this.state.dateRef = dir < 0 ? p.prev_ref : p.next_ref;
        await this.load();
    }
    async thisPeriod() {
        this.state.dateRef = false;
        await this.load();
    }
    async setCompany(ev) {
        this.state.companyId = parseInt(ev.target.value) || false;
        await this.load();
    }
    open(action) {
        if (action) {
            this.action.doAction(action);
        }
    }
    scrollTo(id) {
        const el = this.root.el && this.root.el.querySelector(`#${id}`);
        if (el) {
            el.scrollIntoView({ behavior: "smooth", block: "start" });
        }
    }
    toggleEmp(id) {
        this.state.openEmp[id] = !this.state.openEmp[id];
    }

    // ------------------------------------------------------------ format
    fmt(unit, v) {
        if (v === null || v === undefined) {
            return "–";
        }
        switch (unit) {
            case "money":
                return moneyShort(v);
            case "pct":
                return `${dec1Fmt.format(v)}%`;
            case "min":
                return `${dec1Fmt.format(v)} phút`;
            case "score":
                return intFmt.format(Math.round(v));
            default:
                return Number.isInteger(v) ? intFmt.format(v) : dec1Fmt.format(v);
        }
    }
    dec(v) {
        return v === null || v === undefined ? "–" : dec1Fmt.format(v);
    }
    pct(v) {
        return v === null || v === undefined ? "–" : `${intFmt.format(Math.round(v))}%`;
    }
    status(key) {
        return STATUS[key] || STATUS.no_data;
    }
    okrStatus(key) {
        return OKR_STATUS[key] || { label: key || "–", tone: "muted" };
    }
    sourceLabel(src) {
        return SOURCE_LABEL[src] || "";
    }
    targetText(card) {
        if (card.target === null || card.target === undefined) {
            return "Chưa đặt mục tiêu";
        }
        const sign = card.kind === "rate" ? (card.direction === "lower" ? "≤ " : "≥ ") : "";
        return `${sign}${this.fmt(card.unit, card.target)}`;
    }
    deltaText(card) {
        if (card.delta === null || card.delta === undefined) {
            return "";
        }
        const sign = card.delta > 0 ? "+" : card.delta < 0 ? "−" : "±";
        return `${sign}${dec1Fmt.format(Math.abs(card.delta))}${card.delta_unit || ""}`;
    }
    /** Chiều tốt của thay đổi so kỳ trước: up-good / down-good. */
    deltaTone(card) {
        if (!card.delta) {
            return "is-flat";
        }
        const good = card.direction === "lower" ? card.delta < 0 : card.delta > 0;
        return good ? "is-up" : "is-down";
    }

    // ------------------------------------------------------------ bullet (thực tế · dự báo · mục tiêu · nhịp)
    bullet(card) {
        const p = this.state.data.period;
        const actual = Math.max(0, card.actual || 0);
        const target = card.target;
        const forecast = card.kind === "sum" && card.forecast !== null && card.forecast !== undefined
            ? Math.max(0, card.forecast) : null;
        let max;
        if (card.unit === "pct") {
            max = 100;
        } else {
            max = Math.max(actual, target || 0, forecast || 0) * 1.08 || 1;
        }
        const pos = (v) => Math.max(0, Math.min(100, (100 * v) / max));
        return {
            actual: pos(actual),
            forecast: forecast !== null && !p.is_past ? pos(forecast) : null,
            target: target !== null && target !== undefined && target >= 0 ? pos(target) : null,
            pace: card.kind === "sum" && target && !p.is_past && !p.is_future ? pos((target * p.elapsed_pct) / 100) : null,
        };
    }

    // ------------------------------------------------------------ sparkline 6 kỳ
    spark(card) {
        const pts = card.spark || [];
        const W = 132;
        const H = 36;
        const pad = 5;
        const vals = pts.map((p) => p.value).filter((v) => v !== null && v !== undefined);
        if (vals.length < 2) {
            return null;
        }
        const min = Math.min(...vals, card.kind === "sum" ? 0 : Infinity);
        const max = Math.max(...vals);
        const span = max - min || 1;
        const step = (W - pad * 2) / Math.max(1, pts.length - 1);
        const coords = pts.map((p, i) => ({
            x: pad + i * step,
            y: p.value === null || p.value === undefined ? null : H - pad - ((p.value - min) / span) * (H - pad * 2),
            label: p.label, value: p.value, partial: p.partial,
        }));
        let d = "";
        let pen = false;
        for (const c of coords) {
            if (c.y === null) {
                pen = false;
                continue;
            }
            d += `${pen ? "L" : "M"}${c.x.toFixed(1)},${c.y.toFixed(1)} `;
            pen = true;
        }
        const last = coords[coords.length - 1];
        return { W, H, d, coords, last: last.y === null ? null : last };
    }
    sparkTitle(card, c) {
        return `${c.label}${c.partial ? " (đến hôm nay)" : ""}: ${this.fmt(card.unit, c.value)}`;
    }

    // ------------------------------------------------------------ phễu
    funnelWidth(step) {
        const first = this.state.data.funnel.steps[0].count || 1;
        return Math.max(2, Math.min(100, (100 * step.count) / Math.max(first, step.count)));
    }

    // ------------------------------------------------------------ thác nước lợi nhuận gộp
    get waterfall() {
        const steps = this.state.data.finance.waterfall;
        const W = 640;
        const H = 230;
        const pad = { l: 12, r: 12, t: 26, b: 44 };
        const revenue = Math.max(1, steps[0].value || 0);
        const lo = Math.min(0, steps[steps.length - 1].value || 0);
        const span = revenue - lo || 1;
        const y = (v) => pad.t + ((revenue - v) / span) * (H - pad.t - pad.b);
        const band = (W - pad.l - pad.r) / steps.length;
        const barW = Math.min(64, band * 0.56);
        let running = revenue;
        const bars = steps.map((s, i) => {
            const x = pad.l + i * band + (band - barW) / 2;
            const v = s.value;
            let top;
            let bottom;
            if (v === null || v === undefined) {
                top = bottom = y(running);
            } else if (s.kind === "total") {
                top = y(Math.max(v, 0));
                bottom = y(Math.min(v, 0));
                running = v;
            } else {
                top = y(running);
                running -= v;
                bottom = y(running);
            }
            const pct = steps[0].value ? (100 * (v || 0)) / steps[0].value : null;
            return {
                ...s, i, x, w: barW, top, h: Math.max(1, bottom - top), cx: x + barW / 2,
                na: v === null || v === undefined, pct,
                text: v === null || v === undefined ? "chưa cài" : (s.kind === "minus" ? "−" : "") + moneyShort(v),
            };
        });
        return { W, H, pad, bars, base: y(0) };
    }
    wfLabelLines(label) {
        const words = label.split(" ");
        if (label.length <= 14) {
            return [label];
        }
        const mid = Math.ceil(words.length / 2);
        return [words.slice(0, mid).join(" "), words.slice(mid).join(" ")];
    }
}

registry.category("actions").add("dmag_goal_dashboard", GoalDashboard, { force: true });
