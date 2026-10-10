"""Nguyên tắc phân quyền DMAG: "tạo được – không sửa".

* Lễ tân / Phụ tá / Bác sĩ được TẠO chứng từ (lịch hẹn, ghi nhận, thủ thuật, kế hoạch,
  thanh toán) nhưng không được SỬA hay XÓA sau khi chứng từ đã có hiệu lực.
* Chỉ Giám đốc / Quản lý cấp cao (group_dmag_director) được sửa dữ liệu tài chính,
  mở khóa bệnh án đã ký, duyệt giảm giá vượt hạn mức, hủy chứng từ – mọi thao tác đều ghi vết.
* Các thay đổi do quy trình hệ thống (nút bấm theo luồng) chạy với context
  ``dmag_workflow=True`` để không bị chặn.
"""
from odoo import _
from odoo.exceptions import AccessError

DIRECTOR_GROUP = 'dmag_dental_base.group_dmag_director'
MANAGER_GROUP = 'dmag_dental_base.group_dmag_manager'


def is_director(env):
    return env.su or env.user.has_group(DIRECTOR_GROUP)


def is_manager(env):
    return env.su or env.user.has_group(MANAGER_GROUP)


def is_workflow(env):
    return bool(env.context.get('dmag_workflow'))


def check_director(env, message=None):
    if not is_director(env):
        raise AccessError(message or _(
            'Thao tác này chỉ dành cho Giám đốc / Quản lý cấp cao. '
            'Nhân viên được tạo chứng từ nhưng không được sửa hoặc xóa sau khi đã ghi nhận.'))


def check_discount(env, discount, company):
    """Giảm giá vượt hạn mức phòng khám cần Giám đốc."""
    limit = company.dmag_max_discount if company else 0.0
    if discount and discount > limit and not is_director(env):
        raise AccessError(_(
            'Giảm %(disc)s%% vượt hạn mức %(limit)s%% của phòng khám – cần Giám đốc / Quản lý cấp cao duyệt.',
            disc=discount, limit=limit))
