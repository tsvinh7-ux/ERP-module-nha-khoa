/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { FrontDesk } from "@dmag_clinic_workspace/frontdesk/frontdesk";

/** AI-08 huy hiệu nguy cơ không đến + nhãn "Zalo AI" + nút soạn nội dung chăm sóc (AI-12) trên bảng điều phối. */
patch(FrontDesk.prototype, {
    noshowTooltip(visit) {
        const n = visit.noshow;
        if (!n) {
            return "";
        }
        return [
            `Dự báo không đến: ${n.risk}% (${n.level === "high" ? "cao" : n.level === "medium" ? "trung bình" : "thấp"})`,
            n.factors ? `Vì sao: ${n.factors}` : "",
            `Gợi ý: ${n.suggestion}`,
            "",
            `Cách tính (AI-08): ${n.method}`,
        ].filter((x) => x !== null).join("\n");
    },

    async aiCare(visit) {
        const action = await this.orm.call("dmag.dental.visit", "action_dmag_ai_care_draft", [[visit.id]]);
        return this.action.doAction(action);
    },
});
