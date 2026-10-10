import logging

from .generator import generate_demo, purge_demo

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    """Cài module → biến cơ sở dữ liệu thành môi trường demo: giả lập tích hợp + sinh dữ liệu mẫu."""
    _logger.info('DMAG demo: bắt đầu sinh dữ liệu demo cho %s', env.cr.dbname)
    purge_demo(env)  # lần cài lại sau khi gỡ dở dang: dọn trước
    generate_demo(env)


def uninstall_hook(env):
    """Gỡ module → xóa toàn bộ dữ liệu demo đã sinh và khôi phục cấu hình tích hợp cũ."""
    purge_demo(env)
