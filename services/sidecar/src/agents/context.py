"""从各 Agent 工作区读取提示词并附加运行上下文。"""
import json
import os
import tempfile
from threading import Lock
from pathlib import Path

from ..providers.llm.schemas import ModelError
from ..tools.workspace import agent_workspace

DEFAULT_TOOLS = {"ls", "read_file", "write_file", "edit_file", "glob", "grep", "execute"}
TEMPLATES = Path(__file__).resolve().parent / "templates"
MAX_PROMPT_BYTES = 64 * 1024
PROMPT_LOCK = Lock()


def read_prompt(code: str) -> str:
    """初始化时保留已有文件，每次运行重新读取当前 Agent 的提示词。"""
    workspace = agent_workspace(code)
    file = workspace / "AGENT.md"
    try:
        if file.is_symlink():
            raise ValueError("AGENT.md 不能使用符号链接")
        if not file.exists():
            template = (TEMPLATES / code / "AGENT.md").read_text(encoding="utf-8")
            try:
                with file.open("x", encoding="utf-8") as output:
                    output.write(template)
            except FileExistsError:
                pass
        with file.open("rb") as source:
            raw = source.read(MAX_PROMPT_BYTES + 1)
        if len(raw) > MAX_PROMPT_BYTES:
            raise ValueError("AGENT.md 不能超过 64 KB")
        prompt = raw.decode("utf-8").strip()
        if not prompt:
            raise ValueError("AGENT.md 不能为空")
    except (OSError, UnicodeError, ValueError) as cause:
        raise ModelError("AGENT_PROMPT_INVALID", f"无法读取 {code}/AGENT.md，请检查文件内容及权限。") from cause
    return prompt


def system_prompt(code: str, tool_names: set[str] | None = None) -> str:
    """将当前工作区提示词与实际工具信息装配为系统上下文。"""
    prompt = read_prompt(code)
    context = {"agent_code": code, "available_tools": sorted(DEFAULT_TOOLS | (tool_names or set()))}
    return prompt + "\n\n<runtime_context>\n" + json.dumps(context, ensure_ascii=False) + "\n</runtime_context>"


def save_prompt(code: str, prompt: str, expected_prompt: str) -> str:
    """校验旧内容后原子替换提示词，避免失败时留下半写入文件。"""
    prompt = prompt.strip()
    if not prompt or len(prompt.encode("utf-8")) > MAX_PROMPT_BYTES:
        raise ModelError("AGENT_PROMPT_INVALID", "提示词不能为空，且不能超过 64 KB。")
    with PROMPT_LOCK:
        if read_prompt(code) != expected_prompt:
            raise ModelError("AGENT_PROMPT_CONFLICT", "提示词已被修改，请重新加载后再编辑。")
        file = agent_workspace(code) / "AGENT.md"
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=file.parent,
                                             prefix=".agent-", suffix=".tmp", delete=False) as output:
                temporary = Path(output.name)
                output.write(prompt + "\n")
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, file)
        except OSError as cause:
            raise ModelError("AGENT_PROMPT_SAVE_FAILED", "提示词保存失败，请检查文件权限后重试。") from cause
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    return prompt
