/** @odoo-module **/

import { onWillStart, useState } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { RxPanel } from "@dmag_clinic_workspace/doctor_desk/rx_panel";
import { AiMeta, AiConsent, aiCall, aiFeatureOn, loadAiStatus } from "./ai_utils";

RxPanel.components = { ...(RxPanel.components || {}), AiMeta, AiConsent };

const LEVELS = {
    block: { label: "CHẶN", icon: "fa-ban" },
    warn: { label: "Cảnh báo", icon: "fa-exclamation-triangle" },
    info: { label: "Lưu ý", icon: "fa-info-circle" },
};

/**
 * AI-03 – An toàn đơn thuốc trong RxPanel:
 * quy tắc CỐ ĐỊNH chạy mỗi khi thêm / bỏ thuốc và trước khi phát hành (chặn dị ứng, chống chỉ định, >30 ngày;
 * cảnh báo cần xác nhận) – kể cả khi AI tắt; AI chỉ "giải thích dễ hiểu" khi bác sĩ bấm.
 */
patch(RxPanel.prototype, {
    setup() {
        super.setup(...arguments);
        this.RX_LEVELS = LEVELS;
        this.aiRx = useState({ status: null, check: null, explain: null, meta: null, consent: null, explaining: false,
                               ack: false, pending: false });
        onWillStart(async () => {
            this.aiRx.status = await loadAiStatus(this.orm);
        });
    },

    get aiRxExplainOn() {
        return aiFeatureOn(this.aiRx.status, "AI-03");
    },

    _aiRxLines() {
        return ((this.state.draft && this.state.draft.lines) || []).map((l) => ({
            drug_id: l.drug_id,
            days: Number(l.days) || 0,
            dose_per_time: Number(l.dose_per_time) || 0,
            times_per_day: Number(l.times_per_day) || 0,
        }));
    },

    async aiRxCheck() {
        const lines = this._aiRxLines();
        if (!lines.length) {
            this.aiRx.check = null;
            return null;
        }
        const weight = (this.state.draft && Number(this.state.draft.weight)) || 0;
        const res = await aiCall(this.orm, this.notification, "rx_check", [this.props.visitId, lines, weight]);
        this.aiRx.check = res;
        return res;
    },

    _aiRxChanged() {
        this.aiRx.ack = false;
        this.aiRx.pending = false;
        this.aiRx.explain = null;
        this.aiRxCheck();
    },

    addDrug(drug) {
        super.addDrug(drug);
        this._aiRxChanged();
    },

    applyTemplate(t) {
        super.applyTemplate(t);
        this._aiRxChanged();
    },

    removeLine(line) {
        super.removeLine(line);
        this._aiRxChanged();
    },

    editDraft(p) {
        super.editDraft(p);
        if (!this.aiRx.check) {
            this.aiRxCheck();
        }
    },

    async issue() {
        const res = await this.aiRxCheck();
        if (res && res.blocks) {
            this.notification.add("Đơn thuốc vi phạm quy tắc an toàn (xem mục CHẶN) – sửa đơn trước khi phát hành.", {
                type: "danger",
                title: "An toàn đơn thuốc",
            });
            return;
        }
        if (res && res.warns && !this.aiRx.ack) {
            this.aiRx.pending = true;
            this.notification.add("Có cảnh báo an toàn – đọc và xác nhận trước khi phát hành.", { type: "warning" });
            return;
        }
        this.aiRx.ack = false;
        this.aiRx.pending = false;
        await super.issue();
        if (!this.state.draft) {
            this.aiRx.check = null;
            this.aiRx.explain = null;
        }
    },

    async aiRxConfirmIssue() {
        this.aiRx.ack = true;
        await this.issue();
    },

    async aiRxExplain() {
        this.aiRx.explaining = true;
        this.aiRx.consent = null;
        const weight = (this.state.draft && Number(this.state.draft.weight)) || 0;
        const res = await aiCall(this.orm, this.notification, "ai03_explain", [this.props.visitId, this._aiRxLines(), weight]);
        this.aiRx.explaining = false;
        if (!res) {
            return;
        }
        this.aiRx.check = { findings: res.findings, blocks: res.blocks, warns: res.warns, ok: res.ok };
        if (res.consent) {
            this.aiRx.consent = res.consent;
            return;
        }
        this.aiRx.explain = res.explanation;
        this.aiRx.meta = res.meta;
    },
});
