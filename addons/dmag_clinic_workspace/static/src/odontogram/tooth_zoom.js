/** @odoo-module **/

import { Component } from "@odoo/owl";
import {
    hatchId,
    occlusalGeometry,
    screenSlots,
    sideGeometry,
    surfaceLabel,
    toothInfo,
    toothVisual,
} from "./tooth_geometry";
import { BASE_FILL, ROOT_FILL } from "./odontogram";

const MAP_CX = 204;
const MAP_CY = 118;
const SIDE_CX = 54;

let nextUid = 1;

/**
 * Khung phóng to 1 răng: hình mặt nhai cỡ lớn có ghi tên từng mặt + hình mặt bên,
 * để bác sĩ chọn đúng mặt răng (và giải thích cho bệnh nhân).
 */
export class ToothZoom extends Component {
    static template = "dmag_clinic_workspace.ToothZoom";
    static props = {
        code: String,
        entries: Array,
        surfaces: { type: Array, optional: true },
        onToggleSurface: { type: Function, optional: true },
        showPlanned: { type: Boolean, optional: true },
        readonly: { type: Boolean, optional: true },
    };
    static defaultProps = { surfaces: [], showPlanned: true, readonly: false };

    setup() {
        this.uid = `dmagzoom${nextUid++}`;
        this.BASE_FILL = BASE_FILL;
        this.ROOT_FILL = ROOT_FILL;
    }

    get model() {
        const info = toothInfo(this.props.code);
        const entries = this.props.entries.filter(
            (e) => e.tooth === info.code && (this.props.showPlanned || e.layer !== "planned")
        );
        const visual = toothVisual(entries);
        const occ = occlusalGeometry(info);
        const side = sideGeometry(info);
        const ko = Math.min(4.1, 150 / Math.max(info.w, info.d));
        const ks = Math.min(1.9, 150 / side.height, 84 / info.w);
        const sideBase = info.upper ? 196 : 44;
        const sy = info.upper ? -1 : 1;
        const slots = screenSlots(info);
        const halfW = (info.w * ko) / 2;
        const halfH = (info.d * ko) / 2;
        const centerDy = info.anterior ? -info.d * 0.09 * ko * (info.upper ? 1 : -1) : 0;
        const label = (surface, x, y) => {
            const lb = surfaceLabel(surface, info);
            return { surface, x, y, tag: lb.tag, short: lb.short };
        };
        const regionLabels = [
            label(slots.top, MAP_CX, MAP_CY - halfH * 0.66),
            label(slots.bottom, MAP_CX, MAP_CY + halfH * 0.7),
            label(slots.left, MAP_CX - halfW * 0.74, MAP_CY),
            label(slots.right, MAP_CX + halfW * 0.74, MAP_CY),
            label(slots.center, MAP_CX, MAP_CY + centerDy),
        ];
        const dir = (surface) => {
            switch (surface) {
                case "B":
                    return info.anterior ? "phía môi · mặt trước" : "phía má · mặt ngoài";
                case "L":
                    return info.upper ? "phía khẩu cái · mặt sau" : "phía lưỡi · mặt sau";
                case "M":
                    return "gần – về đường giữa";
                case "D":
                    return "xa – ra sau";
                default:
                    return "";
            }
        };
        // nhãn chữ trên hình mặt bên (tọa độ màn hình)
        const crownMid = info.upper ? sideBase - (info.C * ks) / 2 : sideBase + (info.C * ks) / 2;
        const edgeY = info.upper ? sideBase - 6 : sideBase + 12;
        const mx = SIDE_CX + info.sx * info.w * 0.37 * ks;
        const dx = SIDE_CX - info.sx * info.w * 0.37 * ks;
        const sideLabels = [
            { key: "B", x: SIDE_CX, y: crownMid + (info.upper ? -2 : 6), text: info.anterior ? "B/F" : "B" },
            { key: "M", x: mx, y: crownMid + 3, text: "M" },
            { key: "D", x: dx, y: crownMid + 3, text: "D" },
            { key: "E", x: SIDE_CX, y: edgeY, text: info.anterior ? "I" : "O" },
        ];
        const listOrder = [slots.center, "B", "L", "M", "D"];
        const buttons = listOrder.map((s) => {
            const lb = surfaceLabel(s, info);
            const finding = visual.surfaces[s] || visual.planSurfaces[s] || null;
            return { surface: s, tag: lb.tag, name: lb.name, hint: lb.hint, finding, picked: this.props.surfaces.includes(s) };
        });
        const hatch = [...new Set(entries.filter((e) => e.layer === "planned").map((e) => e.color))].map((color) => ({
            color, id: hatchId(this.uid, color),
        }));
        return {
            info, entries, visual, occ, side, slots, regionLabels, sideLabels, buttons, hatch,
            mapTransform: `translate(${MAP_CX},${MAP_CY}) scale(${info.sx * ko},${(info.upper ? 1 : -1) * ko})`,
            sideTransform: `translate(${SIDE_CX},${sideBase}) scale(${info.sx * ks},${sy * ks})`,
            topText: `▲ ${dir(slots.top)}`,
            bottomText: `▼ ${dir(slots.bottom)}`,
            leftText: `◀ ${dir(slots.left)}`,
            rightText: `${dir(slots.right)} ▶`,
            topY: MAP_CY - halfH - 8,
            bottomY: MAP_CY + halfH + 17,
            sideCaption: info.anterior ? "nhìn từ phía môi" : "nhìn từ phía má",
            sideCaptionTopY: info.upper ? 20 : 216,
        };
    }

    paint(style, fallback) {
        if (!style) {
            return fallback;
        }
        return style.planned ? `url(#${hatchId(this.uid, style.color)})` : style.color;
    }

    fill(model, surface) {
        return this.paint(model.visual.surfaces[surface], BASE_FILL);
    }

    isPicked(surface) {
        return this.props.surfaces.includes(surface);
    }

    toggle(surface) {
        if (!this.props.readonly && this.props.onToggleSurface) {
            this.props.onToggleSurface(this.props.code, surface);
        }
    }

    regionTitle(model, surface) {
        const lb = surfaceLabel(surface, model.info);
        return `Răng ${model.info.code} · ${lb.name} (${lb.tag}) – ${lb.hint}`;
    }
}
