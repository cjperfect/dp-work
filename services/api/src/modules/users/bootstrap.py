"""初始化管理员；通过唯一约束支持重复启动与多个实例同时启动。"""

import logging

from src.core import config

from . import service

log = logging.getLogger(__name__)


async def ensure_initial_admin() -> None:
    """初始化管理员账号。"""
    if not config.BOOTSTRAP_ADMIN_ENABLED:
        return
    user = await service.create_user(
        username=config.BOOTSTRAP_ADMIN_USERNAME,
        password=config.BOOTSTRAP_ADMIN_PASSWORD,
        department="platform",
        role="admin",
        allow_existing=True,
    )
    if user.role != "admin":
        log.warning("初始化管理员账号 %s 已存在且不是管理员，保留原账号", user.username)
