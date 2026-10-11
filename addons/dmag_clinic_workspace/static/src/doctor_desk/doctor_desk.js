/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Odontogram } from "../odontogram/odontogram";
import { ToothZoom } from "../odontogram/tooth_zoom";
import { ConsultMode } from "../consult/consult_mode";
import { EmrPanel } from "./emr_panel";
import { RxPanel } from "./rx_panel";
import { formatDate, formatMoney, formatTime, PLAN_STATES, VISIT_STATES } from "../js/utils";

const QUICK_PHRASES = {
    chief_complaint: ["Ê buốt khi ăn lạnh", "Đau tự nhiên về đêm", "Chảy máu chân răng", "Khám định kỳ", "Muốn làm đẹp răng"],
    examination: ["Lỗ sâu mặt nhai", "Gõ dọc đau", "Lợi viêm đỏ, chảy máu khi thăm", "Cao răng độ 2", "Răng lung lay độ 1"],
    assessment: ["Sâu ngà", "Viêm tủy không hồi phục", "Viêm lợi mạn", "Răng khôn mọc lệch"],
    treatment_note: ["Gây tê tại chỗ", "Trám Composite", "Lấy tủy, đặt thuốc", "Cạo vôi, đánh bóng"],
    advice: ["Không ăn nhai bên điều trị 2 giờ", "Uống thuốc theo đơn", "Chải răng 2 lần/ngày", "Tái khám sau 7 ngày"],
};

export class DoctorDesk extends Component {
    static template = "dmag_clinic_workspace.DoctorDesk";
    static components = { Odontogram, ToothZoom, ConsultMode, EmrPanel, RxPanel };
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = useState({
            loading: true,
            desk: { visits: [], all_visits: [], practitioner: false },
            showAll: false,
            visitId: this.props.action?.params?.visit_id || false,
            ws: null,
            tab: "chart",
            dentition: "permanent",
            selection: { teeth: {} },
            zoomTooth: false,
            showPlanned: true,
            builder: null,
            consultPlan: null,
            procedure: { productId: false },
            catalog: { conditions: [], teeth: [], surfaces: [] },
            services: [],
            diagnoses: [],
        });
        this.QUICK_PHRASES = QUICK_PHRASES;
        this.VISIT_STATES = VISIT_STATES;
        this.PLAN_STATES = PLAN_STATES;
        this.formatMoney = formatMoney;
        this.formatTime = formatTime;
        this.formatDate = formatDate;
        onWillStart(async () => {
            const [catalog, services, diagnoses] = await Promise.all([
                this.orm.call("dmag.dental.chart.entry", "get_chart_catalog", []),
                this.orm.searchRead(
                    "product.product",
                    [["is_dental_service", "=", true]],
                    ["id", "display_name", "lst_price", "dental_requires_tooth", "dental_category"],
                    { order: "dental_category, name" }
                ),
                this.orm.searchRead("dmag.dental.diagnosis", [], ["id", "code", "name"]),
            ]);
            this.state.catalog = catalog;
            this.state.services = services;
            this.state.diagnoses = diagnoses;
            await this.loadDesk();
            if (this.state.visitId) {
                await this.openVisit(this.state.visitId);
            } else if (this.myVisits.length) {
                const current = this.myVisits.find((v) => v.state === "in_chair") || this.myVisits[0];
                await this.openVisit(current.id);
            }
        });
    }

    // ---------------------------------------------------------------- loading
    async loadDesk() {
        this.state.desk = await this.orm.call("dmag.dental.visit", "get_doctor_desk", []);
        this.state.loading = false;
    }

    get myVisits() {
        const list = this.state.showAll ? this.state.desk.all_visits : this.state.desk.visits;
        return list.filter((v) => !["cancel", "no_show"].includes(v.state));
    }

    async openVisit(visitId) {
        this.state.visitId = visitId;
        this.state.selection = { teeth: {} };
        this.state.builder = null;
        await this.reloadVisit();
        this.state.dentition = this.state.ws.patient.primary_dentition ? "mixed" : "permanent";
    }

    async reloadVisit() {
        this.state.ws = await this.orm.call("dmag.dental.visit", "get_visit_workspace", [[this.state.visitId]]);
    }

    get visit() {
        return this.state.ws && this.state.ws.visit;
    }

    get patient() {
        return this.state.ws && this.state.ws.patient;
    }

    get locked() {
        return this.visit && this.visit.record_state === "signed";
    }

    // ---------------------------------------------------------------- chart selection
    get selectedTeeth() {
        return Object.keys(this.state.selection.teeth);
    }

    get selectedSurfaces() {
        const all = new Set();
        for (const surfaces of Object.values(this.state.selection.teeth)) {
            surfaces.forEach((s) => all.add(s));
        }
        return [...all];
    }

    toggleTooth(code) {
        const teeth = { ...this.state.selection.teeth };
        if (code in teeth) {
            delete teeth[code];
        } else {
            teeth[code] = [];
            this.state.zoomTooth = code;
        }
        this.state.selection = { teeth };
    }

    /** Răng đang phóng to ở khung bên phải: răng vừa chạm, nếu đã bỏ chọn thì răng chọn sau cùng. */
    get zoomCode() {
        const teeth = this.selectedTeeth;
        if (this.state.zoomTooth && teeth.includes(this.state.zoomTooth)) {
            return this.state.zoomTooth;
        }
        return teeth.length ? teeth[teeth.length - 1] : false;
    }

    toggleSurface(code, surface) {
        const teeth = { ...this.state.selection.teeth };
        const current = teeth[code] ? [...teeth[code]] : [];
        const idx = current.indexOf(surface);
        if (idx >= 0) {
            current.splice(idx, 1);
        } else {
            current.push(surface);
        }
        teeth[code] = current;
        this.state.selection = { teeth };
        this.state.zoomTooth = code;
    }

    clearSelection() {
        this.state.selection = { teeth: {} };
    }

    get conditionGroups() {
        const groups = [
            { key: "finding", title: "Bệnh lý" },
            { key: "existing", title: "Đã có / đã điều trị" },
            { key: "missing", title: "Mất / chưa mọc" },
        ];
        return groups.map((g) => ({ ...g, items: this.state.catalog.conditions.filter((c) => c.category === g.key) }));
    }

    async applyCondition(condition) {
        const teeth = this.selectedTeeth;
        if (!teeth.length) {
            this.notification.add("Chạm vào răng hoặc mặt răng trên sơ đồ trước.", { type: "warning" });
            return;
        }
        const surfaces = condition.scope === "surface" ? this.selectedSurfaces : [];
        if (condition.scope === "surface" && condition.category === "finding" && !surfaces.length) {
            this.notification.add(`"${condition.name}" cần chọn mặt răng (chạm vào mặt cụ thể).`, { type: "warning" });
            return;
        }
        await this.orm.call("dmag.dental.chart.entry", "add_from_chart", [this.patient.id, teeth, condition.id], {
            surfaces,
            visit_id: this.visit.id,
        });
        this.clearSelection();
        await this.reloadVisit();
    }

    get selectionEntries() {
        const teeth = this.selectedTeeth;
        return this.state.ws.chart.filter((e) => teeth.includes(e.tooth));
    }

    get findings() {
        return this.state.ws.chart.filter((e) => e.category === "finding");
    }

    get chartSummary() {
        const groups = { finding: [], existing: [], missing: [], planned: [] };
        for (const e of this.state.ws.chart) {
            const key = e.layer === "planned" ? "planned" : e.category;
            groups[key].push(e);
        }
        return [
            { key: "finding", title: "Bệnh lý cần xử lý", items: groups.finding },
            { key: "planned", title: "Đã lên kế hoạch", items: groups.planned },
            { key: "existing", title: "Phục hồi / đã điều trị", items: groups.existing },
            { key: "missing", title: "Mất / chưa mọc", items: groups.missing },
        ].filter((g) => g.items.length);
    }

    selectEntryTooth(entry) {
        this.state.selection = { teeth: { [entry.tooth]: [...entry.surfaces] } };
        this.state.zoomTooth = entry.tooth;
    }

    async resolveEntry(entry) {
        await this.orm.call("dmag.dental.chart.entry", "action_resolve", [[entry.id]]);
        await this.reloadVisit();
    }

    // ---------------------------------------------------------------- visit actions
    async visitAction(method) {
        await this.orm.call("dmag.dental.visit", method, [[this.visit.id]]);
        await Promise.all([this.reloadVisit(), this.loadDesk()]);
    }

    async saveField(field, value) {
        if (this.locked) {
            return;
        }
        if (this.visit[field] === value) {
            return;
        }
        this.visit[field] = value;
        await this.orm.call("dmag.dental.visit", "save_record_from_workspace", [[this.visit.id], { [field]: value }]);
    }

    appendPhrase(field, phrase) {
        if (this.locked) {
            return;
        }
        const current = this.visit[field] || "";
        const value = current ? `${current.replace(/\s+$/, "")}; ${phrase}` : phrase;
        this.saveField(field, value);
    }

    async setPain(score) {
        await this.saveField("pain_score", score);
    }

    get suggestedDiagnoses() {
        const codes = new Set(this.state.ws.chart.map((e) => e.diagnosis).filter(Boolean));
        return [...codes];
    }

    async toggleDiagnosis(diag) {
        if (this.locked) {
            return;
        }
        const ids = this.visit.diagnoses.map((d) => d.id);
        const next = ids.includes(diag.id) ? ids.filter((i) => i !== diag.id) : [...ids, diag.id];
        await this.orm.call("dmag.dental.visit", "save_record_from_workspace", [[this.visit.id], { diagnosis_ids: next }]);
        await this.reloadVisit();
    }

    get diagnosisChoices() {
        const chartCodes = new Set(
            this.state.ws.chart.map((e) => (e.diagnosis || "").split(" ")[0]).filter(Boolean)
        );
        const selected = new Set(this.visit.diagnoses.map((d) => d.id));
        return this.state.diagnoses
            .filter((d) => chartCodes.has(d.code) || selected.has(d.id))
            .map((d) => ({ ...d, selected: selected.has(d.id), label: `${d.code} – ${d.name}` }));
    }

    async addDiagnosisById(ev) {
        const id = Number(ev.target.value);
        ev.target.value = "";
        if (!id) {
            return;
        }
        const diag = this.state.diagnoses.find((d) => d.id === id);
        await this.toggleDiagnosis(diag);
    }

    // ---------------------------------------------------------------- procedures
    get todoPlanLines() {
        const lines = [];
        for (const plan of this.state.ws.plans) {
            if (!["accepted", "in_progress"].includes(plan.state)) {
                continue;
            }
            const option = plan.options.find((o) => o.id === plan.accepted_option_id);
            for (const line of option ? option.lines : []) {
                if (line.state === "todo") {
                    lines.push({ ...line, plan: plan.name });
                }
            }
        }
        return lines;
    }

    async doPlanLine(line) {
        await this.orm.call("dmag.dental.procedure", "add_from_workspace", [this.visit.id, false], {
            plan_line_id: line.id,
        });
        this.notification.add(`Đã ghi nhận: ${line.product} – R${line.teeth.join(", ")}`, { type: "success" });
        await this.reloadVisit();
    }

    async addProcedure() {
        const productId = Number(this.state.procedure.productId);
        if (!productId) {
            return;
        }
        const service = this.state.services.find((s) => s.id === productId);
        if (service.dental_requires_tooth && !this.selectedTeeth.length) {
            this.notification.add("Chọn răng trên sơ đồ cho thủ thuật này.", { type: "warning" });
            this.state.tab = "chart";
            return;
        }
        await this.orm.call("dmag.dental.procedure", "add_from_workspace", [this.visit.id, productId], {
            teeth: this.selectedTeeth,
            surfaces: this.selectedSurfaces,
        });
        this.state.procedure.productId = false;
        this.clearSelection();
        await this.reloadVisit();
    }

    get proceduresTotal() {
        return this.state.ws.procedures.reduce((sum, p) => sum + p.amount, 0);
    }

    // ---------------------------------------------------------------- plan builder
    startBuilder() {
        const findings = this.findings;
        const lines = findings.map((f) => {
            const condition = this.state.catalog.conditions.find((c) => c.id === f.condition_id);
            const suggested = condition && condition.services.length ? condition.services[0].id : false;
            return {
                key: `f${f.id}`,
                finding_ids: [f.id],
                teeth: [f.tooth],
                surfaces: f.surfaces,
                label: `R${f.tooth}${f.surfaces.length ? " (" + f.surfaces.join("") + ")" : ""} · ${f.condition}`,
                productA: suggested,
                productB: false,
                phase: 1,
            };
        });
        if (!lines.length && this.selectedTeeth.length) {
            lines.push({
                key: "sel",
                finding_ids: [],
                teeth: this.selectedTeeth,
                surfaces: this.selectedSurfaces,
                label: `R${this.selectedTeeth.join(", ")}`,
                productA: false,
                productB: false,
                phase: 1,
            });
        }
        this.state.builder = {
            title: "",
            nameA: "Phương án A – Khuyến nghị",
            nameB: "Phương án B – Tiết kiệm",
            summaryA: "",
            summaryB: "",
            installmentA: 0,
            installmentB: 0,
            useB: true,
            lines,
        };
        this.state.tab = "plan";
    }

    addBuilderLine() {
        this.state.builder.lines.push({
            key: `n${Date.now()}`,
            finding_ids: [],
            teeth: this.selectedTeeth,
            surfaces: this.selectedSurfaces,
            label: this.selectedTeeth.length ? `R${this.selectedTeeth.join(", ")}` : "Không theo răng",
            productA: false,
            productB: false,
            phase: 1,
        });
    }

    removeBuilderLine(line) {
        const lines = this.state.builder.lines;
        lines.splice(lines.indexOf(line), 1);
    }

    builderTotal(which) {
        let total = 0;
        for (const line of this.state.builder.lines) {
            const productId = Number(which === "A" ? line.productA : line.productB);
            const service = this.state.services.find((s) => s.id === productId);
            if (service) {
                const qty = service.dental_requires_tooth && line.teeth.length ? line.teeth.length : 1;
                total += qty * service.lst_price;
            }
        }
        return total;
    }

    async saveBuilder() {
        const b = this.state.builder;
        const makeLines = (which) =>
            b.lines
                .filter((l) => Number(which === "A" ? l.productA : l.productB))
                .map((l) => ({
                    product_id: Number(which === "A" ? l.productA : l.productB),
                    teeth: l.teeth,
                    surfaces: l.surfaces,
                    phase: Number(l.phase) || 1,
                    finding_ids: l.finding_ids,
                }));
        const options = [
            {
                name: b.nameA,
                title: b.title,
                summary: b.summaryA,
                installment_months: Number(b.installmentA) || 0,
                is_recommended: true,
                lines: makeLines("A"),
            },
        ];
        if (b.useB && makeLines("B").length) {
            options.push({
                name: b.nameB,
                summary: b.summaryB,
                installment_months: Number(b.installmentB) || 0,
                lines: makeLines("B"),
            });
        }
        if (!options[0].lines.length) {
            this.notification.add("Phương án A chưa có dịch vụ nào.", { type: "warning" });
            return;
        }
        await this.orm.call("dmag.treatment.plan", "create_from_workspace", [this.patient.id, this.visit.id, options]);
        this.state.builder = null;
        this.notification.add("Đã lập kế hoạch điều trị. Mở Chế độ tư vấn để trình bày cho bệnh nhân.", {
            type: "success",
        });
        await this.reloadVisit();
    }

    openConsult(plan) {
        this.state.consultPlan = plan;
    }

    async onConsultClosed(changed) {
        this.state.consultPlan = null;
        if (changed) {
            await this.reloadVisit();
        }
    }

    openPlanForm(plan) {
        return this.action.doAction(
            {
                type: "ir.actions.act_window",
                res_model: "dmag.treatment.plan",
                res_id: plan.id,
                views: [[false, "form"]],
                target: "new",
            },
            { onClose: () => this.reloadVisit() }
        );
    }

    openPatientForm() {
        return this.action.doAction(
            {
                type: "ir.actions.act_window",
                res_model: "res.partner",
                res_id: this.patient.id,
                views: [[false, "form"]],
                target: "new",
            },
            { onClose: () => this.reloadVisit() }
        );
    }

    get hasRx() {
        return this.state.ws && Array.isArray(this.state.ws.prescriptions);
    }

    get hasEmr() {
        return this.state.ws && this.state.ws.emr;
    }

    async onRxChanged() {
        await this.reloadVisit();
    }

    goFrontDesk() {
        return this.action.doAction("dmag_clinic_workspace.action_dmag_frontdesk");
    }
}

registry.category("actions").add("dmag_doctor_desk", DoctorDesk);
