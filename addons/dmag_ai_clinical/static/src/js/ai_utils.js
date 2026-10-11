/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

const vnd = new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 0 });

export function formatVnd(value) {
    return `${vnd.format(Math.round(value || 0))} đ`;
}

/** Lấy thông báo lỗi người dùng (UserError / AccessError) từ lỗi RPC của Odoo. */
export function aiErrorMessage(error) {
    return (error && error.data && error.data.message) || (error && error.message) || String(error);
}

/**
 * Gọi dịch vụ AI lâm sàng; lỗi → toast đỏ với đúng thông báo UserError, trả null.
 */
export async function aiCall(orm, notification, method, args = [], kwargs = {}) {
    try {
        return await orm.call("dmag.ai.clinical", method, args, kwargs);
    } catch (error) {
        notification.add(aiErrorMessage(error), { type: "danger", title: "Trợ lý AI" });
        return null;
    }
}

export async function loadAiStatus(orm, visitId = false) {
    try {
        return await orm.call("dmag.ai.clinical", "get_status", [visitId || false]);
    } catch {
        return null; // không có quyền / chưa cài: ẩn toàn bộ tính năng AI
    }
}

export function aiFeatureOn(status, code) {
    return Boolean(status && status.is_doctor && status.features && status.features[code]);
}

/** Nhãn "AI" + chế độ (Giả lập / Claude) + chi phí của lần gọi. */
export class AiMeta extends Component {
    static template = "dmag_ai_clinical.AiMeta";
    static props = { meta: { type: Object, optional: true }, label: { type: String, optional: true } };

    get mode() {
        const m = this.props.meta;
        if (!m || !m.mode) {
            return null;
        }
        return m.simulated ? "Giả lập" : "Claude";
    }

    get costText() {
        const m = this.props.meta;
        if (!m || !m.mode) {
            return "";
        }
        if (m.simulated) {
            return `≈ ${formatVnd(m.estimated_cost_vnd)} nếu chạy thật`;
        }
        return `Chi phí ${formatVnd(m.cost_vnd)}`;
    }

    get modelText() {
        const m = this.props.meta;
        return m && m.model ? m.model.replace(" (giả lập)", "") : "";
    }
}

/** Bệnh nhân chưa đồng ý AI → thông báo + nút một chạm "Bệnh nhân đồng ý" (ghi nhận có thời điểm). */
export class AiConsent extends Component {
    static template = "dmag_ai_clinical.AiConsent";
    static props = { info: Object, onDone: { type: Function, optional: true } };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({ saving: false });
    }

    async agree() {
        this.state.saving = true;
        const res = await aiCall(this.orm, this.notification, "record_consent", [this.props.info.patient_id]);
        this.state.saving = false;
        if (res) {
            this.notification.add(`Đã ghi nhận ${this.props.info.patient_name} đồng ý hỗ trợ bằng AI.`, { type: "success" });
            if (this.props.onDone) {
                await this.props.onDone();
            }
        }
    }
}
