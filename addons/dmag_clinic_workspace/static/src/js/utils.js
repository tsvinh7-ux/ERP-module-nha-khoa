/** @odoo-module **/

import { deserializeDateTime } from "@web/core/l10n/dates";

const moneyFormatter = new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 0 });

export function formatMoney(value) {
    return `${moneyFormatter.format(Math.round(value || 0))} ₫`;
}

export function formatTime(value) {
    return value ? deserializeDateTime(value).toFormat("HH:mm") : "";
}

export function formatDate(value) {
    return value ? deserializeDateTime(value).toFormat("dd/MM/yyyy") : "";
}

export function minutesSince(value) {
    if (!value) {
        return 0;
    }
    const diff = Date.now() - deserializeDateTime(value).toMillis();
    return Math.max(0, Math.floor(diff / 60000));
}

export function formatDuration(minutes) {
    if (minutes < 60) {
        return `${minutes}′`;
    }
    const h = Math.floor(minutes / 60);
    const m = minutes % 60;
    return m ? `${h}g${String(m).padStart(2, "0")}′` : `${h}g`;
}

export const VISIT_STATES = {
    draft: { label: "Đã đặt lịch", tone: "muted" },
    confirmed: { label: "Đã xác nhận", tone: "info" },
    arrived: { label: "Đang chờ", tone: "warning" },
    in_chair: { label: "Đang điều trị", tone: "primary" },
    done: { label: "Hoàn tất", tone: "success" },
    cancel: { label: "Đã hủy", tone: "muted" },
    no_show: { label: "Không đến", tone: "muted" },
};

export const PAYMENT_STATES = {
    none: "Không phát sinh",
    to_invoice: "Chờ lập hóa đơn",
    to_pay: "Chờ thanh toán",
    paid: "Đã thanh toán",
};

export const PLAN_STATES = {
    draft: "Đang soạn",
    presented: "Đã tư vấn",
    accepted: "Đồng ý",
    in_progress: "Đang điều trị",
    done: "Hoàn thành",
    cancel: "Từ chối",
};
