/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { useService } from "@web/core/utils/hooks";
import { formatMoney } from "../js/utils";
import { NewPatientDialog } from "./patient_dialog";

function todayISO(offset = 0) {
    const d = new Date();
    d.setDate(d.getDate() + offset);
    const pad = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/** Đặt lịch 3 bước: Bệnh nhân → Dịch vụ & bác sĩ → Chọn giờ trống. */
export class BookingDialog extends Component {
    static template = "dmag_clinic_workspace.BookingDialog";
    static components = { Dialog };
    static props = { close: Function, onBooked: Function, doctorId: { optional: true } };

    setup() {
        this.orm = useService("orm");
        this.dialog = useService("dialog");
        this.notification = useService("notification");
        this.formatMoney = formatMoney;
        this.state = useState({
            catalog: { doctors: [], chairs: [], services: [], sources: [], alerts: [] },
            query: "",
            results: [],
            patient: null,
            serviceIds: [],
            doctorId: this.props.doctorId || false,
            date: todayISO(),
            slots: [],
            time: "",
            chairId: false,
            reason: "",
            confirm: true,
            saving: false,
            loadingSlots: false,
        });
        this.days = [0, 1, 2, 3, 4, 5, 6].map((o) => {
            const d = new Date();
            d.setDate(d.getDate() + o);
            const label = o === 0 ? "Hôm nay" : o === 1 ? "Ngày mai" : d.toLocaleDateString("vi-VN", { weekday: "short", day: "2-digit", month: "2-digit" });
            return { iso: todayISO(o), label };
        });
        onWillStart(async () => {
            this.state.catalog = await this.orm.call("dmag.workspace", "get_booking_catalog", []);
            await this.loadSlots();
        });
    }

    get duration() {
        const total = this.state.catalog.services
            .filter((s) => this.state.serviceIds.includes(s.id))
            .reduce((sum, s) => sum + (s.duration || 0), 0);
        return total || 30;
    }

    get total() {
        return this.state.catalog.services
            .filter((s) => this.state.serviceIds.includes(s.id))
            .reduce((sum, s) => sum + (s.price || 0), 0);
    }

    get morningSlots() {
        return this.state.slots.filter((s) => Number(s.time.slice(0, 2)) < 12);
    }

    get afternoonSlots() {
        return this.state.slots.filter((s) => Number(s.time.slice(0, 2)) >= 12);
    }

    async onSearch(ev) {
        this.state.query = ev.target.value;
        this.state.results = await this.orm.call("dmag.workspace", "search_patients", [this.state.query]);
    }

    pickPatient(p) {
        this.state.patient = p;
        this.state.results = [];
    }

    newPatient() {
        this.dialog.add(NewPatientDialog, {
            catalog: this.state.catalog,
            initialName: this.state.query,
            onCreated: (p) => this.pickPatient({ id: p.id, name: p.name, code: p.code, alerts: [] }),
        });
    }

    async toggleService(id) {
        const ids = this.state.serviceIds;
        const idx = ids.indexOf(id);
        idx >= 0 ? ids.splice(idx, 1) : ids.push(id);
        await this.loadSlots();
    }

    async setDoctor(ev) {
        this.state.doctorId = Number(ev.target.value) || false;
        await this.loadSlots();
    }

    async setDate(iso) {
        this.state.date = iso;
        await this.loadSlots();
    }

    async loadSlots() {
        this.state.loadingSlots = true;
        this.state.time = "";
        this.state.slots = await this.orm.call("dmag.workspace", "get_free_slots", [this.state.date, this.state.doctorId, this.duration]);
        this.state.loadingSlots = false;
    }

    pickSlot(slot) {
        this.state.time = slot.time;
        this.state.chairId = slot.chairs[0] || false;
        this.state.slotChairs = slot.chairs;
    }

    chairName(id) {
        const c = this.state.catalog.chairs.find((x) => x.id === id);
        return c ? c.name : "";
    }

    async book() {
        this.state.saving = true;
        try {
            const res = await this.orm.call("dmag.workspace", "quick_book", [{
                patient_id: this.state.patient.id,
                doctor_id: this.state.doctorId,
                chair_id: this.state.chairId,
                service_ids: this.state.serviceIds,
                date: this.state.date,
                time: this.state.time,
                reason: this.state.reason,
                confirm: this.state.confirm,
            }]);
            this.notification.add(`Đã đặt lịch ${this.state.time} cho ${this.state.patient.name} (${res.name})`, { type: "success" });
            this.props.onBooked(res);
            this.props.close();
        } finally {
            this.state.saving = false;
        }
    }
}
