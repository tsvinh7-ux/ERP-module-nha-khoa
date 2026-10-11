/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { AiConsent, AiMeta, aiCall } from "./ai_utils";

const ICONS = {
    safety: "fa-exclamation-triangle",
    history: "fa-heartbeat",
    visits: "fa-history",
    plan: "fa-list-ol",
    balance: "fa-money",
    care: "fa-commenting-o",
};

/**
 * AI-04 – Tóm tắt hồ sơ 30 giây (thẻ thu gọn được, đặt ngay dưới thẻ bệnh nhân).
 * Chế độ giả lập: tự tạo khi mở bệnh nhân (miễn phí); chế độ Claude: bấm "Tóm tắt" mới gọi (tốn phí).
 */
export class AiSummaryCard extends Component {
    static template = "dmag_ai_clinical.AiSummaryCard";
    static components = { AiMeta, AiConsent };
    static props = { visitId: Number, mode: { type: String, optional: true } };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        let open = true;
        try {
            open = window.localStorage.getItem("dmag_ai_summary_open") !== "0";
        } catch {
            open = true;
        }
        this.state = useState({ open, loading: false, data: null, consent: null });
        this.ICONS = ICONS;
        onWillStart(() => {
            if (this.props.mode === "simulate") {
                this.load();
            }
        });
    }

    toggle() {
        this.state.open = !this.state.open;
        try {
            window.localStorage.setItem("dmag_ai_summary_open", this.state.open ? "1" : "0");
        } catch {
            // trình duyệt chặn lưu trữ – bỏ qua
        }
        if (this.state.open && !this.state.data && !this.state.loading && !this.state.consent) {
            this.load();
        }
    }

    async load() {
        this.state.loading = true;
        this.state.consent = null;
        const res = await aiCall(this.orm, this.notification, "ai04_summary", [this.props.visitId]);
        this.state.loading = false;
        if (!res) {
            return;
        }
        if (res.consent_required) {
            this.state.consent = res;
            return;
        }
        this.state.data = res;
        this.state.open = true;
    }
}
