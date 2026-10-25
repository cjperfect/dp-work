"""旧库基线表结构定义。"""

from sqlalchemy import MetaData

from app.modules.users.models import User


def legacy_schema_metadata():
    """获取旧库基线表结构。"""
    metadata = MetaData()
    User.__table__.to_metadata(metadata)
    return metadata
