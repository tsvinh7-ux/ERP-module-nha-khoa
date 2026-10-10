/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { formatMoney } from "../js/utils";

/**
 * Chế độ tư vấn – màn hình quay về phía bệnh nhân.
 * Bước 1: cho xem tận mắt (sơ đồ/ảnh) · Bước 2: các phương án đặt cạnh nhau để bệnh nhân tự chọn.
 */
export class ConsultMode extends Component {
    static template = "dmag_clinic_workspace.ConsultMode";
    static props = { plan: Object, patient: Object, onClose: Function };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = useState({ confirming: null, changed: false });
        this.formatMoney = formatMoney;
    }

    get blocked() {
        const plan = this.props.plan;
        return plan.second_opinion_required && !plan.second_opinion_by;
    }

    async markPresented() {
        if (this.props.plan.state === "draft") {
            await this.orm.call("dmag.treatment.plan", "action_present", [[this.props.plan.id]]);
            this.state.changed = true;
        }
    }

    async choose(option) {
        await this.markPresented();
        await this.orm.call("dmag.treatment.option", "action_accept", [[option.id]]);
        this.notification.add(`Bệnh nhân đã chọn ${option.name}. Hợp đồng điều trị đã được lập.`, { type: "success" });
        this.props.onClose(true);
    }

    async print() {
        await this.markPresented();
        await this.action.doAction("dmag_dental_clinic.action_report_treatment_plan", {
            additionalContext: { active_ids: [this.props.plan.id], active_model: "dmag.treatment.plan" },
        });
    }

    close() {
        this.props.onClose(this.state.changed);
    }
}
