"""连接器可安全展示的业务错误。"""
from enum import IntEnum


class ConnectorCode(IntEnum):
    INTERNAL_ERROR = 5000
    STATE_CONFLICT = 4090


class ConnectorError(Exception):
    def __init__(self, code, message, status_code=400):
        super().__init__(message)
        self.code, self.message, self.status_code = code, message, status_code
