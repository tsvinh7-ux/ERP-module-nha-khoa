/** @odoo-module **/

import { Component, useState } from "@odoo/owl";

const SIZE = 46; // cạnh ô răng
const GAP = 6;
const MID = 18; // khoảng hở đường giữa
const INSET = Math.round(SIZE * 0.3);
const LABEL = 18;

const PERMANENT_ROWS = {
    upper: [[18, 17, 16, 15, 14, 13, 12, 11], [21, 22, 23, 24, 25, 26, 27, 28]],
    lower: [[48, 47, 46, 45, 44, 43, 42, 41], [31, 32, 33, 34, 35, 36, 37, 38]],
};
const PRIMARY_ROWS = {
    upper: [[55, 54, 53, 52, 51], [61, 62, 63, 64, 65]],
    lower: [[85, 84, 83, 82, 81], [71, 72, 73, 74, 75]],
};

function quadrantOf(code) {
    return Math.floor(Number(code) / 10);
}

function isUpper(code) {
    return [1, 2, 5, 6].includes(quadrantOf(code));
}

function isAnterior(code) {
    return Number(code) % 10 <= 3;
}

/**
 * Ánh xạ mặt răng → vị trí trên ô vẽ (nhìn từ phía bác sĩ, quy ước FDI).
 * Hàm trên: ngoài (B) ở trên, trong (L) ở dưới. Hàm dưới thì ngược lại.
 * Cung 1/4/5/8 (bên phải bệnh nhân, bên trái màn hình): mặt gần (M) hướng vào đường giữa → phải.
 */
function surfaceSlots(code) {
    const upper = isUpper(code);
    const rightSide = [1, 4, 5, 8].includes(quadrantOf(code));
    return {
        top: upper ? "B" : "L",
        bottom: upper ? "L" : "B",
        left: rightSide ? "D" : "M",
        right: rightSide ? "M" : "D",
        center: isAnterior(code) ? "I" : "O",
    };
}

export class Odontogram extends Component {
    static template = "dmag_clinic_workspace.Odontogram";
    static props = {
        entries: Array,
        dentition: { type: String, optional: true }, // permanent | primary | mixed
        selection: Object, // { teeth: {code: Set(surfaces)} }
        onToggleTooth: Function,
        onToggleSurface: Function,
        showPlanned: { type: Boolean, optional: true },
    };
    static defaultProps = { dentition: "permanent", showPlanned: true };

    setup() {
        this.state = useState({ hover: null });
        this.size = SIZE;
        this.inset = INSET;
    }

    get rows() {
        const sets = [];
        const dentition = this.props.dentition;
        if (dentition === "permanent" || dentition === "mixed") {
            sets.push({ key: "perm", rows: PERMANENT_ROWS });
        }
        if (dentition === "primary" || dentition === "mixed") {
            sets.push({ key: "prim", rows: PRIMARY_ROWS });
        }
        const layout = [];
        let y = 6;
        const maxPerSide = 8;
        const sideWidth = maxPerSide * (SIZE + GAP);
        const totalWidth = sideWidth * 2 + MID;
        for (const set of sets) {
            for (const arch of ["upper", "lower"]) {
                const [left, right] = set.rows[arch];
                const teeth = [];
                const leftStart = sideWidth - left.length * (SIZE + GAP);
                left.forEach((code, i) => teeth.push(this._tooth(code, leftStart + i * (SIZE + GAP), y, arch)));
                right.forEach((code, i) =>
                    teeth.push(this._tooth(code, sideWidth + MID + i * (SIZE + GAP), y, arch))
                );
                layout.push({ key: `${set.key}-${arch}`, arch, y, teeth });
                y += SIZE + LABEL + (arch === "upper" ? 10 : 26);
            }
        }
        this.height = y;
        this.width = totalWidth;
        return layout;
    }

    _tooth(code, x, y, arch) {
        const labelY = arch === "upper" ? y + 12 : y + LABEL + SIZE + 14;
        const boxY = arch === "upper" ? y + LABEL : y;
        return { code: String(code), x, y: boxY, labelY, arch };
    }

    /** Ghi nhận còn hiệu lực trên một răng, cũ → mới */
    entriesFor(code) {
        return this.props.entries.filter(
            (e) => e.tooth === code && (this.props.showPlanned || e.layer !== "planned")
        );
    }

    surfacePolys(tooth) {
        const { x, y } = tooth;
        const s = SIZE;
        const i = INSET;
        const slots = surfaceSlots(tooth.code);
        const pts = (arr) => arr.map((p) => p.join(",")).join(" ");
        return [
            { slot: "top", surface: slots.top, points: pts([[x, y], [x + s, y], [x + s - i, y + i], [x + i, y + i]]) },
            { slot: "bottom", surface: slots.bottom, points: pts([[x, y + s], [x + s, y + s], [x + s - i, y + s - i], [x + i, y + s - i]]) },
            { slot: "left", surface: slots.left, points: pts([[x, y], [x + i, y + i], [x + i, y + s - i], [x, y + s]]) },
            { slot: "right", surface: slots.right, points: pts([[x + s, y], [x + s - i, y + i], [x + s - i, y + s - i], [x + s, y + s]]) },
            { slot: "center", surface: slots.center, points: pts([[x + i, y + i], [x + s - i, y + i], [x + s - i, y + s - i], [x + i, y + s - i]]) },
        ];
    }

    /** Màu + kiểu cho từng mặt răng theo ghi nhận mới nhất */
    surfaceStyle(tooth, surface) {
        let style = { fill: "#FFFFFF", planned: false };
        for (const entry of this.entriesFor(tooth.code)) {
            if (entry.symbol !== "fill") {
                continue;
            }
            const appliesTooth = !entry.surfaces.length;
            if (appliesTooth || entry.surfaces.includes(surface)) {
                style = { fill: entry.color, planned: entry.layer === "planned" };
            }
        }
        return style;
    }

    symbolsFor(tooth) {
        const symbols = [];
        for (const entry of this.entriesFor(tooth.code)) {
            if (entry.symbol !== "fill") {
                symbols.push(entry);
            }
        }
        return symbols;
    }

    isSelected(code) {
        return code in this.props.selection.teeth;
    }

    isSurfaceSelected(code, surface) {
        const surfaces = this.props.selection.teeth[code];
        return surfaces ? surfaces.includes(surface) : false;
    }

    hasFinding(code) {
        return this.entriesFor(code).some((e) => e.category === "finding");
    }

    onSurfaceClick(tooth, surface) {
        this.props.onToggleSurface(tooth.code, surface);
    }

    onToothClick(tooth) {
        this.props.onToggleTooth(tooth.code);
    }
}
