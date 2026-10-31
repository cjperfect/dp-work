"""百度通用文字识别高精度版，供隔离的 PDF 解析进程调用。"""
import base64
import time
from urllib.parse import urlencode

import httpx

from ... import config

TOKEN_URL = "https://aip.baidubce.com/oauth/2.0/token"
OCR_URL = "https://aip.baidubce.com/rest/2.0/ocr/v1/accurate_basic"
MAX_FORM_BYTES = 4 * 1024 * 1024


def image_form(image: bytes) -> bytes:
    """构造百度要求的 Base64 与表单编码。"""
    return urlencode({"image": base64.b64encode(image).decode("ascii"),
                      "detect_direction": "true", "language_type": "CHN_ENG"}).encode("ascii")


class BaiduOCR:
    """按文档复用 HTTP 连接及访问令牌，不在磁盘保存凭证。"""
    def __init__(self, client: httpx.Client):
        self.client = client
        self.token = ""
        self.expires_at = 0.0

    def _post(self, url, **kwargs) -> dict:
        """屏蔽包含凭证的网络异常及服务端原文。"""
        try:
            response = self.client.post(url, **kwargs)
            response.raise_for_status()
            value = response.json()
        except httpx.TimeoutException:
            raise ValueError("百度 OCR 请求超时，请稍后重试。") from None
        except (httpx.HTTPError, ValueError):
            raise ValueError("百度 OCR 服务连接失败或响应无效，请稍后重试。") from None
        if not isinstance(value, dict):
            raise ValueError("百度 OCR 返回数据格式无效。")
        return value

    def _access_token(self) -> str:
        """在当前解析任务内缓存令牌，过期前重新获取。"""
        if self.token and time.monotonic() < self.expires_at:
            return self.token
        if not config.BAIDU_OCR_API_KEY or not config.BAIDU_OCR_SECRET_KEY:
            raise ValueError("PDF 包含需要 OCR 的页面，请配置 BAIDU_OCR_API_KEY 和 BAIDU_OCR_SECRET_KEY。")
        data = self._post(TOKEN_URL, data={"grant_type": "client_credentials",
            "client_id": config.BAIDU_OCR_API_KEY, "client_secret": config.BAIDU_OCR_SECRET_KEY})
        token, lifetime = data.get("access_token"), data.get("expires_in")
        if not isinstance(token, str) or not token or type(lifetime) is not int or lifetime <= 0:
            raise ValueError("百度 OCR 鉴权失败，请检查 API Key 和 Secret Key。")
        self.token = token
        self.expires_at = time.monotonic() + max(0, lifetime - 60)
        return token

    def recognize(self, image: bytes) -> str:
        """识别单页图片；令牌失效只刷新一次，其余失败交由任务重试。"""
        body = image_form(image)
        if len(body) > MAX_FORM_BYTES:
            raise ValueError("PDF 页面图像过大，请降低分辨率后重试。")
        for attempt in range(2):
            data = self._post(OCR_URL, params={"access_token": self._access_token()},
                content=body, headers={"Content-Type": "application/x-www-form-urlencoded"})
            code = data.get("error_code")
            if code is not None and type(code) is not int:
                raise ValueError("百度 OCR 返回错误码格式无效。")
            if code in (110, 111) and attempt == 0:
                self.token = ""
                continue
            if code is not None:
                messages = {
                    6: "百度 OCR 未开通接口权限，请开通通用文字识别高精度版。",
                    17: "百度 OCR 调用额度已用尽，请检查控制台配额。",
                    18: "百度 OCR 请求过于频繁，请稍后重试。",
                    19: "百度 OCR 总调用额度已用尽，请检查控制台配额。",
                    110: "百度 OCR 访问令牌无效，请检查凭证。",
                    111: "百度 OCR 访问令牌已过期，请重试。",
                }
                raise ValueError(messages.get(code, "百度 OCR 识别失败，请检查服务权限、配额或稍后重试。"))
            rows = data.get("words_result")
            if not isinstance(rows, list) or any(not isinstance(row, dict) or not isinstance(row.get("words"), str) for row in rows):
                raise ValueError("百度 OCR 返回识别结果格式无效。")
            return "\n".join(row["words"] for row in rows).strip()
        raise ValueError("百度 OCR 识别失败，请稍后重试。")
