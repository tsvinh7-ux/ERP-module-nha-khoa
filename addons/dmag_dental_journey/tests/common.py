from datetime import datetime, timedelta

import pytz

from odoo import fields

from odoo.addons.dmag_dental_clinic.tests.common import DentalCommon


class JourneyCommon(DentalCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.company = env.company
        cls.company.partner_id.tz = 'Asia/Ho_Chi_Minh'
        Users = env['res.users'].with_context(no_reset_password=True)
        cls.cskh_user = Users.create({
            'name': 'CSKH Một', 'login': 'cskh_mot', 'email': 'cskh@dmag.test',
            'groups_id': [(6, 0, [env.ref('dmag_dental_base.group_dmag_receptionist').id])],
        })
        cls.lead_user = Users.create({
            'name': 'Trưởng CSKH', 'login': 'truong_cskh', 'email': 'lead@dmag.test',
            'groups_id': [(6, 0, [env.ref('dmag_dental_base.group_dmag_manager').id])],
        })
        cls.company.write({
            'dmag_zns_mode': 'mock',
            'dmag_zns_quiet_start': 0.0,
            'dmag_zns_quiet_end': 0.0,
            'dmag_cskh_user_id': cls.cskh_user.id,
            'dmag_cskh_lead_user_id': cls.lead_user.id,
            'dmag_google_review_url': 'https://g.page/r/dmag-test/review',
        })
        cls.patient.write({'mobile': '0912345678'})
        cls.Rule = env['dmag.journey.rule']
        cls.Message = env['dmag.zns.message']
        cls.Execution = env['dmag.journey.execution']

    def _set_quiet_now(self):
        tz = pytz.timezone('Asia/Ho_Chi_Minh')
        hour = pytz.utc.localize(datetime.utcnow()).astimezone(tz).hour
        self.company.write({'dmag_zns_quiet_start': float(hour), 'dmag_zns_quiet_end': float((hour + 2) % 24)})

    def _shift(self, visit, **values):
        """Ghi trực tiếp mốc thời gian (giả lập thời gian đã trôi qua)."""
        sets = ', '.join('%s = %%s' % k for k in values)
        self.env.cr.execute('UPDATE dmag_dental_visit SET %s WHERE id = %%s' % sets, (*values.values(), visit.id))
        visit.invalidate_recordset()

    def _done_visit(self, **kw):
        visit = self._visit(**kw)
        visit.action_confirm()
        visit.action_check_in()
        visit.action_start()
        visit.action_done()
        return visit

    def _messages(self, visit, code):
        return self.Message.search([('res_model', '=', 'dmag.dental.visit'), ('res_id', '=', visit.id),
                                    ('template_id.code', '=', code)])

    def _execs(self, rule_xmlid, **domain):
        rule = self.env.ref('dmag_dental_journey.%s' % rule_xmlid)
        dom = [('rule_id', '=', rule.id)] + [(k, '=', v) for k, v in domain.items()]
        return self.Execution.search(dom)

    @staticmethod
    def _now():
        return fields.Datetime.now().replace(microsecond=0)

    @staticmethod
    def _ago(**kw):
        return fields.Datetime.now().replace(microsecond=0) - timedelta(**kw)
