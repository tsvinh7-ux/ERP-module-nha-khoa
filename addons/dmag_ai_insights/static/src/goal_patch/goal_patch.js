/** @odoo-module **/

import { onWillStart, useState } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { GoalDashboard } from "@dmag_dental_goals/goal_dashboard/goal_dashboard";
import { AiQaChat } from "../qa/qa_chat";
import { AiForecastChart } from "../forecast/forecast_chart";
import { money, pct } from "../common/ai_utils";

GoalDashboard.components = { ...(GoalDashboard.components || {}), AiQaChat, AiForecastChart };

/** Dải AI trên Bảng điều hành mục tiêu: dự báo (AI-16), bản tin (AI-14), bất thường (AI-15), hỏi đáp (AI-13). */
patch(GoalDashboard.prototype, {
    setup() {
        super.setup(...arguments);
        const ctx = (this.props.action && this.props.action.context) || {};
        this.ai = useState({ panel: null, chat: !!ctx.dmag_ai_open_chat, question: "" });
        this.aiMoney = money;
        this.aiPct = pct;
        onWillStart(async () => {
            try {
                this.ai.panel = await this.orm.call("dmag.ai.hub", "get_goal_panel", []);
            } catch {
                this.ai.panel = null;
            }
        });
    },
    toggleAiChat(question) {
        this.ai.question = typeof question === "string" ? question : "";
        this.ai.chat = !this.ai.chat;
    },
    /** Câu hỏi gợi ý theo chỉ tiêu đang lệch nhất của kỳ đang xem. */
    get aiQuestions() {
        const d = this.state.data;
        const qs = [];
        const period = d && d.period.type === "quarter" ? "quý này" : d && d.period.type === "year" ? "năm nay" : "tháng này";
        const bad = d ? [...d.north_star, ...d.service].filter((c) => ["at_risk", "behind"].includes(c.status)) : [];
        if (bad.length) {
            qs.push(`Vì sao ${bad[0].label.toLowerCase()} ${period} ${bad[0].direction === "lower" ? "cao" : "thấp"}?`);
        } else {
            qs.push(`Vì sao doanh thu ${period} chậm?`);
        }
        qs.push(`Bác sĩ nào có doanh thu cao nhất ${period}?`);
        return qs;
    },
    openAiAction(xmlid) {
        this.action.doAction(xmlid);
    },
    openAiBrief() {
        const b = this.ai.panel && this.ai.panel.brief;
        if (b) {
            this.action.doAction("dmag_ai_insights.action_dmag_ai_brief_screen");
        }
    },
});
