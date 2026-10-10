/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class DmagJourneyDashboard extends Component {
    static template = "dmag_dental_journey.JourneyDashboard";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({ data: null, days: 30, loading: true });
        onWillStart(() => this.load());
    }

    async load() {
        this.state.loading = true;
        const to = new Date();
        const from = new Date(to.getTime() - (this.state.days - 1) * 86400000);
        const fmt = (d) => d.toISOString().slice(0, 10);
        this.state.data = await this.orm.call("dmag.dental.visit", "get_journey_dashboard", [fmt(from), fmt(to)]);
        this.state.loading = false;
    }

    async setDays(days) {
        this.state.days = days;
        await this.load();
    }

    openTasks(filter) {
        this.action.doAction("dmag_dental_journey.action_mail_activity_cskh", {
            additionalContext: { search_default_todo: 0, [`search_default_${filter}`]: 1 },
        });
    }

    openAction(xmlid, context = {}) {
        this.action.doAction(xmlid, { additionalContext: context });
    }
}

registry.category("actions").add("dmag_journey_dashboard", DmagJourneyDashboard);
