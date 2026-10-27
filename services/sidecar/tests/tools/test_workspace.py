"""默认工具、Agent 工作目录及命令取消回归。"""
import asyncio
import json
import os
import shlex
import sys
from pathlib import Path

import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage

from src import config
from src.agents import agent
from src.providers.llm.schemas import ModelSettings
from src.tools.workspace import agent_backend


@pytest.fixture(autouse=True)
def isolated_workspace(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "WORKSPACE_DIR", tmp_path / "workspace")


def test_every_agent_has_independent_deepagents_backend():
    for code in ("general", "product"):
        backend = agent_backend(code)
        assert backend.write("/notes.md", f"# {code}\nBattery 5000mAh").error is None
        assert code in str(backend.read("/notes.md").file_data)
        assert backend.edit("/notes.md", "5000mAh", "6000mAh").error is None
        assert any(row["path"].endswith("notes.md") for row in backend.glob("*.md").matches)
        assert backend.grep("6000mAh").matches
        assert backend.ls("/").entries
    assert "product" not in (config.WORKSPACE_DIR / "general/notes.md").read_text()


def test_deepagents_file_tools_reject_escape_and_symlinks():
    backend = agent_backend("general")
    (config.WORKSPACE_DIR / "private.txt").write_text("private-fixture")
    with pytest.raises(ValueError):
        backend.read("../private.txt")
    with pytest.raises(ValueError):
        backend.write("../overwrite.txt", "no")
    assert not (config.WORKSPACE_DIR / "overwrite.txt").exists()
    if os.name != "nt":
        (config.WORKSPACE_DIR / "general/link.txt").symlink_to(config.WORKSPACE_DIR / "private.txt")
        with pytest.raises(ValueError):
            backend.read("/link.txt")


def test_bash_workspace_output_limits_and_timeout():
    async def case():
        backend = agent_backend("general")
        result = await backend.aexecute("pwd")
        assert result.exit_code == 0
        assert Path(result.output.strip()).resolve() == (config.WORKSPACE_DIR / "general").resolve()
        result = await backend.aexecute("sleep 10", timeout=.15)
        assert result.exit_code == 124
        backend._max_output_bytes = 16
        result = await backend.aexecute("printf '%0100d' 0")
        assert result.truncated and result.output.startswith("0" * 16)
    asyncio.run(case())


@pytest.mark.skipif(os.name == "nt", reason="POSIX 进程组回归")
def test_bash_cancellation_kills_subprocesses(tmp_path):
    async def case():
        backend = agent_backend("general")
        marker = tmp_path / "pid"
        program = "import os,time;open(" + repr(str(marker)) + ",'w').write(str(os.getpid()));time.sleep(30)"
        command = shlex.quote(sys.executable) + " -c " + shlex.quote(program)
        task = asyncio.create_task(backend.aexecute(command))
        try:
            for _ in range(100):
                if marker.exists() and marker.read_text():
                    break
                await asyncio.sleep(.02)
            assert marker.exists()
            pid = int(marker.read_text())
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            for _ in range(50):
                try:
                    os.kill(pid, 0)
                except ProcessLookupError:
                    return
                await asyncio.sleep(.02)
            pytest.fail("命令子进程未随取消退出")
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
    asyncio.run(case())


def test_real_agent_runs_default_write_and_read_tools(monkeypatch):
    class ToolModel(FakeMessagesListChatModel):
        def bind_tools(self, tools, **kwargs):
            assert {"read_file", "write_file", "edit_file", "ls", "glob", "grep", "execute"}.issubset({item.name for item in tools})
            return self
    model = ToolModel(responses=[
        AIMessage(content="", tool_calls=[{"name": "write_file", "args": {"file_path": "report.md", "content": "默认工具已接入"}, "id": "write", "type": "tool_call"}]),
        AIMessage(content="", tool_calls=[{"name": "read_file", "args": {"file_path": "report.md"}, "id": "read", "type": "tool_call"}]),
        AIMessage(content="已保存并读取文档"),
    ])
    monkeypatch.setattr(agent, "create_model", lambda *_: model)
    async def case():
        body = agent.AgentRequest(agent_code="product", thread_id="tools-test", messages=[{"role": "user", "content": "保存并读取文档"}])
        events = [event async for event in agent.run_agent(body, ModelSettings(timeout=10))]
        assert events[-1]["type"] == "done", events
        assert (config.WORKSPACE_DIR / "product/report.md").read_text() == "默认工具已接入"
    asyncio.run(case())


def test_prompt_does_not_claim_rag_when_only_default_tools():
    prompt = agent.system_prompt("general")
    context = json.loads(prompt.split("<runtime_context>\n")[1].split("\n</runtime_context>")[0])
    assert "execute" in context["available_tools"]
    assert "search_knowledge" not in context["available_tools"]


def test_knowledge_tool_is_added_without_replacing_defaults(monkeypatch):
    from langchain_core.tools import tool
    from src.knowledge.rag import tool as rag_tools
    from src.transport.handlers import AgentInput
    @tool
    def search_knowledge(query: str) -> str:
        """检索测试资料。"""
        return "fixture"
    monkeypatch.setattr(rag_tools, "knowledge_tool", lambda token, client: search_knowledge)
    captured = []
    class ToolModel(FakeMessagesListChatModel):
        def bind_tools(self, tools, **kwargs):
            captured.extend(item.name for item in tools)
            return self
    monkeypatch.setattr(agent, "create_model", lambda *_: ToolModel(responses=[AIMessage("fixture")]))
    async def case():
        body = AgentInput(thread_id="knowledge-tools", messages=[{"role": "user", "content": "查资料"}],
            retrieval_token="fixture-token", knowledge_base_ids=[1])
        result = [event async for event in agent.run_agent(body, ModelSettings(timeout=10))]
        assert result[-1]["type"] == "done"
    asyncio.run(case())
    assert {"read_file", "write_file", "edit_file", "ls", "glob", "grep", "execute", "search_knowledge"}.issubset(set(captured))
