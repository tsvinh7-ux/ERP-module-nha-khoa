/** @odoo-module **/

import { Component, onWillStart, onMounted, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { formatDuration, formatMoney, formatTime, minutesSince, PAYMENT_STATES, VISIT_STATES } from "../js/utils";

const WAIT_ALERT_MINUTES = 15;

export class FrontDesk extends Component {
    static template = "dmag_clinic_workspace.FrontDesk";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = useState({
            loading: true,
            board: { visits: [], chairs: [], doctors: [] },
            search: "",
            doctorId: false,
            chairPicker: null, // visit id đang chọn ghế
            tick: 0,
        });
        this.formatMoney = formatMoney;
        this.formatTime = formatTime;
        this.formatDuration = formatDuration;
        this.VISIT_STATES = VISIT_STATES;
        this.PAYMENT_STATES = PAYMENT_STATES;
        this.WAIT_ALERT_MINUTES = WAIT_ALERT_MINUTES;
        onWillStart(() => this.load());
        onMounted(() => {
            this.refreshTimer = setInterval(() => this.load(), 30000);
            this.tickTimer = setInterval(() => this.state.tick++, 20000);
        });
        onWillUnmount(() => {
            clearInterval(this.refreshTimer);
            clearInterval(this.tickTimer);
        });
    }

    async load() {
        this.state.board = await this.orm.call("dmag.dental.visit", "get_frontdesk_board", []);
        this.state.loading = false;
    }

    // ---------------------------------------------------------------- data
    get visits() {
        const q = this.state.search.trim().toLowerCase();
        return this.state.board.visits.filter((v) => {
            if (this.state.doctorId && v.doctor_id !== this.state.doctorId) {
                return false;
            }
            if (!q) {
                return true;
            }
            return [v.patient, v.patient_code, v.phone].some((s) => (s || "").toLowerCase().includes(q));
        });
    }

    get lanes() {
        const visits = this.visits;
        return [
            {
                key: "upcoming",
                title: "Sắp đến",
                hint: "Đã đặt / đã xác nhận",
                visits: visits.filter((v) => ["draft", "confirmed"].includes(v.state)),
            },
            {
                key: "waiting",
                title: "Đang chờ",
                hint: `Cảnh báo khi chờ quá ${WAIT_ALERT_MINUTES} phút`,
                visits: visits.filter((v) => v.state === "arrived"),
            },
            {
                key: "in_chair",
                title: "Đang điều trị",
                hint: "Trên ghế",
                visits: visits.filter((v) => v.state === "in_chair"),
            },
            {
                key: "checkout",
                title: "Chờ thu tiền",
                hint: "Hoàn tất – còn phải thu",
                visits: visits.filter((v) => v.state === "done" && ["to_invoice", "to_pay"].includes(v.payment_status)),
            },
            {
                key: "finished",
                title: "Đã xong",
                hint: "Cảm ơn & chăm sóc sau",
                visits: visits.filter((v) => v.state === "done" && !["to_invoice", "to_pay"].includes(v.payment_status)),
            },
        ];
    }

    get kpis() {
        const all = this.state.board.visits;
        const waiting = all.filter((v) => v.state === "arrived");
        const lost = all.filter((v) => ["cancel", "no_show"].includes(v.state));
        return [
            { label: "Lịch hôm nay", value: all.filter((v) => !["cancel"].includes(v.state)).length },
            { label: "Khách mới", value: all.filter((v) => v.is_new).length },
            { label: "Đang chờ", value: waiting.length, alert: waiting.some((v) => this.waitOf(v) > WAIT_ALERT_MINUTES) },
            { label: "Ghế đang dùng", value: `${this.state.board.chairs.filter((c) => c.visit).length}/${this.state.board.chairs.length}` },
            { label: "Hoàn tất", value: all.filter((v) => v.state === "done").length },
            { label: "Không đến / hủy", value: lost.length },
        ];
    }

    get freeChairs() {
        return this.state.board.chairs.filter((c) => !c.visit);
    }

    waitOf(visit) {
        // eslint-disable-next-line no-unused-expressions
        this.state.tick;
        return visit.state === "arrived" ? minutesSince(visit.checkin) : visit.wait;
    }

    elapsedOf(visit) {
        // eslint-disable-next-line no-unused-expressions
        this.state.tick;
        return minutesSince(visit.chair_time);
    }

    initials(name) {
        return (name || "?")
            .split(" ")
            .filter(Boolean)
            .slice(-2)
            .map((w) => w[0])
            .join("")
            .toUpperCase();
    }

    // ---------------------------------------------------------------- actions
    async callVisit(method, visit, args = []) {
        await this.orm.call("dmag.dental.visit", method, [[visit.id], ...args]);
        await this.load();
    }

    async checkIn(visit) {
        await this.callVisit("action_check_in", visit);
        this.notification.add(`Đã check-in ${visit.patient}. Hệ thống gửi lời chào mừng qua Zalo (nếu bật).`, {
            type: "success",
        });
    }

    async confirm(visit) {
        await this.callVisit("action_confirm", visit);
    }

    openChairPicker(visit) {
        if (visit.chair_id && !this.state.board.chairs.find((c) => c.id === visit.chair_id && c.visit)) {
            return this.seat(visit, visit.chair_id);
        }
        this.state.chairPicker = visit.id;
    }

    async seat(visit, chairId) {
        this.state.chairPicker = null;
        await this.orm.call("dmag.dental.visit", "action_start", [[visit.id]], { chair_id: chairId });
        await this.load();
    }

    async finish(visit) {
        await this.callVisit("action_done", visit);
    }

    async noShow(visit) {
        await this.callVisit("action_no_show", visit);
    }

    async collect(visit) {
        if (visit.payment_status === "to_invoice") {
            const action = await this.orm.call("dmag.dental.visit", "action_create_invoice", [[visit.id]]);
            return this.action.doAction(action, { onClose: () => this.load() });
        }
        return this.openVisit(visit);
    }

    openVisit(visit) {
        return this.action.doAction(
            {
                type: "ir.actions.act_window",
                res_model: "dmag.dental.visit",
                res_id: visit.id,
                views: [[false, "form"]],
                target: "new",
            },
            { onClose: () => this.load() }
        );
    }

    openPatient(visit) {
        return this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "res.partner",
            res_id: visit.patient_id,
            views: [[false, "form"]],
            target: "current",
        });
    }

    newBooking() {
        return this.action.doAction(
            {
                type: "ir.actions.act_window",
                res_model: "dmag.dental.visit",
                views: [[false, "form"]],
                target: "new",
                name: "Đặt lịch hẹn",
                context: { default_doctor_id: this.state.doctorId || false },
            },
            { onClose: () => this.load() }
        );
    }

    newPatient() {
        return this.action.doAction(
            {
                type: "ir.actions.act_window",
                res_model: "res.partner",
                views: [[false, "form"]],
                target: "new",
                name: "Bệnh nhân mới",
                context: { default_is_patient: true, default_is_company: false },
            },
            { onClose: () => this.load() }
        );
    }

    openCalendar() {
        return this.action.doAction("dmag_dental_clinic.action_dmag_visit_calendar");
    }

    openDoctorDesk(visit) {
        return this.action.doAction({
            type: "ir.actions.client",
            tag: "dmag_doctor_desk",
            params: { visit_id: visit.id },
        });
    }
}

registry.category("actions").add("dmag_frontdesk", FrontDesk);
