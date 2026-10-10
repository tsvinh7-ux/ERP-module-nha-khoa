"""In ấn khi máy chủ có / không có wkhtmltopdf.

Có wkhtmltopdf → mở PDF. Không có → mở bản HTML của báo cáo (đúng khổ giấy nhờ CSS @page) kèm nút "In" dùng
hộp thoại in của trình duyệt (chọn máy in hoặc "Lưu thành PDF").
"""
from odoo.addons.base.models import ir_actions_report


def pdf_available():
    return ir_actions_report.wkhtmltopdf_state in ('ok', 'upgrade')


def report_url(report_name, ids):
    ids = ids if isinstance(ids, (list, tuple)) else [ids]
    kind = 'pdf' if pdf_available() else 'html'
    return '/report/%s/%s/%s' % (kind, report_name, ','.join(str(i) for i in ids))
