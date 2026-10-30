"""Agent 飞书业务工具；固定命令、账号隔离，不开放任意 CLI。"""
import asyncio
import json
import re
import tempfile
from pathlib import Path

from langchain_core.tools import tool
from . import cli, service
from .errors import ConnectorError


def business_tools(owner):
    """仅对已授权账号挂载业务工具。"""
    if type(owner) is not int or owner <= 0 or not cli.binary():
        return []
    connection = cli.read_connection(owner)
    if not connection.get('last_verified_at'):
        return []

    async def invoke(*args):
        try:
            if not (await service.status(owner))['connected']:
                return '飞书授权已失效，请在连接器页面重新授权。'
            result = await cli.run(owner, *args, timeout=45)
            text = json.dumps(result, ensure_ascii=False)
            return text[:30000] + ('\n[返回内容已截断，可缩小查询范围]' if len(text) > 30000 else '')
        except ConnectorError:
            return '飞书操作失败，请检查文档访问权限、应用权限及用户授权；可在连接器重新授权文档与云空间权限。写入结果可能未知，请先搜索核验，勿直接重复创建。'

    @tool
    async def feishu_search_documents(query: str) -> str:
        """搜索当前授权用户可访问的飞书文档，返回文档标识及链接。query 最多30字。"""
        if not query.strip() or len(query) > 30:
            return '请输入1到30字的搜索内容。'
        return await invoke('drive', '+search', '--as', 'user', '--query', query, '--page-size', '10', '--json')

    @tool
    async def feishu_read_document(document: str) -> str:
        """读取飞书文档 Markdown，document 为搜索结果中的文档 token 或 HTTPS 飞书链接。"""
        if not re.fullmatch(r'[A-Za-z0-9]{8,256}', document) and not cli.safe_url(document):
            return '请输入有效的飞书文档链接或文档 token。'
        return await invoke('docs', '+fetch', '--as', 'user', '--doc', document, '--doc-format', 'markdown')

    @tool
    async def feishu_create_document(title: str, content: str) -> str:
        """创建飞书 Markdown 文档；执行前需要人工审批，返回新文档链接。"""
        if not title.strip() or len(title) > 200 or len(content) > 50000:
            return '文档标题不能为空且最多200字，正文最多50000字。'
        # 仅将内容写入受控临时文件，避免 CLI 将 @ 开头正文解释为任意本机路径。
        with tempfile.TemporaryDirectory(prefix='feishu-doc-', dir=cli.profile(owner)) as directory:
            file = Path(directory) / 'content.md'
            await asyncio.to_thread(file.write_text, content, encoding='utf-8')
            return await invoke('docs', '+create', '--as', 'user', '--title', title,
                                '--doc-format', 'markdown', '--content', '@' + str(file))

    return [feishu_search_documents, feishu_read_document, feishu_create_document]
