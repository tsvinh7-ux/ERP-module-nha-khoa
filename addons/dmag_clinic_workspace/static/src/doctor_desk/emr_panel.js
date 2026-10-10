/** @odoo-module **/

import { Component } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

const VITALS = [
    ["pulse", "Mạch", "lần/phút"],
    ["temperature", "Nhiệt độ", "°C"],
    ["bp_systolic", "HA tâm thu", "mmHg"],
    ["bp_diastolic", "HA tâm trương", "mmHg"],
    ["respiratory_rate", "Nhịp thở", "lần/phút"],
    ["weight", "Cân nặng", "kg"],
    ["height", "Chiều cao", "cm"],
];

const SECTIONS = [
    { title: "III. Hỏi bệnh", fields: [["present_illness", "Quá trình bệnh lý (bệnh sử)"], ["personal_history", "Tiền sử bản thân"], ["family_history", "Tiền sử gia đình"]] },
    { title: "IV. Khám chuyên khoa Răng Hàm Mặt", fields: [["exam_extraoral", "Khám ngoài mặt"], ["exam_intraoral", "Khám trong miệng"], ["exam_occlusion", "Khớp cắn"], ["exam_soft_tissue", "Mô mềm"], ["exam_periodontal", "Nha chu"]] },
    { title: "V. Cận lâm sàng · IX. Hướng điều trị", fields: [["paraclinical_summary", "Tóm tắt cận lâm sàng (X-quang, xét nghiệm)"], ["treatment_direction", "Hướng điều trị"]] },
];

/**
 * Các mục bệnh án ngoại trú RHM (mẫu 16/BV1) – hiển thị khi đã cài dmag_dental_emr.
 */
export class EmrPanel extends Component {
    static template = "dmag_clinic_workspace.EmrPanel";
    static props = { visitId: Number, emr: Object, locked: Boolean };

    setup() {
        this.orm = useService("orm");
        this.VITALS = VITALS;
        this.SECTIONS = SECTIONS;
    }

    async save(field, raw, numeric = false) {
        if (this.props.locked) {
            return;
        }
        const value = numeric ? (raw === "" ? 0 : Number(raw)) : raw;
        if (this.props.emr[field] === value) {
            return;
        }
        this.props.emr[field] = value;
        await this.orm.call("dmag.dental.visit", "save_record_from_workspace", [[this.props.visitId], { [field]: value }]);
    }
}
