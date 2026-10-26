"""保留标题层级的父子分块，子块召回、父块提供上下文。"""
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter
from .embedding import EmbeddingError


def split_document(content: str, metadata: list[dict] | None = None) -> list[dict]:
    """按标题分组，再拆分为父块和带重叠的子块。"""
    if not content.strip():
        raise EmbeddingError("解析正文为空，不能向量化。")
    headers = MarkdownHeaderTextSplitter(headers_to_split_on=[("#", "h1"), ("##", "h2"), ("###", "h3")], strip_headers=False)
    parent_splitter = RecursiveCharacterTextSplitter(chunk_size=2000, chunk_overlap=200, add_start_index=True,
        separators=["\n\n", "\n", "。", "！", "？", "；", " ", ""])
    child_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=80, add_start_index=True,
        separators=["\n\n", "\n", "。", "！", "？", "；", " ", ""])
    parents = []
    total = 0
    for section in headers.split_text(content):
        for parent in parent_splitter.split_documents([section]):
            text = parent.page_content
            meta = {"headings": [parent.metadata[key] for key in ("h1", "h2", "h3") if key in parent.metadata]}
            # 人工修订后仅在正文仍能精确对应某页时附加页码，不猜测页码。
            for page in metadata or []:
                if isinstance(page.get("content"), str) and text.strip() in page["content"]:
                    number = page.get("page_number")
                    if type(number) is int and number > 0:
                        meta["page"] = number
                        break
            children = [{"content": child.page_content, "start": child.metadata["start_index"]}
                        for child in child_splitter.create_documents([text])]
            total += len(children)
            parents.append({"content": text, "metadata": meta, "children": children})
            if total > 4096:
                raise EmbeddingError("文档超过 4096 个子块，请拆分文档后重试。")
    if not parents:
        raise EmbeddingError("没有可向量化的正文。")
    return parents
