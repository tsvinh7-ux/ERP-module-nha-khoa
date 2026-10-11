/** @odoo-module **/

import { onWillStart, useState } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { RxPanel } from "@dmag_clinic_workspace/doctor_desk/rx_panel";
import { useService } from "@web/core/utils/hooks";
import { AiMeta, AiConsent, aiCall, aiFeatureOn, loadAiStatus } from "./ai_utils";
import { RxOverrideDialog } from "./rx_override_dialog";

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
                               ack: false, pending: false, blockedAttempt: false, requesting: false });
        this.dialogService = useService("dialog");
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
        const rxId = (this.state.draft && this.state.draft.id) || false;
        const res = await aiCall(this.orm, this.notification, "rx_check", [this.props.visitId, lines, weight, rxId]);
        this.aiRx.check = res;
        return res;
    },

    _aiRxChanged() {
        this.aiRx.blockedAttempt = false;
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
        if (res && res.blocks && !res.override_valid) {
            this.aiRx.blockedAttempt = true;
            this.notification.add(
                res.is_director
                    ? "Đơn thuốc vi phạm quy tắc an toàn – sửa đơn, hoặc bấm “Duyệt vượt & ký chịu trách nhiệm”."
                    : "Đơn thuốc vi phạm quy tắc an toàn (xem mục CHẶN) – sửa đơn, hoặc “Đề nghị Giám đốc duyệt vượt”.",
                { type: "danger", title: "An toàn đơn thuốc" }
            );
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

    get aiRxBlocks() {
        return ((this.aiRx.check && this.aiRx.check.findings) || []).filter((f) => f.level === "block");
    },

    /** Bác sĩ: lưu nháp rồi đề nghị Giám đốc duyệt vượt (tạo việc cần làm cho Giám đốc). */
    async aiRxRequestOverride() {
        this.aiRx.requesting = true;
        try {
            const saved = await this.save();
            const res = await aiCall(this.orm, this.notification, "rx_request_override", [this.props.visitId, saved.id, ""]);
            if (res) {
                this.notification.add(
                    `Đã gửi đề nghị duyệt vượt tới ${res.directors.join(", ") || "Giám đốc"} – đơn giữ ở trạng thái nháp.`,
                    { type: "success" }
                );
                await this.aiRxCheck();
            }
        } finally {
            this.aiRx.requesting = false;
        }
    },

    /** Giám đốc: hộp thoại "Duyệt vượt & ký chịu trách nhiệm" → ghi vết + ký số + phát hành. */
    aiRxOpenOverride() {
        this.dialogService.add(RxOverrideDialog, {
            blocks: this.aiRxBlocks,
            patient: (this.aiRx.check && this.aiRx.check.patient) || "",
            doctor: (this.aiRx.check && this.aiRx.check.doctor) || "",
            onConfirm: async (reason, confirm) => {
                const saved = await this.save();
                const res = await this.orm.call("dmag.ai.clinical", "rx_override", [this.props.visitId, saved.id, reason, confirm, true]);
                if (!res.issued) {
                    this.notification.add(
                        `Đã duyệt vượt (ký số: ${(res.esign && res.esign.label) || "—"}). Chưa phát hành vì: ${(res.issue_errors || []).join("; ")} – bổ sung rồi bấm “Phát hành”.`,
                        { type: "warning", title: "Duyệt vượt an toàn đơn thuốc", sticky: true }
                    );
                    this.aiRx.blockedAttempt = false;
                    await this.aiRxCheck();
                    return;
                }
                this.state.result = res;
                this.state.draft = null;
                this.aiRx.check = null;
                this.aiRx.explain = null;
                this.aiRx.blockedAttempt = false;
                this.notification.add(
                    `Đã duyệt vượt và phát hành đơn ${res.code || ""}. Ký số: ${(res.esign && res.esign.label) || "—"}`,
                    { type: "warning", title: "Duyệt vượt an toàn đơn thuốc" }
                );
                await this.props.onChanged();
            },
        });
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
