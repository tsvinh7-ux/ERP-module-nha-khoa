/** @odoo-module **/

import { onWillStart, useState } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { DoctorDesk } from "@dmag_clinic_workspace/doctor_desk/doctor_desk";
import { AiDictation } from "./ai_dictation";
import { AiPlanSuggest } from "./ai_plan_suggest";
import { AiRecordCheckDialog } from "./ai_record_check";
import { AiSummaryCard } from "./ai_summary_card";
import { AiXrayDialog } from "./ai_xray";
import { aiCall, aiFeatureOn, loadAiStatus } from "./ai_utils";

DoctorDesk.components = { ...DoctorDesk.components, AiDictation, AiPlanSuggest, AiSummaryCard };

/**
 * Gắn trợ lý AI vào Bàn làm việc bác sĩ (không sửa file của dmag_clinic_workspace):
 * AI-04 thẻ tóm tắt, AI-01/AI-02 trong tab Bệnh án, AI-02 trước khi ký, AI-05 trong tab Kế hoạch, AI-06 trên sơ đồ.
 */
patch(DoctorDesk.prototype, {
    setup() {
        super.setup(...arguments);
        this.dialogService = useService("dialog");
        this.ai = useState({ status: null, plan: null, planLoading: false, planConsent: null, xrayTeeth: [] });
        onWillStart(async () => {
            this.ai.status = await loadAiStatus(this.orm);
        });
    },

    aiOn(code) {
        return aiFeatureOn(this.ai.status, code);
    },

    get aiHighlight() {
        return this.ai.xrayTeeth;
    },

    async openVisit(visitId) {
        this.ai.plan = null;
        this.ai.planConsent = null;
        this.ai.xrayTeeth = [];
        return super.openVisit(visitId);
    },

    /** AI-02: bấm "Ký bệnh án" → kiểm tra trước; bác sĩ vẫn có thể ký. */
    async visitAction(method) {
        if (method === "action_sign_record" && this.aiOn("AI-02")) {
            this.dialogService.add(AiRecordCheckDialog, {
                visitId: this.visit.id,
                signMode: true,
                onSign: () => super.visitAction(method),
                onChanged: () => this.reloadVisit(),
            });
            return;
        }
        return super.visitAction(method);
    },

    aiCheckRecord() {
        this.dialogService.add(AiRecordCheckDialog, {
            visitId: this.visit.id,
            signMode: false,
            onChanged: () => this.reloadVisit(),
        });
    },

    async aiReloadAfterApply() {
        await this.reloadVisit();
    },

    // ---------------------------------------------------------------- AI-05
    async aiSuggestPlan() {
        this.state.tab = "plan";
        this.ai.planLoading = true;
        this.ai.planConsent = null;
        this.ai.plan = null;
        const res = await aiCall(this.orm, this.notification, "ai05_suggest", [this.visit.id]);
        this.ai.planLoading = false;
        if (!res) {
            this.ai.plan = null;
            return;
        }
        if (res.consent_required) {
            this.ai.planConsent = res;
            this.ai.plan = { consent: true };
            return;
        }
        this.ai.plan = res;
    },

    aiClosePlan() {
        this.ai.plan = null;
        this.ai.planConsent = null;
        this.ai.planLoading = false;
    },

    /** Điền khung lập kế hoạch có sẵn: cột A = Tối ưu, cột B = Cơ bản. Chưa lưu gì. */
    aiUsePlan(result) {
        const optimal = result.options.find((o) => o.tier === "optimal");
        const basic = result.options.find((o) => o.tier === "basic");
        const groups = new Map();
        for (const [which, option] of [["A", optimal], ["B", basic]]) {
            for (const line of option ? option.lines : []) {
                const key = line.teeth.join(",") || "_";
                if (!groups.has(key)) {
                    groups.set(key, { teeth: line.teeth, A: [], B: [] });
                }
                groups.get(key)[which].push(line);
            }
        }
        const lines = [];
        let i = 0;
        for (const group of groups.values()) {
            const n = Math.max(group.A.length, group.B.length);
            for (let j = 0; j < n; j++) {
                const a = group.A[j];
                const b = group.B[j];
                const ref = a || b;
                const findingIds = result.findings.filter((f) => group.teeth.includes(f.tooth)).map((f) => f.id);
                lines.push({
                    key: `ai${i++}`,
                    finding_ids: j === 0 ? findingIds : [],
                    teeth: group.teeth,
                    surfaces: [],
                    label: group.teeth.length ? `R${group.teeth.join(", ")} · ${ref.reason}` : ref.reason,
                    productA: a ? a.product_id : false,
                    productB: b ? b.product_id : false,
                    phase: ref.phase,
                });
            }
        }
        lines.sort((x, y) => x.phase - y.phase);
        this.state.builder = {
            title: "Kế hoạch theo gợi ý AI – bác sĩ duyệt",
            nameA: "Phương án A – Tối ưu",
            nameB: "Phương án B – Cơ bản",
            summaryA: [optimal && optimal.summary, result.patient_explanation && `Giải thích: ${result.patient_explanation}`]
                .filter(Boolean)
                .join("\n"),
            summaryB: basic ? basic.summary : "",
            installmentA: 0,
            installmentB: 0,
            useB: Boolean(basic && basic.lines.length),
            lines,
        };
        this.ai.plan = null;
        this.state.tab = "plan";
        this.notification.add("Đã điền gợi ý vào khung lập kế hoạch. Kiểm tra, chỉnh sửa rồi bấm \"Lưu kế hoạch\".", {
            type: "info",
        });
    },

    // ---------------------------------------------------------------- AI-06
    aiOpenXray() {
        this.dialogService.add(AiXrayDialog, {
            visitId: this.visit.id,
            chart: this.state.ws.chart,
            dentition: this.state.dentition,
            locked: this.locked,
            onHighlight: (teeth) => (this.ai.xrayTeeth = teeth),
            onChartChanged: () => this.reloadVisit(),
            onSelectTooth: (tooth) => {
                this.state.tab = "chart";
                this.state.selection = { teeth: { [tooth]: [] } };
                this.state.zoomTooth = tooth;
            },
        });
    },
});
