/** @odoo-module **/

import { markup } from "@odoo/owl";

const intFmt = new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 0 });
const dec1Fmt = new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 1 });
const dec2Fmt = new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 2 });

/** Tiền rút gọn kiểu Việt: 1,25 tỷ · 450,5 tr · 85.000 ₫ */
export function money(v) {
    if (v === null || v === undefined || Number.isNaN(v)) {
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

export function num(v, digits = 0) {
    if (v === null || v === undefined) {
        return "–";
    }
    return new Intl.NumberFormat("vi-VN", { maximumFractionDigits: digits }).format(v);
}

export function pct(v) {
    return v === null || v === undefined ? "–" : `${intFmt.format(Math.round(v))}%`;
}

function escapeHtml(text) {
    return String(text || "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
}

/** Markdown tối giản và an toàn (escape trước): **đậm**, dòng "- " → danh sách, xuống dòng. */
export function renderMd(text) {
    const lines = escapeHtml(text).split(/\n/);
    let html = "";
    let inList = false;
    for (let line of lines) {
        line = line.replace(/\*\*(.+?)\*\*/g, "<b>$1</b>");
        const m = line.match(/^\s*(?:[-•]|\d+\.)\s+(.*)$/);
        if (m) {
            if (!inList) {
                html += "<ul>";
                inList = true;
            }
            html += `<li>${m[1]}</li>`;
            continue;
        }
        if (inList) {
            html += "</ul>";
            inList = false;
        }
        if (line.trim()) {
            html += `<p>${line}</p>`;
        }
    }
    if (inList) {
        html += "</ul>";
    }
    return markup(html);
}

export const SEVERITY = {
    high: { label: "Cao", icon: "fa-exclamation-triangle", tone: "bad" },
    medium: { label: "Trung bình", icon: "fa-exclamation-circle", tone: "warn" },
    low: { label: "Thấp", icon: "fa-info-circle", tone: "muted" },
};
