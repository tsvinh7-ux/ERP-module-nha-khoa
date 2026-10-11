/** @odoo-module **/

import { useState } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { BookingDialog } from "@dmag_clinic_workspace/dialogs/booking_dialog";

/** AI-11 – chip "Gợi ý" xếp lịch (chấm điểm tại chỗ) trong hộp thoại Đặt lịch. */
patch(BookingDialog.prototype, {
    setup() {
        super.setup(...arguments);
        this.aiSlots = useState({ active: true, items: [], method: "", loading: false });
    },

    async loadSlots() {
        await super.loadSlots(...arguments);
        await this.loadAiSuggestions();
    },

    pickPatient(p) {
        super.pickPatient(...arguments);
        this.loadAiSuggestions();
    },

    async loadAiSuggestions() {
        this.aiSlots.loading = true;
        try {
            const res = await this.orm.call("dmag.workspace", "get_slot_suggestions", [this.state.date], {
                doctor_id: this.state.doctorId || false,
                duration: this.duration,
                service_ids: this.state.serviceIds,
                patient_id: this.state.patient ? this.state.patient.id : false,
            });
            this.aiSlots.active = res.active;
            this.aiSlots.items = res.suggestions || [];
            this.aiSlots.method = res.method || "";
        } finally {
            this.aiSlots.loading = false;
        }
    },

    pickSuggestion(s) {
        const slot = this.state.slots.find((x) => x.time === s.time);
        if (slot) {
            this.pickSlot(slot);
        } else {
            this.state.time = s.time;
            this.state.slotChairs = [s.chair_id];
        }
        if (s.chair_id) {
            this.state.chairId = s.chair_id;
        }
        if (!this.state.doctorId && s.doctor_id) {
            this.state.doctorId = s.doctor_id;
        }
    },
});
