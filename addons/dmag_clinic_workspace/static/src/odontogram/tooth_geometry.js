/** @odoo-module **/

/**
 * Hình học sơ đồ răng FDI (dùng chung cho sơ đồ toàn hàm và khung phóng to 1 răng).
 *
 * Quy ước khung vẽ cục bộ của MỘT răng (trước khi lật):
 *   - Mặt nhai (frame "O"): tâm (0,0); phía má/môi (B) ở TRÊN (y âm); mặt gần (M) ở PHẢI (x dương).
 *   - Mặt bên nhìn từ má (frame "S"): bờ nhai ở y = 0, cổ răng ở y = C, chóp chân răng ở y = C + R
 *     (thân răng ở trên, chân răng đi xuống) – mặt gần (M) ở PHẢI.
 *
 * Sau đó lật theo cung phần tư để đúng giải phẫu khi bác sĩ nhìn đối diện bệnh nhân
 * (bên phải bệnh nhân = bên trái màn hình):
 *   - sx = -1 cho cung 2/3/6/7 (nửa trái bệnh nhân): mặt gần quay sang TRÁI, về đường giữa.
 *   - Hàm trên: frame O giữ nguyên (má ở trên, khẩu cái về đường nhai ở giữa); frame S lật dọc
 *     (chân răng hướng lên trên).
 *   - Hàm dưới: frame O lật dọc (lưỡi ở trên về phía đường nhai, má ở dưới); frame S giữ nguyên.
 */

export const PITCH = 50; // khoảng cách giữa 2 cột răng
export const CELL = 46;

const TYPE_NAMES = {
    permanent: {
        1: "Răng cửa giữa",
        2: "Răng cửa bên",
        3: "Răng nanh",
        4: "Răng cối nhỏ thứ nhất",
        5: "Răng cối nhỏ thứ hai",
        6: "Răng cối lớn thứ nhất",
        7: "Răng cối lớn thứ hai",
        8: "Răng cối lớn thứ ba (răng khôn)",
    },
    primary: {
        1: "Răng cửa giữa sữa",
        2: "Răng cửa bên sữa",
        3: "Răng nanh sữa",
        4: "Răng cối sữa thứ nhất",
        5: "Răng cối sữa thứ hai",
    },
};

// [rộng gần-xa của thân, cao thân C, dài chân R, sâu má-lưỡi d (mặt nhai)]
const DIMS = {
    permanent: {
        upper: { 1: [38, 34, 46, 30], 2: [31, 30, 42, 28], 3: [34, 34, 56, 32], 4: [32, 30, 44, 40],
                 5: [31, 29, 44, 40], 6: [42, 28, 42, 44], 7: [40, 27, 40, 42], 8: [36, 26, 34, 38] },
        lower: { 1: [25, 28, 40, 28], 2: [27, 28, 42, 28], 3: [31, 33, 52, 30], 4: [30, 29, 46, 34],
                 5: [32, 28, 46, 35], 6: [44, 27, 42, 40], 7: [42, 26, 40, 38], 8: [40, 25, 34, 36] },
    },
    primary: {
        upper: { 1: [32, 26, 34, 28], 2: [27, 24, 32, 26], 3: [30, 27, 38, 30], 4: [35, 23, 30, 36],
                 5: [40, 24, 32, 40] },
        lower: { 1: [23, 23, 30, 26], 2: [25, 23, 32, 26], 3: [27, 25, 36, 28], 4: [36, 22, 30, 34],
                 5: [42, 23, 32, 38] },
    },
};

export function toothInfo(code) {
    const n = Number(code);
    const q = Math.floor(n / 10);
    const pos = n % 10;
    const primary = q >= 5;
    const upper = [1, 2, 5, 6].includes(q);
    const patientRight = [1, 4, 5, 8].includes(q);
    let kind;
    if (pos <= 2) {
        kind = "incisor";
    } else if (pos === 3) {
        kind = "canine";
    } else if (primary || pos >= 6) {
        kind = "molar";
    } else {
        kind = "premolar";
    }
    const dentition = primary ? "primary" : "permanent";
    const [w, C, R, d] = DIMS[dentition][upper ? "upper" : "lower"][pos];
    let roots = 1;
    if (kind === "molar") {
        roots = upper ? 3 : 2;
    } else if (kind === "premolar" && upper && pos === 4) {
        roots = 2; // răng cối nhỏ thứ nhất hàm trên: 2 chân (ngoài + trong)
    }
    const name =
        `${TYPE_NAMES[dentition][pos]} ${upper ? "hàm trên" : "hàm dưới"} ${patientRight ? "phải" : "trái"}`;
    return {
        code: String(code), q, pos, primary, upper, patientRight, kind,
        anterior: pos <= 3, roots, w, C, R, d, name,
        sx: patientRight ? 1 : -1,
    };
}

/**
 * Nhãn tiếng Việt cho mặt răng theo đúng loại răng / hàm.
 * Mã lưu trữ không đổi (M, D, O, I, B, L) – F và P chỉ là tên gọi khác của B và L.
 */
export function surfaceLabel(code, info) {
    const anterior = info ? info.anterior : false;
    const upper = info ? info.upper : true;
    switch (code) {
        case "M":
            return { code, short: "Gần", name: "Mặt gần", tag: "M", hint: "mặt bên, phía đường giữa" };
        case "D":
            return { code, short: "Xa", name: "Mặt xa", tag: "D", hint: "mặt bên, phía trong cung hàm (ra sau)" };
        case "O":
            return { code, short: "Nhai", name: "Mặt nhai", tag: "O", hint: "mặt ăn nhai trên đỉnh răng" };
        case "I":
            return { code, short: "Rìa cắn", name: "Rìa cắn", tag: "I", hint: "bờ cắn của răng cửa / răng nanh" };
        case "B":
            return anterior
                ? { code, short: "Ngoài", name: "Mặt ngoài", tag: "B/F", hint: "phía môi – mặt trước" }
                : { code, short: "Ngoài", name: "Mặt ngoài", tag: "B", hint: "phía má" };
        case "L":
            return upper
                ? { code, short: "Trong", name: "Mặt trong", tag: "L/P", hint: "phía khẩu cái (vòm miệng) – mặt sau" }
                : { code, short: "Trong", name: "Mặt trong", tag: "L", hint: "phía lưỡi – mặt sau" };
        default:
            return { code, short: code, name: `Mặt ${code}`, tag: code, hint: "" };
    }
}

/** Mã 5 mặt của một răng: [trên, phải, dưới, trái, giữa] trong khung O chưa lật. */
export function centerSurface(info) {
    return info.anterior ? "I" : "O";
}

/** Mặt nằm ở mỗi phía TRÊN MÀN HÌNH (sau khi lật) – dùng cho nhãn ở khung phóng to. */
export function screenSlots(info) {
    return {
        top: info.upper ? "B" : "L",
        bottom: info.upper ? "L" : "B",
        left: info.patientRight ? "D" : "M",
        right: info.patientRight ? "M" : "D",
        center: centerSurface(info),
    };
}

// ------------------------------------------------------------------ path helpers
const f = (v) => Math.round(v * 10) / 10;

/** Đa giác bo góc mềm: mỗi đỉnh thay bằng một đường cong bậc 2. */
function roundedPoly(points, frac = 0.3) {
    const n = points.length;
    const parts = [];
    for (let i = 0; i < n; i++) {
        const p = points[i];
        const prev = points[(i - 1 + n) % n];
        const next = points[(i + 1) % n];
        const a = [p[0] + (prev[0] - p[0]) * frac, p[1] + (prev[1] - p[1]) * frac];
        const b = [p[0] + (next[0] - p[0]) * frac, p[1] + (next[1] - p[1]) * frac];
        parts.push(`${i === 0 ? "M" : "L"}${f(a[0])},${f(a[1])} Q${f(p[0])},${f(p[1])} ${f(b[0])},${f(b[1])}`);
    }
    return parts.join(" ") + " Z";
}

const poly = (pts) => pts.map((p) => `${f(p[0])},${f(p[1])}`).join(" ");

// ------------------------------------------------------------------ occlusal view (frame O)
function occlusalPoints(info, scale = 1) {
    const w = (info.w * scale) / 2;
    const d = (info.d * scale) / 2;
    switch (info.kind) {
        case "molar":
            if (info.upper) {
                const s = w * 0.12; // hình thoi: góc ngoài-gần nhọn, góc trong-xa nhọn
                return [[-w + s, -d], [w + s, -d], [w - s, d], [-w - s, d]];
            }
            return [[-w, -d], [w, -d], [w * 0.94, d], [-w * 0.86, d]];
        case "premolar":
            return info.upper
                ? [[-w * 0.8, -d], [w * 0.8, -d], [w, 0], [w * 0.72, d], [-w * 0.72, d], [-w, 0]]
                : [[-w * 0.85, -d], [w * 0.85, -d], [w, -d * 0.1], [w * 0.6, d], [-w * 0.6, d], [-w, -d * 0.1]];
        case "canine":
            return [[-w, -d * 0.1], [-w * 0.42, -d], [w * 0.42, -d], [w, -d * 0.1], [w * 0.3, d], [-w * 0.3, d]];
        default: // răng cửa: bờ môi cong rộng, phía lưỡi thu về gót răng
            return [[-w, -d * 0.35], [-w * 0.6, -d], [w * 0.6, -d], [w, -d * 0.35], [w * 0.32, d], [-w * 0.32, d]];
    }
}

function occlusalFrac(info) {
    return info.kind === "molar" ? 0.3 : info.kind === "premolar" ? 0.42 : 0.36;
}

/**
 * Vùng 5 mặt trên mặt nhai: viền giải phẫu + các hình thang (cắt theo viền bằng clipPath)
 * + vùng giữa (mặt nhai / rìa cắn).
 */
export function occlusalGeometry(info) {
    const outline = roundedPoly(occlusalPoints(info), occlusalFrac(info));
    const W = info.w / 2 + 6;
    const H = info.d / 2 + 6;
    let ix0, ix1, iy0, iy1, center;
    if (info.anterior) {
        // rìa cắn: dải hẹp gần phía môi
        ix0 = -info.w * 0.24;
        ix1 = info.w * 0.24;
        iy0 = -info.d * 0.22;
        iy1 = info.d * 0.04;
        center = roundedPoly([[ix0, iy0], [ix1, iy0], [ix1, iy1], [ix0, iy1]], 0.45);
    } else {
        const inner = occlusalPoints(info, 0.5);
        const xs = inner.map((p) => p[0]);
        const ys = inner.map((p) => p[1]);
        ix0 = Math.min(...xs) * 0.9;
        ix1 = Math.max(...xs) * 0.9;
        iy0 = Math.min(...ys);
        iy1 = Math.max(...ys);
        center = roundedPoly(inner, occlusalFrac(info));
    }
    const regions = [
        { slot: "top", surface: "B", points: poly([[-W, -H], [W, -H], [ix1, iy0], [ix0, iy0]]) },
        { slot: "right", surface: "M", points: poly([[W, -H], [W, H], [ix1, iy1], [ix1, iy0]]) },
        { slot: "bottom", surface: "L", points: poly([[W, H], [-W, H], [ix0, iy1], [ix1, iy1]]) },
        { slot: "left", surface: "D", points: poly([[-W, H], [-W, -H], [ix0, iy0], [ix0, iy1]]) },
    ];
    // vết rãnh / múi trên mặt nhai cho dễ nhận ra loại răng
    let grooves = "";
    if (info.kind === "molar") {
        const a = info.w * 0.16;
        const b = info.d * 0.12;
        grooves = `M${f(-a * 1.6)},${f(-b * 0.2)} L${f(-a * 0.4)},${f(b * 0.3)} L${f(a * 0.5)},${f(-b * 0.4)} L${f(a * 1.6)},${f(b * 0.1)}`
            + ` M${f(-a * 0.4)},${f(b * 0.3)} L${f(-a * 0.2)},${f(b * 1.8)} M${f(a * 0.5)},${f(-b * 0.4)} L${f(a * 0.3)},${f(-b * 1.9)}`;
    } else if (info.kind === "premolar") {
        const a = info.w * 0.2;
        grooves = `M${f(-a)},0 Q0,${f(info.d * 0.06)} ${f(a)},0`;
    }
    return { outline, regions, center, centerSurface: centerSurface(info), grooves };
}

// ------------------------------------------------------------------ buccal / labial side view (frame S)
function crownPath(info) {
    const { w, C, kind } = info;
    const h = w / 2;
    const neck = h * (kind === "molar" ? 0.78 : kind === "incisor" ? 0.7 : 0.66);
    const bulgeY = C * 0.32;
    let top;
    let startY;
    if (kind === "molar") {
        startY = C * 0.2;
        const k = info.primary ? 2 : 3; // số múi nhìn từ phía má
        const step = (w * 0.86) / k;
        const x0 = -w * 0.43;
        top = `M${f(-h)},${f(C * 0.2)} Q${f(-h)},${f(C * 0.06)} ${f(x0)},${f(C * 0.08)}`;
        for (let i = 0; i < k; i++) {
            const xa = x0 + step * i;
            const xb = xa + step;
            top += ` Q${f((xa + xb) / 2)},${f(-C * 0.1)} ${f(xb)},${f(C * 0.08)}`;
        }
        top += ` Q${f(h)},${f(C * 0.06)} ${f(h)},${f(C * 0.2)}`;
    } else if (kind === "premolar") {
        startY = C * 0.26;
        top = `M${f(-h)},${f(C * 0.26)} C${f(-h * 0.72)},${f(C * 0.1)} ${f(-h * 0.32)},${f(-C * 0.01)} 0,${f(-C * 0.01)} C${f(h * 0.32)},${f(-C * 0.01)} ${f(h * 0.72)},${f(C * 0.1)} ${f(h)},${f(C * 0.26)}`;
    } else if (kind === "canine") {
        startY = C * 0.3;
        top = `M${f(-h)},${f(C * 0.3)} C${f(-h * 0.62)},${f(C * 0.2)} ${f(-h * 0.26)},${f(C * 0.02)} ${f(-h * 0.04)},${f(-C * 0.03)} C${f(h * 0.18)},${f(C * 0.02)} ${f(h * 0.6)},${f(C * 0.14)} ${f(h)},${f(C * 0.26)}`;
    } else {
        // răng cửa: bờ cắn gần như thẳng, góc gần vuông hơn góc xa
        startY = C * 0.14;
        top = `M${f(-h)},${f(C * 0.14)} Q${f(-h * 0.96)},${f(C * 0.01)} ${f(-h * 0.7)},${f(C * 0.01)} L${f(h * 0.82)},0 Q${f(h)},0 ${f(h)},${f(C * 0.1)}`;
    }
    return `${top} C${f(h * 1.04)},${f(bulgeY + C * 0.1)} ${f(neck * 1.08)},${f(C * 0.82)} ${f(neck)},${f(C)}`
        + ` L${f(-neck)},${f(C)} C${f(-neck * 1.08)},${f(C * 0.82)} ${f(-h * 1.04)},${f(bulgeY + C * 0.1)} ${f(-h)},${f(startY)} Z`;
}

/** Đường bao chân răng + vị trí ống tủy / chóp răng. */
function rootGeometry(info) {
    const { w, C, R, kind, roots } = info;
    const h = w / 2;
    const neck = h * (kind === "molar" ? 0.78 : kind === "incisor" ? 0.7 : 0.66);
    const apexY = C + R;
    const tilt = -w * 0.06; // chân răng hơi nghiêng về phía xa
    const canals = [];
    const apexes = [];
    let path;
    let back = "";
    if (roots === 1) {
        const ax = tilt;
        path = `M${f(-neck)},${f(C - 1)} C${f(-neck * 0.95)},${f(C + R * 0.45)} ${f(ax - neck * 0.32)},${f(apexY - 4)} ${f(ax)},${f(apexY)}`
            + ` C${f(ax + neck * 0.32)},${f(apexY - 4)} ${f(neck * 0.95)},${f(C + R * 0.45)} ${f(neck)},${f(C - 1)} Z`;
        canals.push(`M0,${f(C * 0.55)} Q${f(tilt * 0.3)},${f(C + R * 0.5)} ${f(ax)},${f(apexY - 3)}`);
        apexes.push([ax, apexY]);
    } else {
        // 2 chân: chân xa (trái) và chân gần (phải) – nhìn từ phía má
        const spread = info.primary ? 1.25 : kind === "premolar" ? 0.55 : 1.0;
        const furY = C + R * (kind === "premolar" ? 0.55 : info.primary ? 0.18 : 0.3);
        const rw = neck * (kind === "premolar" ? 0.6 : 0.62);
        const dx = -neck * 0.55 * spread + tilt;
        const mx = neck * 0.55 * spread + tilt * 0.5;
        const dApex = apexY - (kind === "premolar" ? 0 : 3);
        path = `M${f(-neck)},${f(C - 1)}`
            + ` C${f(-neck * 1.02)},${f(C + R * 0.35)} ${f(dx - rw * 0.5)},${f(dApex - R * 0.25)} ${f(dx)},${f(dApex)}`
            + ` C${f(dx + rw * 0.45)},${f(dApex - R * 0.2)} ${f(-rw * 0.25)},${f(furY + 4)} 0,${f(furY)}`
            + ` C${f(rw * 0.25)},${f(furY + 4)} ${f(mx - rw * 0.45)},${f(apexY - R * 0.2)} ${f(mx)},${f(apexY)}`
            + ` C${f(mx + rw * 0.5)},${f(apexY - R * 0.25)} ${f(neck * 1.02)},${f(C + R * 0.35)} ${f(neck)},${f(C - 1)} Z`;
        canals.push(`M${f(-neck * 0.25)},${f(C * 0.6)} Q${f(dx * 0.7)},${f(furY)} ${f(dx)},${f(dApex - 3)}`);
        canals.push(`M${f(neck * 0.25)},${f(C * 0.6)} Q${f(mx * 0.7)},${f(furY)} ${f(mx)},${f(apexY - 3)}`);
        apexes.push([dx, dApex], [mx, apexY]);
        if (roots === 3) {
            // chân trong (khẩu cái) nằm phía sau, nhìn thấy mờ ở giữa và dài hơn
            const px = tilt * 0.3;
            const pApex = apexY + 3;
            back = `M${f(-neck * 0.5)},${f(C)} C${f(-neck * 0.5)},${f(C + R * 0.5)} ${f(px - 5)},${f(pApex - 3)} ${f(px)},${f(pApex)}`
                + ` C${f(px + 5)},${f(pApex - 3)} ${f(neck * 0.5)},${f(C + R * 0.5)} ${f(neck * 0.5)},${f(C)} Z`;
            canals.push(`M0,${f(C * 0.6)} L${f(px)},${f(pApex - 4)}`);
            apexes.push([px, pApex]);
        }
    }
    const pulp = `M${f(-neck * 0.42)},${f(C * 0.92)} Q${f(-neck * 0.5)},${f(C * 0.42)} ${f(-neck * 0.18)},${f(C * 0.38)}`
        + ` L${f(neck * 0.18)},${f(C * 0.38)} Q${f(neck * 0.5)},${f(C * 0.42)} ${f(neck * 0.42)},${f(C * 0.92)} Z`;
    return { path, back, canals, apexes, pulp, neck };
}

/** Vùng mặt răng trên thân răng nhìn từ phía má: dải nhai/rìa cắn, dải gần, dải xa, mặt ngoài ở giữa. */
function sideRegions(info) {
    const { w, C } = info;
    const W = w / 2 + 4;
    const ix = w * 0.27;
    const iy = C * (info.anterior ? 0.2 : 0.27);
    const bottom = C + 2;
    return [
        { slot: "edge", surface: centerSurface(info), points: poly([[-W, -6], [W, -6], [ix, iy], [-ix, iy]]) },
        { slot: "right", surface: "M", points: poly([[W, -6], [W, bottom], [ix, bottom], [ix, iy]]) },
        { slot: "left", surface: "D", points: poly([[-W, -6], [-ix, iy], [-ix, bottom], [-W, bottom]]) },
        { slot: "face", surface: "B", points: poly([[-ix, iy], [ix, iy], [ix, bottom], [-ix, bottom]]) },
    ];
}

export function sideGeometry(info) {
    const root = rootGeometry(info);
    // implant: thân trụ ren thay cho chân răng
    const iw = Math.max(7, info.w * 0.22);
    const implant = {
        body: `M${f(-iw / 2)},${f(info.C + 1)} L${f(iw / 2)},${f(info.C + 1)} L${f(iw * 0.38)},${f(info.C + info.R * 0.86)}`
            + ` Q0,${f(info.C + info.R * 0.98)} ${f(-iw * 0.38)},${f(info.C + info.R * 0.86)} Z`,
        threads: [0.18, 0.32, 0.46, 0.6, 0.74].map((t) => {
            const y = info.C + info.R * t;
            const half = iw / 2 - t * iw * 0.14 + 2;
            return `M${f(-half)},${f(y)} L${f(half)},${f(y + 2.5)}`;
        }),
    };
    return {
        crown: crownPath(info),
        regions: sideRegions(info),
        root,
        implant,
        cej: info.C,
        height: info.C + info.R + (info.roots === 3 ? 3 : 0),
    };
}

// ------------------------------------------------------------------ chart findings → visual flags
/**
 * Gom các ghi nhận còn hiệu lực của 1 răng thành cờ hiển thị.
 * Ghi nhận mới hơn ghi đè ghi nhận cũ trên cùng mặt.
 */
export function toothVisual(entries) {
    const v = {
        surfaces: {}, planSurfaces: {}, missing: null, crown: null, bridge: null, implant: null, canal: null, pulp: null,
        apex: null, residual: null, calculus: null, unerupted: null, mobility: null, other: [],
    };
    const style = (e) => ({ color: e.color || "#E5484D", planned: e.layer === "planned", done: e.layer === "done",
                            name: e.condition, id: e.id });
    for (const e of entries) {
        const code = e.condition_code || "";
        const st = style(e);
        switch (e.symbol) {
            case "fill": {
                const list = e.surfaces && e.surfaces.length ? e.surfaces : ["M", "D", "O", "I", "B", "L"];
                const target = st.planned ? v.planSurfaces : v.surfaces;
                for (const s of list) {
                    target[s] = st;
                }
                break;
            }
            case "cross":
                v.missing = st;
                break;
            case "ring":
                if (code === "mobility") {
                    v.mobility = st;
                } else if (code === "bridge") {
                    v.bridge = st;
                    v.crown = st;
                } else {
                    v.crown = st;
                }
                break;
            case "implant":
                v.implant = st;
                break;
            case "root":
                if (code === "periapical") {
                    v.apex = st;
                } else if (code === "pulpitis") {
                    v.pulp = st;
                } else if (code === "residual_root") {
                    v.residual = st;
                } else {
                    v.canal = st;
                }
                break;
            case "dash":
                if (code === "impacted" || code === "unerupted") {
                    v.unerupted = st;
                } else {
                    v.calculus = st;
                }
                break;
            default:
                v.other.push(st);
        }
    }
    if (v.missing && !v.missing.planned) {
        // mất răng thật: bỏ các dấu cũ trên thân/chân răng (trừ implant thay thế)
        v.surfaces = {};
        v.planSurfaces = {};
        v.crown = v.implant ? v.crown : null;
    }
    return v;
}

export function hatchId(prefix, color) {
    return `${prefix}-h-${String(color || "").replace(/[^0-9a-zA-Z]/g, "")}`;
}
