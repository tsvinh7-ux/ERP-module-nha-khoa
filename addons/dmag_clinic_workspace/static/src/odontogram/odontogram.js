/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import {
    CELL,
    PITCH,
    hatchId,
    occlusalGeometry,
    sideGeometry,
    surfaceLabel,
    toothInfo,
    toothVisual,
} from "./tooth_geometry";

const PERMANENT_ROWS = {
    upper: [[18, 17, 16, 15, 14, 13, 12, 11], [21, 22, 23, 24, 25, 26, 27, 28]],
    lower: [[48, 47, 46, 45, 44, 43, 42, 41], [31, 32, 33, 34, 35, 36, 37, 38]],
};
const PRIMARY_ROWS = {
    upper: [[55, 54, 53, 52, 51], [61, 62, 63, 64, 65]],
    lower: [[85, 84, 83, 82, 81], [71, 72, 73, 74, 75]],
};

const GUTTER = 10; // lề trái/phải
const MIDGAP = 18; // khe đường giữa
const CAPTION = 22; // dòng chú thích "Phía má / môi"
const SIDE_GAP = 5; // giữa hình mặt bên và hình mặt nhai
const NUM_H = 24; // dòng số răng
const BAND = 40; // dải giữa 2 hàm (phía khẩu cái / lưỡi)
const TITLE_H = 20; // tiêu đề khối khi hiển thị hỗn hợp

const LAYER_LABELS = { existing: "Hiện trạng", planned: "Kế hoạch", done: "Đã điều trị" };

let nextUid = 1;

export const BASE_FILL = "#FFFFFF";
export const ROOT_FILL = "#F3EBDC";

/** Tên đầy đủ của răng + mặt răng cho tooltip / aria-label. */
export function toothTitle(info, surface) {
    let text = `Răng ${info.code} – ${info.name}`;
    if (surface) {
        const lb = surfaceLabel(surface, info);
        text += ` · mặt ${lb.short} (${lb.tag})`;
    }
    return text;
}

/**
 * Sơ đồ răng FDI: mỗi răng có hình mặt bên (thân + chân răng, nhìn từ phía má/môi)
 * và hình mặt nhai chia 5 mặt theo đúng giải phẫu, đặt theo góc nhìn bác sĩ đối diện bệnh nhân.
 */
export class Odontogram extends Component {
    static template = "dmag_clinic_workspace.Odontogram";
    static props = {
        entries: Array,
        dentition: { type: String, optional: true }, // permanent | primary | mixed
        selection: { type: Object, optional: true }, // { teeth: {code: [surfaces]} }
        onToggleTooth: { type: Function, optional: true },
        onToggleSurface: { type: Function, optional: true },
        showPlanned: { type: Boolean, optional: true },
        readonly: { type: Boolean, optional: true },
        highlight: { type: Array, optional: true }, // răng cần làm nổi bật (vd. răng trong kế hoạch)
        showLegend: { type: Boolean, optional: true },
    };
    static defaultProps = {
        dentition: "permanent",
        showPlanned: true,
        readonly: false,
        showLegend: true,
    };

    setup() {
        this.uid = `dmagodo${nextUid++}`;
        this.state = useState({ tip: null });
        this.BASE_FILL = BASE_FILL;
        this.ROOT_FILL = ROOT_FILL;
        this.LAYER_LABELS = LAYER_LABELS;
        this.surfaceLabel = surfaceLabel;
    }

    get interactive() {
        return !this.props.readonly && !!this.props.onToggleTooth;
    }

    get selectionTeeth() {
        return (this.props.selection && this.props.selection.teeth) || {};
    }

    /** Ghi nhận còn hiệu lực đang hiển thị (cũ → mới). */
    get visibleEntries() {
        return this.props.entries.filter((e) => this.props.showPlanned || e.layer !== "planned");
    }

    get entriesByTooth() {
        const map = {};
        for (const e of this.visibleEntries) {
            (map[e.tooth] = map[e.tooth] || []).push(e);
        }
        return map;
    }

    get hatchColors() {
        const colors = new Set();
        for (const e of this.visibleEntries) {
            if (e.layer === "planned") {
                colors.add(e.color || "#178BEC");
            }
        }
        return [...colors].map((color) => ({ color, id: hatchId(this.uid, color) }));
    }

    // ------------------------------------------------------------ layout
    get layout() {
        const dentition = this.props.dentition;
        const sets = [];
        if (dentition === "permanent" || dentition === "mixed") {
            sets.push({ key: "perm", title: "Răng vĩnh viễn", rows: PERMANENT_ROWS });
        }
        if (dentition === "primary" || dentition === "mixed") {
            sets.push({ key: "prim", title: "Răng sữa", rows: PRIMARY_ROWS });
        }
        const perSide = Math.max(...sets.map((s) => s.rows.upper[0].length));
        const width = GUTTER * 2 + perSide * 2 * PITCH + MIDGAP;
        const mid = width / 2;
        const byTooth = this.entriesByTooth;
        const highlight = new Set((this.props.highlight || []).map(String));
        const selected = this.selectionTeeth;
        const blocks = [];
        let y = 0;
        for (const set of sets) {
            const showTitle = sets.length > 1;
            const top = y;
            y += showTitle ? TITLE_H : 0;
            const codes = [...set.rows.upper[0], ...set.rows.lower[0]];
            const infos = codes.map((c) => toothInfo(c));
            const sideH = Math.ceil(Math.max(...infos.map((i) => i.C + i.R + (i.roots === 3 ? 3 : 0)))) + 4;
            const mapH = Math.ceil(Math.max(...infos.map((i) => i.d))) + 6;
            const captionTop = y + 15;
            // hàm trên
            const upperSideTop = y + CAPTION;
            const upperSideBase = upperSideTop + sideH; // bờ nhai của hình mặt bên
            const upperMapY = upperSideBase + SIDE_GAP + mapH / 2;
            const upperNumY = upperSideBase + SIDE_GAP + mapH + NUM_H / 2 + 1;
            const bandTop = upperSideBase + SIDE_GAP + mapH + NUM_H;
            const bandMid = bandTop + BAND / 2;
            // hàm dưới
            const lowerNumY = bandTop + BAND + NUM_H / 2 - 1;
            const lowerMapTop = bandTop + BAND + NUM_H;
            const lowerMapY = lowerMapTop + mapH / 2;
            const lowerSideBase = lowerMapTop + mapH + SIDE_GAP;
            const bottom = lowerSideBase + sideH;
            const captionBottom = bottom + 15;
            const teeth = [];
            for (const arch of ["upper", "lower"]) {
                const [right, left] = set.rows[arch];
                for (const code of [...right, ...left]) {
                    const info = toothInfo(code);
                    const idx = info.pos - 1;
                    const cx = info.patientRight
                        ? mid - MIDGAP / 2 - PITCH / 2 - idx * PITCH
                        : mid + MIDGAP / 2 + PITCH / 2 + idx * PITCH;
                    const upper = arch === "upper";
                    const sideBase = upper ? upperSideBase : lowerSideBase;
                    const mapY = upper ? upperMapY : lowerMapY;
                    const numY = upper ? upperNumY : lowerNumY;
                    const entries = byTooth[info.code] || [];
                    const visual = toothVisual(entries);
                    const side = sideGeometry(info);
                    // phạm vi cột (để tô nền khi chọn / làm nổi bật)
                    const colTop = upper ? sideBase - side.height - 4 : numY - NUM_H / 2 + 1;
                    const colBottom = upper ? numY + NUM_H / 2 - 1 : sideBase + side.height + 4;
                    teeth.push({
                        code: info.code,
                        info,
                        cx,
                        numY,
                        colTop,
                        colBottom,
                        sideTransform: `translate(${cx},${sideBase}) scale(${info.sx},${upper ? -1 : 1})`,
                        mapTransform: `translate(${cx},${mapY}) scale(${info.sx},${upper ? 1 : -1})`,
                        // vị trí trên màn hình của giữa thân răng / giữa chân răng (cho các ký hiệu không lật)
                        crownMidY: upper ? sideBase - info.C / 2 : sideBase + info.C / 2,
                        rootMidY: upper ? sideBase - info.C - info.R * 0.45 : sideBase + info.C + info.R * 0.45,
                        crossTop: upper ? sideBase - side.height : mapY - info.d / 2 - 2,
                        crossBottom: upper ? mapY + info.d / 2 + 2 : sideBase + side.height,
                        side,
                        occ: occlusalGeometry(info),
                        visual,
                        entries,
                        selected: info.code in selected,
                        picked: selected[info.code] || [],
                        highlighted: highlight.has(info.code),
                        hasFinding: entries.some((e) => e.category === "finding" && e.layer !== "planned"),
                        hasPlan: entries.some((e) => e.layer === "planned"),
                        ghost: !!(visual.missing && !visual.missing.planned) || !!visual.unerupted,
                    });
                }
            }
            blocks.push({
                key: set.key,
                title: showTitle ? set.title : "",
                top,
                titleY: top + 14,
                captionTop,
                captionBottom,
                bandTop,
                bandMid,
                bottom: captionBottom + 9,
                teeth,
                quarterL: GUTTER + (perSide * PITCH) / 2,
                quarterR: width - GUTTER - (perSide * PITCH) / 2,
                spanL: mid - MIDGAP / 2 - set.rows.upper[0].length * PITCH,
                spanR: mid + MIDGAP / 2 + set.rows.upper[0].length * PITCH,
            });
            y = captionBottom + 9 + (sets.length > 1 ? 14 : 0);
        }
        return { blocks, width, height: y - (sets.length > 1 ? 14 : 0), mid };
    }

    // ------------------------------------------------------------ rendering helpers
    paint(style, fallback) {
        if (!style) {
            return fallback;
        }
        return style.planned ? `url(#${hatchId(this.uid, style.color)})` : style.color;
    }

    ringStyle(style, width) {
        if (!style) {
            return null;
        }
        return `stroke:${style.color};stroke-width:${width}px;${style.planned ? "stroke-dasharray:4 2.5;" : ""}`;
    }

    surfaceFill(tooth, surface) {
        return this.paint(tooth.visual.surfaces[surface], BASE_FILL);
    }

    isPicked(tooth, surface) {
        return tooth.picked.includes(surface);
    }

    toothClass(tooth) {
        let cls = "o-odo-tooth";
        if (tooth.selected) {
            cls += " is-selected";
        }
        if (tooth.highlighted) {
            cls += " is-highlight";
        }
        if (tooth.hasFinding) {
            cls += " has-finding";
        }
        if (tooth.ghost) {
            cls += " is-ghost";
        }
        return cls;
    }

    regionTitle(tooth, surface) {
        const lb = surfaceLabel(surface, tooth.info);
        return `${toothTitle(tooth.info, surface)} – ${lb.name.toLowerCase()} ${lb.hint}`;
    }

    // ------------------------------------------------------------ tooltip
    _tipLines(tooth, surface) {
        const lines = [];
        for (const e of tooth.entries) {
            if (surface && e.surfaces.length && !e.surfaces.includes(surface)) {
                continue;
            }
            lines.push({
                id: e.id,
                color: e.color,
                text: `${e.condition}${e.surfaces.length ? " (" + e.surfaces.join("") + ")" : ""}`,
                layer: LAYER_LABELS[e.layer] || "",
                planned: e.layer === "planned",
            });
        }
        return lines;
    }

    showTip(ev, tooth, surface) {
        const lb = surface ? surfaceLabel(surface, tooth.info) : null;
        this.state.tip = {
            title: `Răng ${tooth.code} – ${tooth.info.name}`,
            surface: lb ? `mặt ${lb.short} (${lb.tag})` : "",
            hint: lb ? `${lb.name} – ${lb.hint}` : this.interactive ? "Chạm để chọn cả răng" : "",
            lines: this._tipLines(tooth, surface),
            ...this._tipPos(ev),
        };
    }

    moveTip(ev) {
        if (this.state.tip) {
            Object.assign(this.state.tip, this._tipPos(ev));
        }
    }

    hideTip() {
        this.state.tip = null;
    }

    _tipPos(ev) {
        const host = ev.currentTarget.closest(".o-odo");
        const rect = host.getBoundingClientRect();
        const x = ev.clientX - rect.left;
        const y = ev.clientY - rect.top;
        return { x, y, flip: x > rect.width - 280 };
    }

    // ------------------------------------------------------------ events
    onSurfaceClick(tooth, surface) {
        if (this.interactive && this.props.onToggleSurface) {
            this.props.onToggleSurface(tooth.code, surface);
        }
    }

    onToothClick(tooth) {
        if (this.interactive) {
            this.props.onToggleTooth(tooth.code);
        }
    }

    onToothKey(ev, tooth) {
        if (ev.key === "Enter" || ev.key === " ") {
            ev.preventDefault();
            this.onToothClick(tooth);
        }
    }

    // ------------------------------------------------------------ legend
    get legendConditions() {
        const seen = new Map();
        for (const e of this.visibleEntries) {
            const key = e.condition_id || e.condition;
            if (!seen.has(key)) {
                seen.set(key, { key, name: e.condition, color: e.color, symbol: e.symbol, code: e.condition_code || "" });
            }
        }
        return [...seen.values()];
    }

    get surfaceKey() {
        return [
            { tag: "O / I", name: "Mặt nhai / rìa cắn", hint: "đỉnh răng, chỗ ăn nhai" },
            { tag: "B / F", name: "Mặt ngoài", hint: "phía má / môi – “mặt trước”" },
            { tag: "L / P", name: "Mặt trong", hint: "phía lưỡi / khẩu cái – “mặt sau”" },
            { tag: "M", name: "Mặt gần", hint: "mặt bên hướng về đường giữa" },
            { tag: "D", name: "Mặt xa", hint: "mặt bên hướng ra sau" },
        ];
    }

    /** Răng mẫu cho chú giải: 16 (hàm trên phải) nhìn từ mặt nhai, có nhãn từng mặt. */
    get keyTooth() {
        const info = toothInfo(16);
        return { info, occ: occlusalGeometry(info) };
    }
}

export { CELL, PITCH };
