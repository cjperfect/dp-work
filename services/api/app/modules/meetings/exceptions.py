from app.core.exceptions import ApiError
from app.core.responses import ApiCode


class MinutesNotReadyError(ApiError):
    def __init__(self):
        super().__init__(ApiCode.MINUTES_NOT_READY, "会议纪要尚未生成", 404)
