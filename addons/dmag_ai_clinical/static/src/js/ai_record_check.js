/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { useService } from "@web/core/utils/hooks";
import { AiConsent, AiMeta, aiCall } from "./ai_utils";

const SEVERITY = {
    high: { label: "Cần sửa", icon: "fa-times-circle" },
    medium: { label: "Nên bổ sung", icon: "fa-exclamation-triangle" },
    low: { label: "Gợi ý", icon: "fa-lightbulb-o" },
};

/**
 * AI-02 – Kiểm tra bệnh án trước khi ký: quy tắc cố định (mục bắt buộc, sơ đồ ↔ ICD-10) + AI đối chiếu
 * + gợi ý mã ICD-10 chỉ trong danh mục. Bác sĩ vẫn quyết định ký.
 */
export class AiRecordCheckDialog extends Component {
    static template = "dmag_ai_clinical.AiRecordCheckDialog";
    static components = { Dialog, AiMeta, AiConsent };
    static props = {
        visitId: Number,
        signMode: { type: Boolean, optional: true },
        onSign: { type: Function, optional: true },
        onChanged: { type: Function, optional: true },
        close: Function,
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.SEVERITY = SEVERITY;
        this.state = useState({ loading: true, data: null, added: {}, signing: false });
        onWillStart(() => this.load());
    }

    async load() {
        this.state.loading = true;
        this.state.data = await aiCall(this.orm, this.notification, "ai02_check", [this.props.visitId]);
        this.state.loading = false;
    }

    get issues() {
        const d = this.state.data;
        if (!d) {
            return [];
        }
        const all = [...d.local, ...(d.ai ? d.ai.issues : [])];
        const order = { high: 0, medium: 1, low: 2 };
        return all.sort((a, b) => (order[a.severity] ?? 3) - (order[b.severity] ?? 3));
    }

    get counts() {
        const c = { high: 0, medium: 0, low: 0 };
        for (const i of this.issues) {
            c[i.severity] = (c[i.severity] || 0) + 1;
        }
        return c;
    }

    async addDiagnosis(d) {
        const ok = await aiCall(this.orm, this.notification, "ai02_add_diagnosis", [this.props.visitId, d.id]);
        if (ok) {
            this.state.added[d.id] = true;
            this.notification.add(`Đã thêm ${d.code} vào chẩn đoán.`, { type: "success" });
            if (this.props.onChanged) {
                await this.props.onChanged();
            }
        }
    }

    async recheck() {
        this.state.added = {};
        await this.load();
    }

    async sign() {
        this.state.signing = true;
        const onSign = this.props.onSign;
        this.props.close();
        await onSign();
    }
}
