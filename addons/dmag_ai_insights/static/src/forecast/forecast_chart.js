/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { money } from "../common/ai_utils";

/** Biểu đồ doanh thu lũy kế trong tháng: thực tế (đường liền) → dự báo (đường đứt) + dải tin cậy 80 % + mục tiêu. */
export class AiForecastChart extends Component {
    static template = "dmag_ai_insights.AiForecastChart";
    static props = { data: Object, compact: { type: Boolean, optional: true } };

    setup() {
        this.state = useState({ hover: null });
        this.money = money;
    }

    get geo() {
        const d = this.props.data;
        const W = this.props.compact ? 360 : 860;
        const H = this.props.compact ? 150 : 300;
        const pad = this.props.compact ? { l: 8, r: 8, t: 14, b: 18 } : { l: 56, r: 92, t: 18, b: 30 };
        const pts = d.cumulative || [];
        const start = new Date(d.from + "T00:00:00");
        const end = new Date(d.to + "T00:00:00");
        const span = Math.max(1, (end - start) / 86400000);
        const maxV = Math.max(
            1,
            d.target || 0,
            ...pts.map((p) => Math.max(p.actual || 0, p.high || 0, p.forecast || 0))
        ) * 1.06;
        const x = (date) => pad.l + (((new Date(date + "T00:00:00") - start) / 86400000) / span) * (W - pad.l - pad.r);
        const y = (v) => H - pad.b - (v / maxV) * (H - pad.t - pad.b);
        const actual = pts.filter((p) => p.actual !== undefined);
        const fc = pts.filter((p) => p.forecast !== undefined);
        const line = (arr, key) => arr.map((p, i) => `${i ? "L" : "M"}${x(p.date).toFixed(1)},${y(p[key]).toFixed(1)}`).join(" ");
        const last = actual[actual.length - 1];
        const fcLine = last && fc.length ? [{ date: last.date, forecast: last.actual, low: last.actual, high: last.actual }, ...fc] : fc;
        let band = "";
        if (fcLine.length > 1) {
            band = fcLine.map((p, i) => `${i ? "L" : "M"}${x(p.date).toFixed(1)},${y(p.high).toFixed(1)}`).join(" ");
            band += " " + [...fcLine].reverse().map((p) => `L${x(p.date).toFixed(1)},${y(p.low).toFixed(1)}`).join(" ") + " Z";
        }
        const ticks = [];
        const step = this.niceStep(maxV / 4);
        for (let v = 0; v <= maxV; v += step) {
            ticks.push({ v, y: y(v), label: money(v) });
        }
        const xTicks = [];
        for (const day of [1, 8, 15, 22, 29]) {
            const dt = new Date(start.getTime() + (day - 1) * 86400000);
            if (dt <= end) {
                const iso = `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, "0")}-${String(dt.getDate()).padStart(2, "0")}`;
                xTicks.push({ x: x(iso), label: `${day}/${dt.getMonth() + 1}` });
            }
        }
        const lastFc = fcLine[fcLine.length - 1];
        return {
            W, H, pad, ticks, xTicks, band,
            actualPath: actual.length > 1 ? line(actual, "actual") : "",
            fcPath: fcLine.length > 1 ? line(fcLine, "forecast") : "",
            targetY: d.target ? y(d.target) : null,
            lastActual: last ? { x: x(last.date), y: y(last.actual), v: last.actual } : null,
            lastFc: lastFc ? { x: x(lastFc.date), y: y(lastFc.forecast), v: lastFc.forecast, lo: lastFc.low, hi: lastFc.high } : null,
            points: pts.map((p) => ({ ...p, x: x(p.date), y: y(p.actual !== undefined ? p.actual : p.forecast) })),
        };
    }

    niceStep(raw) {
        const pow = Math.pow(10, Math.floor(Math.log10(raw || 1)));
        const n = raw / pow;
        return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10) * pow;
    }

    onMove(ev, geo) {
        const rect = ev.currentTarget.getBoundingClientRect();
        const px = ((ev.clientX - rect.left) / rect.width) * geo.W;
        let best = null;
        for (const p of geo.points) {
            if (!best || Math.abs(p.x - px) < Math.abs(best.x - px)) {
                best = p;
            }
        }
        this.state.hover = best;
    }

    onLeave() {
        this.state.hover = null;
    }

    hoverText(p) {
        const [yy, mm, dd] = p.date.split("-");
        if (p.actual !== undefined) {
            return `${dd}/${mm}: thực tế lũy kế ${money(p.actual)}`;
        }
        return `${dd}/${mm}: dự báo lũy kế ${money(p.forecast)} (80%: ${money(p.low)} – ${money(p.high)})`;
    }
}
