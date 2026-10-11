/** @odoo-module **/

import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";

/**
 * Màn hình chờ cho hành động "Bảng điều hành mục tiêu" khi chưa cài module dmag_dental_goals.
 * Module dmag_dental_goals đăng ký component thật cùng khóa (force) và thay thế màn hình này.
 */
export class GoalDashboardPlaceholder extends Component {
    static template = "dmag_clinic_workspace.GoalDashboardPlaceholder";
    static props = ["*"];
}

registry.category("actions").add("dmag_goal_dashboard", GoalDashboardPlaceholder);
