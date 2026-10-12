/** @odoo-module **/

import { Component } from "@odoo/owl";

export function formatVnd(v) {
    return Math.round(v || 0).toLocaleString("vi-VN") + " đ";
}

/** Huy hiệu nhỏ cho mọi kết quả AI: Giả lập / Claude / Tại chỗ + chi phí (ước tính). */
export class AiBadge extends Component {
    static template = "dmag_ai_customer.AiBadge";
    static props = {
        mode: { type: String, optional: true }, // simulate | live | local
        cost: { type: Number, optional: true },
        estimated: { type: Number, optional: true },
        label: { type: String, optional: true },
        title: { type: String, optional: true },
    };

    get text() {
        if (this.props.mode === "local") {
            return this.props.label || "AI tại chỗ";
        }
        const base = this.props.mode === "live" ? "Claude" : "Giả lập";
        if (this.props.mode === "live" && this.props.cost) {
            return `${base} · ${formatVnd(this.props.cost)}`;
        }
        if (this.props.estimated) {
            return `${base} · ~${formatVnd(this.props.estimated)}`;
        }
        return base;
    }

    get tooltip() {
        if (this.props.title) {
            return this.props.title;
        }
        if (this.props.mode === "local") {
            return "Chạy tại máy chủ phòng khám, không gửi dữ liệu ra ngoài, không tốn phí.";
        }
        if (this.props.mode === "live") {
            return "Claude API (Anthropic) – dữ liệu bệnh nhân đã ẩn danh trước khi gửi. Chi phí thật theo token.";
        }
        return "Chế độ giả lập: kết quả dựng từ dữ liệu thật của Odoo, không gọi AI thật, không tốn phí. Số tiền là chi phí ước tính nếu chạy Claude.";
    }
}

export const TOOL_LABELS = {
    search_services: { icon: "fa-tags", label: "Tra bảng giá dịch vụ" },
    get_free_slots: { icon: "fa-calendar-check-o", label: "Xem giờ trống (đã xếp hạng AI-11)" },
    find_patient_by_phone: { icon: "fa-id-card-o", label: "Tìm hồ sơ theo SĐT" },
    book_appointment: { icon: "fa-calendar-plus-o", label: "Giữ chỗ lịch hẹn (nháp)" },
    get_clinic_info: { icon: "fa-info-circle", label: "Thông tin phòng khám" },
    search_knowledge: { icon: "fa-book", label: "Tra kho tri thức đã duyệt" },
    handoff_to_staff: { icon: "fa-user-circle", label: "Chuyển nhân viên" },
};

/** Tóm tắt kết quả một lần gọi công cụ cho giao diện. */
export function summarizeTool(step) {
    const out = step.output || {};
    if (out.error) {
        return { kind: "error", text: out.error };
    }
    switch (step.tool) {
        case "search_services":
            return { kind: "list", items: (out.services || []).map((s) => `${s.name} – ${s.price_text}`) };
        case "get_free_slots":
            return {
                kind: "chips",
                text: `${out.weekday || ""} ${out.date || ""} · ${out.duration_min || 30} phút`,
                items: (out.slots || []).map((s) => s.time + (s.doctor ? ` · ${s.doctor}` : "")),
            };
        case "find_patient_by_phone":
            return { kind: "text", text: out.found ? `Đã có hồ sơ – chào "${out.salutation} ${out.greeting_name}"` : "Chưa có hồ sơ – sẽ tạo mới khi đặt lịch" };
        case "book_appointment":
            return out.booked
                ? { kind: "booking", text: `${out.visit} · ${out.time} ${out.date} · ${out.patient}${out.doctor ? " · BS " + out.doctor : ""}`, visitId: out.visit_id }
                : { kind: "error", text: out.message || "Không đặt được" };
        case "search_knowledge":
            return (out.results || []).length
                ? { kind: "list", items: out.results.map((r) => `${r.source || r.title}${r.score ? " · " + Math.round(r.score * 100) + "%" : ""}${r.title && r.source !== r.title ? " – " + r.title : ""}`) }
                : { kind: "error", text: "Không có mục nào đủ khớp trong dữ liệu đã nạp" };
        case "get_clinic_info":
            return { kind: "list", items: Object.entries(out).filter(([k]) => k !== "clinic").map(([k, v]) => v) };
        case "handoff_to_staff":
            return { kind: "alert", text: `Đã chuyển nhân viên (${(step.input || {}).reason || ""})` };
        default:
            return { kind: "text", text: JSON.stringify(out).slice(0, 200) };
    }
}
