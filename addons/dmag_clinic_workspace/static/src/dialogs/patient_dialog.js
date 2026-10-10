/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { useService } from "@web/core/utils/hooks";

/** Tạo nhanh bệnh nhân tại quầy – chỉ các trường thiết yếu, kiểm tra trùng SĐT. */
export class NewPatientDialog extends Component {
    static template = "dmag_clinic_workspace.NewPatientDialog";
    static components = { Dialog };
    static props = { close: Function, catalog: Object, onCreated: Function, initialName: { type: String, optional: true } };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({
            name: this.props.initialName || "",
            phone: "",
            birthdate: "",
            gender: "",
            citizen_id: "",
            source_id: "",
            allergy: "",
            alert_ids: [],
            consent: false,
            duplicate: null,
            saving: false,
        });
    }

    toggleAlert(id) {
        const ids = this.state.alert_ids;
        const idx = ids.indexOf(id);
        idx >= 0 ? ids.splice(idx, 1) : ids.push(id);
    }

    async save(force = false) {
        this.state.saving = true;
        try {
            const res = await this.orm.call("dmag.workspace", "quick_create_patient", [{
                name: this.state.name,
                phone: this.state.phone,
                birthdate: this.state.birthdate || false,
                gender: this.state.gender || false,
                citizen_id: this.state.citizen_id || false,
                source_id: Number(this.state.source_id) || false,
                allergy: this.state.allergy || false,
                alert_ids: this.state.alert_ids,
                consent: this.state.consent,
                force,
            }]);
            if (res.duplicate) {
                this.state.duplicate = res.duplicate;
                return;
            }
            this.notification.add(`Đã tạo hồ sơ ${res.name} (${res.code})`, { type: "success" });
            this.props.onCreated(res);
            this.props.close();
        } finally {
            this.state.saving = false;
        }
    }

    useExisting() {
        this.props.onCreated(this.state.duplicate);
        this.props.close();
    }
}
