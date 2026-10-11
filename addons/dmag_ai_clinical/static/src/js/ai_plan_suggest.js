/** @odoo-module **/

import { Component } from "@odoo/owl";
import { AiConsent, AiMeta, formatVnd } from "./ai_utils";

/**
 * AI-05 – 2 phương án (Tối ưu / Cơ bản) từ sơ đồ răng, dịch vụ chỉ trong danh mục, kèm lời giải thích cho khách.
 * "Dùng gợi ý" chỉ điền sẵn khung lập kế hoạch có sẵn – bác sĩ sửa rồi tự bấm "Lưu kế hoạch".
 */
export class AiPlanSuggest extends Component {
    static template = "dmag_ai_clinical.AiPlanSuggest";
    static components = { AiMeta, AiConsent };
    static props = {
        loading: Boolean,
        result: { optional: true },
        consent: { optional: true },
        onUse: Function,
        onClose: Function,
        onRetry: Function,
    };

    setup() {
        this.formatVnd = formatVnd;
    }

    phases(option) {
        const groups = {};
        for (const line of option.lines) {
            (groups[line.phase] = groups[line.phase] || []).push(line);
        }
        return Object.keys(groups)
            .sort((a, b) => a - b)
            .map((p) => ({ phase: p, lines: groups[p] }));
    }
}
