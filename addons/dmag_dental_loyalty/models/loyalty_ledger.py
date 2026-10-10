from psycopg2 import IntegrityError

from odoo import _, api, fields, models
from odoo.tools import mute_logger
from odoo.exceptions import AccessError, UserError

from odoo.addons.dmag_dental_base.models.dmag_access import check_director, is_workflow

REASONS = [
    ('payment', 'Thanh toán'),
    ('recall', 'Tái khám đúng hẹn'),
    ('referral', 'Giới thiệu thành công'),
    ('survey', 'Khảo sát / NPS'),
    ('redemption', 'Đổi điểm'),
    ('adjustment', 'Điều chỉnh'),
]
# Điểm "gắn bó" dùng để xét hạng (không tính điểm từ chi tiêu)
ENGAGEMENT_REASONS = ('recall', 'referral', 'survey')


class DmagLoyaltyLedger(models.Model):
    """Sổ điểm – chỉ ghi thêm, không sửa / xóa.

    Mỗi bút toán có ``source_key`` duy nhất để bảo đảm tính lũy đẳng
    (một khoản thanh toán / một lượt giới thiệu chỉ được cộng điểm một lần).
    """
    _name = 'dmag.loyalty.ledger'
    _description = 'Sổ điểm khách hàng thân thiết'
    _order = 'date desc, id desc'

    partner_id = fields.Many2one('res.partner', string='Bệnh nhân', required=True, index=True,
                                 ondelete='restrict', readonly=True)
    family_id = fields.Many2one('dmag.patient.family', string='Nhóm gia đình', readonly=True, index=True,
                                help='Nhóm gia đình tại thời điểm ghi sổ.')
    company_id = fields.Many2one('res.company', string='Phòng khám', required=True, readonly=True,
                                 default=lambda self: self.env.company, index=True)
    points = fields.Integer('Điểm', required=True, readonly=True)
    reason = fields.Selection(REASONS, string='Lý do', required=True, readonly=True, index=True)
    source_ref = fields.Reference(selection='_selection_source_ref', string='Chứng từ nguồn', readonly=True)
    source_key = fields.Char('Khóa nguồn', readonly=True, index=True, copy=False,
                             help='Khóa chống ghi trùng (ví dụ payment:123).')
    note = fields.Char('Diễn giải', readonly=True)
    date = fields.Datetime('Thời điểm', required=True, readonly=True, default=fields.Datetime.now)
    user_id = fields.Many2one('res.users', string='Người ghi', readonly=True,
                              default=lambda self: self.env.user)
    amount = fields.Monetary('Số tiền liên quan', readonly=True, currency_field='currency_id')
    currency_id = fields.Many2one(related='company_id.currency_id')

    _sql_constraints = [
        ('source_key_uniq', 'unique(source_key)', 'Bút toán điểm cho chứng từ này đã được ghi.'),
    ]

    @api.model
    def _selection_source_ref(self):
        return [
            ('account.payment', 'Thanh toán'),
            ('dmag.dental.visit', 'Lượt khám'),
            ('res.partner', 'Bệnh nhân'),
            ('dmag.loyalty.voucher', 'Voucher'),
            ('dmag.care.subscription', 'Gói chăm sóc'),
            ('dmag.nps.response', 'Khảo sát NPS'),
        ]

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su and not is_workflow(self.env):
            # Nhập tay: chỉ Giám đốc, chỉ loại "Điều chỉnh"
            check_director(self.env, _('Chỉ Giám đốc / Quản lý cấp cao được điều chỉnh điểm.'))
            for vals in vals_list:
                if vals.get('reason') != 'adjustment':
                    raise AccessError(_('Điểm chỉ được ghi tự động theo nghiệp vụ; nhập tay chỉ cho "Điều chỉnh".'))
        for vals in vals_list:
            if vals.get('partner_id') and 'family_id' not in vals:
                vals['family_id'] = self.env['res.partner'].browse(vals['partner_id']).sudo().dental_family_id.id
        return super().create(vals_list)

    def write(self, vals):
        raise UserError(_('Sổ điểm chỉ ghi thêm – không sửa được. Hãy tạo bút toán điều chỉnh.'))

    def unlink(self):
        raise UserError(_('Sổ điểm chỉ ghi thêm – không xóa được. Hãy tạo bút toán điều chỉnh.'))

    @api.model
    def _dmag_earn(self, partner, reason, points, source=None, key=None, note=None, amount=0.0, company=None):
        """Ghi điểm (lũy đẳng theo ``key``). Trả về bút toán mới hoặc bản ghi rỗng nếu đã ghi."""
        points = int(points or 0)
        if not partner or not points:
            return self.browse()
        Ledger = self.sudo()
        if key and Ledger.search_count([('source_key', '=', key)], limit=1):
            return self.browse()
        vals = {
            'partner_id': partner.id,
            'points': points,
            'reason': reason,
            'source_key': key or False,
            'note': note or False,
            'amount': amount or 0.0,
            'company_id': (company or partner.company_id or self.env.company).id,
            'user_id': self.env.user.id,
        }
        if source:
            vals['source_ref'] = '%s,%s' % (source._name, source.id)
        # Hai giao dịch song song: ràng buộc unique(source_key) chặn ghi trùng
        try:
            with self.env.cr.savepoint(), mute_logger('odoo.sql_db'):
                return Ledger.create(vals)
        except IntegrityError:
            return self.browse()

    def _ledger_dict(self):
        return [{
            'id': entry.id,
            'date': fields.Datetime.to_string(entry.date),
            'points': entry.points,
            'reason': entry.reason,
            'reason_label': dict(REASONS).get(entry.reason),
            'note': entry.note or '',
            'partner': entry.partner_id.name,
        } for entry in self]
