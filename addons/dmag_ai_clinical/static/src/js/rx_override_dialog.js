/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";

const MIN_REASON = 15;

/**
 * AI-03 – Giám đốc "Duyệt vượt & ký chịu trách nhiệm": danh sách quy tắc bị vượt + lý do bắt buộc + xác nhận ký bổ sung.
 * Máy chủ kiểm tra lại quyền Giám đốc, độ dài lý do và đúng tập vi phạm (dmag.prescription.action_director_override).
 */
export class RxOverrideDialog extends Component {
    static template = "dmag_ai_clinical.RxOverrideDialog";
    static components = { Dialog };
    static props = {
        close: Function,
        blocks: Array,
        patient: { type: String, optional: true },
        doctor: { type: String, optional: true },
        onConfirm: Function,
    };

    setup() {
        this.MIN_REASON = MIN_REASON;
        this.state = useState({ reason: "", confirm: false, saving: false, error: "" });
    }

    get canSubmit() {
        return this.state.reason.trim().length >= MIN_REASON && this.state.confirm && !this.state.saving;
    }

    async submit() {
        if (!this.canSubmit) {
            return;
        }
        this.state.saving = true;
        this.state.error = "";
        try {
            await this.props.onConfirm(this.state.reason.trim(), this.state.confirm);
            this.props.close();
        } catch (e) {
            this.state.error = (e && e.data && e.data.message) || (e && e.message) || String(e);
        } finally {
            this.state.saving = false;
        }
    }
}
