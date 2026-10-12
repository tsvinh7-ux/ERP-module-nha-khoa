/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const WEEKDAYS = ["Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7", "Chủ nhật"];
const KIND_LABELS = { weekly_off: "Nghỉ luân phiên", leave: "Nghỉ phép", swap_off: "Đổi ca" };

/** Hộp thoại tạo yêu cầu nghỉ phép / đổi ca (Quản lý có thể duyệt ngay). */
class LeaveDialog extends Component {
    static template = "dmag_clinic_workspace.LeaveDialog";
    static components = { Dialog };
    static props = { close: Function, members: Array, date: String, canManage: Boolean, myMemberId: { optional: true }, onSaved: Function };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({
            memberId: this.props.canManage ? (this.props.members[0] || {}).id : this.props.myMemberId,
            kind: "leave",
            dateFrom: this.props.date,
            dateTo: this.props.date,
            swapDate: "",
            reason: "",
            approve: this.props.canManage,
            saving: false,
        });
    }

    get members() {
        return this.props.canManage ? this.props.members : this.props.members.filter((m) => m.id === this.props.myMemberId);
    }

    async save() {
        this.state.saving = true;
        try {
            const res = await this.orm.call("dmag.staff.leave", "request_leave", [{
                member_id: this.state.memberId,
                kind: this.state.kind,
                date_from: this.state.dateFrom,
                date_to: this.state.kind === "leave" ? this.state.dateTo : this.state.dateFrom,
                swap_date: this.state.kind === "swap" ? this.state.swapDate : false,
                reason: this.state.reason,
                approve: this.state.approve,
            }]);
            this.notification.add(
                res.state === "approved" ? `Đã duyệt: ${res.name} – ${res.label}` : `Đã gửi yêu cầu: ${res.label} – chờ Quản lý duyệt`,
                { type: res.warning ? "warning" : "success" }
            );
            if (res.warning) {
                this.notification.add(`Thiếu người trực: ${res.warning}`, { type: "danger", sticky: true });
            }
            this.props.onSaved();
            this.props.close();
        } finally {
            this.state.saving = false;
        }
    }
}

/** Lịch nghỉ luân phiên: lịch tháng ai trực / ai nghỉ, cảnh báo thiếu người, duyệt nghỉ phép / đổi ca. */
export class RotationCalendar extends Component {
    static template = "dmag_clinic_workspace.RotationCalendar";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.dialog = useService("dialog");
        this.notification = useService("notification");
        this.user = useService("user");
        this.WEEKDAYS = WEEKDAYS;
        this.KIND_LABELS = KIND_LABELS;
        this.state = useState({ data: null, month: false, loading: true });
        onWillStart(() => this.load());
    }

    async load(month) {
        this.state.loading = true;
        this.state.data = await this.orm.call("dmag.staff.rotation", "get_month_roster", [month || this.state.month || false]);
        this.state.month = this.state.data.month;
        this.state.loading = false;
    }

    get myMemberId() {
        const me = (this.state.data.members || []).find((m) => m.user_id === this.user.userId);
        return me ? me.id : false;
    }

    cellClass(day) {
        const cls = ["dmag-rot-day"];
        if (!day.in_month) cls.push("is-out");
        if (!day.open) cls.push("is-closed");
        else if (!day.ok) cls.push("is-short");
        if (day.is_sunday) cls.push("is-sunday");
        if (day.is_today) cls.push("is-today");
        return cls.join(" ");
    }

    covList(day) {
        return this.state.data.roles.map((r) => ({ ...r, ...(day.coverage[r.code] || { n: 0, ok: true }) }));
    }

    async generate() {
        const res = await this.orm.call("dmag.staff.rotation", "action_generate_rotation", []);
        this.notification.add(
            res.warnings.length ? res.warnings.join(" ") : "Đã xếp lại ngày nghỉ luân phiên – đủ người trực mọi ngày.",
            { type: res.warnings.length ? "warning" : "success", sticky: !!res.warnings.length }
        );
        await this.load();
    }

    newLeave(date) {
        if (!this.state.data.can_manage && !this.myMemberId) {
            this.notification.add("Tài khoản của bạn chưa có trong lịch luân phiên – nhờ Quản lý thêm.", { type: "warning" });
            return;
        }
        this.dialog.add(LeaveDialog, {
            members: this.state.data.members,
            date: date || new Date().toISOString().slice(0, 10),
            canManage: this.state.data.can_manage,
            myMemberId: this.myMemberId,
            onSaved: () => this.load(),
        });
    }

    async approve(leave) {
        await this.orm.call("dmag.staff.leave", "action_approve", [[leave.id]]);
        this.notification.add(`Đã duyệt: ${leave.name} – ${leave.label}`, { type: "success" });
        await this.load();
    }

    async refuse(leave) {
        await this.orm.call("dmag.staff.leave", "action_refuse", [[leave.id]]);
        await this.load();
    }

    openMembers() {
        return this.action.doAction("dmag_dental_base.action_dmag_staff_rotation");
    }

    openSchedule() {
        return this.action.doAction("dmag_dental_base.action_dmag_clinic_schedule");
    }
}

registry.category("actions").add("dmag_staff_rotation_calendar", RotationCalendar);
