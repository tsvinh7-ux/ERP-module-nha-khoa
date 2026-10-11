"""Xóa sạch dữ liệu demo (gỡ module hoặc "Tạo lại dữ liệu demo").

Chỉ xóa bản ghi có external id ``dmag_dental_demo.gen_*`` (do bộ sinh dữ liệu tạo). Các chứng từ đã khóa theo
nguyên tắc "tạo được – không sửa" được đưa về trạng thái xóa được bằng ngữ cảnh quy trình (``dmag_workflow``)
hoặc xóa trực tiếp ở mức cơ sở dữ liệu (sổ cái, kho, nhật ký không xóa được qua giao diện).
"""
import json
import logging
import time

from odoo import SUPERUSER_ID, fields
from odoo.tools import mute_logger

from .generator import MODULE, PARAM_BACKUP, PARAM_INFO, PARAM_MODE, XMLID_PREFIX

_logger = logging.getLogger(__name__)

# Thứ tự xóa ưu tiên: chứng từ con trước, danh mục sau. Model không có trong danh sách xóa sau cùng.
ORDER = [
    'mail.activity', 'mail.mail', 'dmag.business.target',
    'dmag.pay3p.line', 'dmag.pay3p.sheet', 'dmag.kpi.result', 'dmag.competency.assessment.line',
    'dmag.competency.assessment',
    'dmag.commission.line', 'dmag.commission.statement',
    'dmag.loyalty.ledger', 'dmag.loyalty.voucher', 'dmag.care.usage', 'dmag.care.entitlement',
    'dmag.care.subscription',
    'dmag.nps.response', 'dmag.journey.execution', 'dmag.zns.webhook.event', 'dmag.zns.message',
    'dmag.warranty.claim', 'dmag.warranty.card',
    'dmag.material.usage',
    'dmag.lab.tryin', 'dmag.lab.order',
    'dmag.esign.log', 'dmag.esign.request',
    'dmag.rx.send.log', 'dmag.prescription.line', 'dmag.prescription',
    'dmag.payment.log', 'dmag.sepay.transaction', 'dmag.payment.request', 'dmag.cash.closing',
    'account.payment', 'account.move', 'account.bank.statement.line',
    'purchase.order.line', 'purchase.order',
    'sale.order.line', 'sale.order',
    'dmag.record.access.log', 'dmag.record.request', 'dmag.consent',
    'dmag.dental.chart.entry', 'dmag.dental.procedure',
    'dmag.treatment.plan.line', 'dmag.treatment.option', 'dmag.treatment.plan',
    'dmag.dental.visit',
    'stock.valuation.layer', 'stock.move.line', 'stock.move', 'stock.quant', 'stock.picking', 'stock.lot',
    'dmag.sterilization.batch', 'dmag.instrument.set', 'dmag.equipment.log', 'dmag.compliance.doc',
    'dmag.equipment',
    'dmag.service.bom.line', 'dmag.service.bom',
    'dmag.prescription.template.line', 'dmag.prescription.template', 'dmag.drug',
    'dmag.commission.tier', 'dmag.commission.rule', 'dmag.care.plan.line', 'dmag.care.plan',
    'dmag.rx.national.config', 'dmag.esign.provider', 'dmag.sepay.config',
    'hr.employee', 'resource.resource',
    'dmag.dental.practitioner', 'dmag.dental.chair',
    'res.users',
    'dmag.patient.family',
    'product.product', 'product.template', 'product.category',
    'res.partner',
]
# Xóa trực tiếp bằng SQL (ORM chặn xóa hoặc kéo theo nghiệp vụ phụ như tính lại hoa hồng)
SQL_FIRST = {'account.move', 'account.payment', 'dmag.loyalty.ledger', 'dmag.record.access.log',
             'stock.valuation.layer', 'stock.move.line', 'stock.move', 'stock.quant'}
# Chuẩn bị trước khi xóa qua ORM: đưa chứng từ về trạng thái xóa được (chỉ ngữ cảnh quy trình)
PREPARE = {
    'dmag.prescription': {'state': 'draft', 'name': False},
    'dmag.dental.procedure': {'state': 'draft'},
    'dmag.dental.visit': {'state': 'cancel'},
    'dmag.care.subscription': {'state': 'draft'},
    'dmag.commission.statement': {'state': 'draft'},
    'dmag.pay3p.sheet': {'state': 'draft'},
    'dmag.competency.assessment': {'state': 'draft'},
    'dmag.lab.order': {'state': 'draft'},
    'sale.order': {'state': 'cancel'},
    'purchase.order': {'state': 'cancel'},
    'stock.picking': {'state': 'cancel'},
}


class DemoPurger:

    def __init__(self, env):
        ctx = dict(env.context, dmag_workflow=True, dmag_demo_purge=True, force_delete=True, active_test=False,
                   tracking_disable=True, mail_notrack=True, dmag_journey_disable=True)
        self.env = env(user=SUPERUSER_ID, su=True, context=ctx)
        self.deleted = 0

    def _demo_data(self):
        Data = self.env['ir.model.data']
        rows = Data.search_read([('module', '=', MODULE), ('name', '=like', XMLID_PREFIX + '%')],
                                ['model', 'res_id'])
        by_model = {}
        for row in rows:
            by_model.setdefault(row['model'], set()).add(row['res_id'])
        return by_model

    def run(self):
        t0 = time.time()
        self.restore_backup()
        by_model = self._demo_data()
        total = sum(len(ids) for ids in by_model.values())
        if not by_model:
            self._clear_params()
            return 0
        models = [m for m in ORDER if m in by_model] + sorted(m for m in by_model if m not in ORDER)
        for _pass in range(4):
            progress = False
            for model in models:
                ids = by_model.get(model)
                if not ids or model not in self.env:
                    continue
                remaining = self._delete(model, sorted(ids))
                if len(remaining) != len(ids):
                    progress = True
                by_model[model] = set(remaining)
            if not any(by_model.values()) or not progress:
                break
        left = {m: len(ids) for m, ids in by_model.items() if ids}
        if left:
            _logger.warning('DMAG demo: còn bản ghi demo chưa xóa được: %s', left)
        self.deleted = total - sum(left.values())
        self._cleanup_xmlids()
        self._clear_params()
        self.env.invalidate_all()
        _logger.info('DMAG demo: đã xóa %s bản ghi demo trong %.1fs', self.deleted, time.time() - t0)
        return self.deleted

    # ------------------------------------------------------------------ deletion
    def _existing(self, model, ids):
        Model = self.env[model]
        self.env.cr.execute('SELECT id FROM "%s" WHERE id = ANY(%%s)' % Model._table, [list(ids)])  # noqa: S608
        return [r[0] for r in self.env.cr.fetchall()]

    def _transient_refs(self):
        """{model: [(bảng tạm, cột)]} – bản ghi wizard (TransientModel) trỏ tới dữ liệu demo."""
        if not hasattr(self, '_trefs'):
            refs = {}
            for name in self.env.registry.models:
                Model = self.env.registry[name]
                if not Model._transient or not Model._auto:
                    continue
                for field in Model._fields.values():
                    if field.type == 'many2one' and field.store and not field.inherited:
                        refs.setdefault(field.comodel_name, []).append((Model._table, field.name))
            self._trefs = refs
        return self._trefs

    def _delete(self, model, ids):
        ids = self._existing(model, ids)
        if not ids:
            return []
        for table, column in self._transient_refs().get(model, []):
            self.env.cr.execute('DELETE FROM "%s" WHERE "%s" = ANY(%%s)' % (table, column), [ids])  # noqa: S608
        if model not in SQL_FIRST:
            if self._orm_delete(model, ids):
                return []
            # thử từng bản ghi (bản ghi phụ thuộc chưa xóa sẽ còn lại cho lượt sau)
            if len(ids) <= 200:
                left = [rid for rid in ids if not self._orm_delete(model, [rid])]
                if not left:
                    return []
                ids = left
        return [rid for rid in ids if rid in set(self._sql_delete(model, ids))]

    def _orm_delete(self, model, ids):
        records = self.env[model].browse(ids)
        try:
            with mute_logger('odoo.sql_db'), self.env.cr.savepoint():
                vals = {k: v for k, v in PREPARE.get(model, {}).items() if k in records._fields}
                if vals:
                    records.write(vals)
                if model == 'dmag.dental.visit':
                    records.invalidate_recordset(['retention_until'])
                if model == 'res.users':
                    records.write({'active': False})
                records.unlink()
                self.env.flush_all()
        except Exception as exc:  # noqa: BLE001
            _logger.debug('DMAG demo purge: ORM unlink %s(%s) failed: %s', model, len(ids), exc)
            self.env.invalidate_all()
            return False
        self.deleted += len(ids)
        return True

    def _sql_delete(self, model, ids):
        """Xóa mức CSDL. Trả về các id CHƯA xóa được (ràng buộc khóa ngoại với dữ liệu còn lại)."""
        Model = self.env[model]
        cr = self.env.cr
        self.env.flush_all()
        try:
            with mute_logger('odoo.sql_db'), cr.savepoint():
                if model == 'account.move':
                    cr.execute('SELECT id FROM account_move_line WHERE move_id = ANY(%s)', [ids])
                    line_ids = [r[0] for r in cr.fetchall()]
                    if line_ids:
                        cr.execute('SELECT DISTINCT full_reconcile_id FROM account_move_line '
                                   'WHERE id = ANY(%s) AND full_reconcile_id IS NOT NULL', [line_ids])
                        full_ids = [r[0] for r in cr.fetchall()]
                        cr.execute('DELETE FROM account_partial_reconcile WHERE debit_move_id = ANY(%s) '
                                   'OR credit_move_id = ANY(%s)', [line_ids, line_ids])
                        if full_ids:
                            cr.execute('UPDATE account_move_line SET full_reconcile_id = NULL '
                                       'WHERE full_reconcile_id = ANY(%s)', [full_ids])
                            cr.execute('DELETE FROM account_full_reconcile WHERE id = ANY(%s)', [full_ids])
                    cr.execute('DELETE FROM account_payment WHERE move_id = ANY(%s)', [ids])
                    cr.execute('DELETE FROM account_move_line WHERE move_id = ANY(%s)', [ids])
                cr.execute('DELETE FROM "%s" WHERE id = ANY(%%s)' % Model._table, [ids])  # noqa: S608
                self._cleanup_mail(model, ids)
        except Exception as exc:  # noqa: BLE001
            _logger.debug('DMAG demo purge: SQL delete %s failed: %s', model, exc)
            if len(ids) == 1:
                return ids
            half = len(ids) // 2
            return self._sql_delete(model, ids[:half]) + self._sql_delete(model, ids[half:])
        self.deleted += len(ids)
        self.env.invalidate_all()
        return []

    def _cleanup_mail(self, model, ids):
        cr = self.env.cr
        for table, column in (('mail_message', 'model'), ('mail_followers', 'res_model'),
                              ('mail_activity', 'res_model'), ('ir_attachment', 'res_model')):
            cr.execute('DELETE FROM %s WHERE %s = %%s AND res_id = ANY(%%s)' % (table, column),  # noqa: S608
                       [model, ids])

    def _cleanup_xmlids(self):
        """Xóa external id của bản ghi đã xóa."""
        cr = self.env.cr
        Data = self.env['ir.model.data']
        rows = Data.search_read([('module', '=', MODULE), ('name', '=like', XMLID_PREFIX + '%')],
                                ['model', 'res_id'])
        by_model = {}
        for row in rows:
            by_model.setdefault(row['model'], []).append(row['res_id'])
        for model, ids in by_model.items():
            if model not in self.env:
                gone = ids
            else:
                existing = set(self._existing(model, ids))
                gone = [rid for rid in ids if rid not in existing]
            if gone:
                cr.execute('DELETE FROM ir_model_data WHERE module = %s AND model = %s AND res_id = ANY(%s) '
                           'AND name LIKE %s', [MODULE, model, gone, XMLID_PREFIX + '%'])
        self.env.registry.clear_cache()

    # ------------------------------------------------------------------ settings backup
    def restore_backup(self):
        ICP = self.env['ir.config_parameter']
        backup = json.loads(ICP.get_param(PARAM_BACKUP) or '{}')
        for key, vals in backup.items():
            model, res_id = key.split(',')
            if model not in self.env:
                continue
            record = self.env[model].browse(int(res_id)).exists()
            if not record:
                continue
            clean = {}
            for fname, value in vals.items():
                field = record._fields.get(fname)
                if not field:
                    continue
                if field.type == 'many2one' and value and not self.env[field.comodel_name].browse(value).exists():
                    value = False
                clean[fname] = value
            try:
                with self.env.cr.savepoint():
                    record.write(clean)
            except Exception as exc:  # noqa: BLE001
                _logger.warning('DMAG demo: không khôi phục được %s: %s', key, exc)
        ICP.set_param(PARAM_BACKUP, False)

    def _clear_params(self):
        ICP = self.env['ir.config_parameter']
        for key in (PARAM_MODE, PARAM_INFO):
            ICP.set_param(key, False)
        self.env['ir.config_parameter'].flush_model()


def purge_demo(env):
    return DemoPurger(env).run()


def generate_demo(env):
    from .generator import DemoGenerator
    return DemoGenerator(env).run()


def regenerate_demo(env):
    """Xóa dữ liệu demo cũ rồi sinh lại (idempotent)."""
    purge_demo(env)
    env.invalidate_all()
    stats = generate_demo(env)
    _logger.info('DMAG demo: tạo lại lúc %s', fields.Datetime.now())
    return stats
