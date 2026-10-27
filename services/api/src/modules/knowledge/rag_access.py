"""检索 Tool 的短时、最小范围授权。"""
import time
import jwt
from src.core import config
from src.core.exceptions import ApiError
from src.core.responses import ApiCode
from src.modules.users import service as users
from .rag import index_coverage, search_vector


def issue_capability(owner_id: int, base_ids: list[int]):
    """固定用户与知识库范围，不向 Sidecar 暴露用户登录令牌。"""
    return jwt.encode({"sub": str(owner_id), "bases": sorted(set(base_ids)), "aud": "knowledge-retrieval",
                       "exp": int(time.time()) + 240}, config.JWT_SECRET, algorithm=config.JWT_ALG)


async def authorized_scope(capability: str):
    """验证短时权限，并重新校验用户及知识库状态。"""
    try:
        payload = jwt.decode(capability, config.JWT_SECRET, algorithms=[config.JWT_ALG], audience="knowledge-retrieval",
                             options={"require": ["sub", "bases", "exp", "aud"]})
        owner_id = int(payload["sub"])
        bases = payload["bases"]
        if not isinstance(bases, list) or not 1 <= len(bases) <= 20 or any(type(value) is not int or value <= 0 for value in bases):
            raise ValueError("invalid scope")
    except (jwt.InvalidTokenError, ValueError, TypeError) as cause:
        raise ApiError(ApiCode.UNAUTHORIZED, "检索授权无效或已过期。", 401) from cause
    user = await users.find_by_id(owner_id)
    if user is None or not user.is_active:
        raise ApiError(ApiCode.UNAUTHORIZED, "账号不存在或已停用。", 401)
    return owner_id, bases


async def retrieve(capability: str, vector: list[float], profile: str, top_k: int):
    """在短时授权范围内检索父块。"""
    owner_id, bases = await authorized_scope(capability)
    return await search_vector(owner_id, bases, vector, profile, top_k)


async def retrieve_with_status(capability: str, vector: list[float] | None, profile: str, top_k: int, query: str = ""):
    """向 Agent 明确报告尚未向量化的文档，避免误判为资料不存在。"""
    owner_id, bases = await authorized_scope(capability)
    coverage = await index_coverage(owner_id, bases, profile)
    retrieval = None
    retrieval_message = ""
    if query.strip():
        from .hybrid import search as search_hybrid
        result = await search_hybrid(owner_id, bases, query, vector, profile, top_k)
        sources, retrieval, retrieval_message = result["sources"], result["retrieval"], result["message"]
    else:
        sources = await search_vector(owner_id, bases, vector, profile, top_k) if coverage["ready"] and vector is not None else []
    message = ""
    if not coverage["total"]:
        message = "当前关联的知识库还没有文档。"
    elif not coverage["ready"] and not sources:
        message = "关联知识库中的文档尚未完成向量化，当前无法检索。请先在文档列表或详情页点击向量化；不能据此断言文档中没有相关内容。"
    elif coverage["not_ready"]:
        message = "部分文档尚未完成向量化，本次只检索已完成向量化的文档。"
    return {"sources": sources, "coverage": coverage, "retrieval": retrieval, "message": message + retrieval_message}
