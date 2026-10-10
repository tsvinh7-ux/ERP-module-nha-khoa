/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

/**
 * Biểu tượng "CHẾ ĐỘ DEMO" trên thanh trên cùng: luôn nhắc người dùng đây là cơ sở dữ liệu demo
 * (tích hợp giả lập). Bấm vào mở màn hình "Dữ liệu demo".
 */
export class DmagDemoSystray extends Component {
    static template = "dmag_dental_demo.DemoSystray";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({ active: false, title: "" });
        onWillStart(async () => {
            try {
                const status = await this.orm.call("dmag.demo", "get_demo_status", []);
                this.state.active = status.active;
                this.state.title = status.title;
            } catch {
                this.state.active = false;
            }
        });
    }

    onClick() {
        this.action.doAction("dmag_dental_demo.action_dmag_demo_settings");
    }
}

registry.category("systray").add("dmag_dental_demo.demo_systray", { Component: DmagDemoSystray }, { sequence: 1 });
