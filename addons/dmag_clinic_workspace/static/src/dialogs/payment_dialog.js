/** @odoo-module **/

import { Component, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { useService } from "@web/core/utils/hooks";
import { formatMoney } from "../js/utils";

const METHODS = [
    { key: "transfer", label: "Chuyển khoản QR", icon: "fa-qrcode" },
    { key: "cash", label: "Tiền mặt", icon: "fa-money" },
    { key: "card", label: "Quẹt thẻ", icon: "fa-credit-card" },
];

/** Thu tiền tại quầy: QR động (SePay) tự xác nhận, tiền mặt có tính tiền thừa, thẻ. */
export class PaymentDialog extends Component {
    static template = "dmag_clinic_workspace.PaymentDialog";
    static components = { Dialog };
    static props = { close: Function, visitId: Number, onPaid: Function };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.formatMoney = formatMoney;
        this.METHODS = METHODS;
        this.state = useState({ panel: null, method: "transfer", qr: null, received: "", amount: 0, saving: false, paid: false });
        onWillStart(() => this.load());
        onWillUnmount(() => clearInterval(this.poll));
    }

    async load() {
        const panel = await this.orm.call("dmag.workspace", "get_payment_panel", [this.props.visitId]);
        this.state.panel = panel;
        this.state.amount = panel.amount_due;
        if (!panel.sepay && this.state.method === "transfer") {
            this.state.method = "cash";
        }
        if (panel.sepay && this.state.method === "transfer") {
            await this.loadQr();
        }
    }

    async loadQr() {
        this.state.qr = await this.orm.call("dmag.dental.visit", "get_payment_qr", [[this.props.visitId]]);
        clearInterval(this.poll);
        this.poll = setInterval(() => this.checkPaid(), 5000);
    }

    async checkPaid() {
        const panel = await this.orm.call("dmag.workspace", "get_payment_panel", [this.props.visitId]);
        if (panel.payment_status === "paid") {
            clearInterval(this.poll);
            this.state.paid = true;
            this.notification.add(`Đã nhận chuyển khoản – ${this.state.panel.patient}`, { type: "success" });
            this.props.onPaid();
        }
    }

    async setMethod(key) {
        this.state.method = key;
        clearInterval(this.poll);
        if (key === "transfer" && this.state.panel.sepay) {
            await this.loadQr();
        }
    }

    get change() {
        const received = Number(String(this.state.received).replace(/\D/g, "")) || 0;
        return Math.max(0, received - this.state.amount);
    }

    async confirm() {
        this.state.saving = true;
        try {
            await this.orm.call("dmag.dental.visit", "register_payment", [[this.props.visitId], this.state.method, this.state.amount]);
            this.state.paid = true;
            this.notification.add(`Đã thu ${formatMoney(this.state.amount)}`, { type: "success" });
            this.props.onPaid();
        } finally {
            this.state.saving = false;
        }
    }

    async printReceipt() {
        await this.action.doAction("dmag_clinic_workspace.action_report_payment_receipt", {
            additionalContext: { active_ids: [this.props.visitId], active_model: "dmag.dental.visit" },
        });
    }
}
