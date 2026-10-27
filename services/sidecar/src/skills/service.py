"""从 skills.sh 发现公开技能，按 Agent 安装标准 SKILL.md 目录。"""
import asyncio
import io
import json
import logging
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tempfile
from urllib.parse import urlsplit
import zipfile

import httpx
import yaml

from .. import config
from ..tools.workspace import agent_workspace

log = logging.getLogger(__name__)

SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
REPOSITORY = re.compile(r"[A-Za-z0-9_-]+/(?!\.{1,2}\Z)[A-Za-z0-9_.-]+\Z")
LOCKS: dict[str, asyncio.Lock] = {}
MAX_ARCHIVE = 32 * 1024 * 1024
FRONTMATTER = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.S)


class SkillError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


async def file_operation(function, *args):
    """在线程执行文件操作；取消时等待线程收尾，避免提前释放安装锁。"""
    task = asyncio.create_task(asyncio.to_thread(function, *args))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                continue
            except Exception:
                break
        if not task.cancelled():
            task.exception()
        raise


def skill_directory(agent_code):
    """仅在当前 Agent 的 workspace 中维护技能。"""
    root = agent_workspace(agent_code) / "skills"
    if root.is_symlink():
        raise SkillError("技能目录不能使用符号链接。")
    root.mkdir(exist_ok=True, mode=0o700)
    return root


def metadata(content):
    """校验 Deep Agents 能加载的标准技能元数据。"""
    if len(content) > 256 * 1024:
        raise SkillError("SKILL.md 不能超过 256 KB。")
    try:
        text = content.decode("utf-8")
        header = FRONTMATTER.match(text)
        data = yaml.safe_load(header.group(1)) if header else None
        name, description = data["name"], data["description"]
        if (not isinstance(name, str) or not SLUG.fullmatch(name) or len(name) > 64
                or not isinstance(description, str) or not description.strip() or len(description) > 1024):
            raise ValueError()
        return {"name": name, "description": description.strip()}
    except (UnicodeError, ValueError, TypeError, KeyError, yaml.YAMLError) as cause:
        raise SkillError("SKILL.md 需要合法的 name 和 description，名称应为小写字母、数字与横杠。") from cause


def parse_source(source):
    """接受 skills.sh 链接或 owner/repo@skill，拒绝任意下载地址。"""
    source = source.strip()
    if source.startswith("https://"):
        try:
            url = urlsplit(source)
            port = url.port
        except ValueError as cause:
            raise SkillError("技能来源链接无效。") from cause
        if url.hostname not in {"skills.sh", "www.skills.sh"} or url.username or url.password or port:
            raise SkillError("请使用 skills.sh 技能详情链接。")
        parts = url.path.strip("/").split("/")
        if len(parts) != 3:
            raise SkillError("请粘贴包含具体技能名称的 skills.sh 详情链接。")
        repository, name = "/".join(parts[:2]), parts[2]
    else:
        repository, separator, name = source.rpartition("@")
        if not separator:
            raise SkillError("请输入 owner/repo@skill 或 skills.sh 详情链接。")
    if not REPOSITORY.fullmatch(repository) or not SLUG.fullmatch(name) or len(name) > 64:
        raise SkillError("技能来源格式无效。")
    return repository, name


async def download(url, limit, client):
    """有界读取固定来源，安装不执行远程脚本或 CLI。"""
    try:
        async with client.stream("GET", url) as response:
            if response.status_code != 200:
                raise SkillError("技能来源暂不可用，请确认公开仓库和技能名称。", 502)
            content = bytearray()
            async for chunk in response.aiter_bytes():
                content.extend(chunk)
                if len(content) > limit:
                    raise SkillError("技能资源超过下载大小限制。", 413)
            return bytes(content)
    except httpx.HTTPError as cause:
        raise SkillError("无法连接技能服务，请稍后重试。", 502) from cause


async def search(query, client=None):
    """查询 skills.sh 公开目录，仅返回可安装的标准来源。"""
    if client is None:
        async with httpx.AsyncClient(timeout=20, follow_redirects=False) as owned:
            return await search(query, owned)
    url = httpx.URL("https://skills.sh/api/search", params={"q": query.strip() or "agent", "limit": 24})
    raw = await download(url, 1024 * 1024, client)
    try:
        rows = json.loads(raw).get("skills", [])
        result = []
        for row in rows[:24]:
            source = row.get("source", "")
            name = row.get("skillId", "")
            if not REPOSITORY.fullmatch(source) or not SLUG.fullmatch(name) or len(name) > 64:
                continue
            result.append({"id": f"{source}@{name}", "name": name, "source": source,
                "description": row.get("description", "")[:1024], "installs": row.get("installs", 0),
                "url": f"https://skills.sh/{source}/{name}"})
        return result
    except (ValueError, TypeError, AttributeError) as cause:
        raise SkillError("技能目录返回格式无效，请稍后重试。", 502) from cause


def installed(agent_code):
    """以本机实际 SKILL.md 为准，刷新后可恢复安装状态。"""
    result = []
    for folder in sorted(skill_directory(agent_code).iterdir()):
        if folder.is_symlink() or not folder.is_dir() or not (folder / "SKILL.md").is_file():
            continue
        if (folder / "SKILL.md").is_symlink():
            continue
        try:
            if (folder / "SKILL.md").stat().st_size > 256 * 1024:
                continue
            item = metadata((folder / "SKILL.md").read_bytes())
            if item["name"] != folder.name:
                continue
            marker = folder / ".dp-work-skill.json"
            if marker.is_symlink():
                raise SkillError("安装记录不能使用符号链接。")
            if marker.is_file() and marker.stat().st_size > 8192:
                raise SkillError("安装记录过大。")
            saved = json.loads(marker.read_text(encoding="utf-8")) if marker.is_file() else {}
            if not isinstance(saved, dict):
                raise SkillError("安装记录格式无效。")
            source = saved.get("source", "")
            if not isinstance(source, str) or (source and not REPOSITORY.fullmatch(source)):
                raise SkillError("安装记录来源无效。")
            result.append({**item, "id": f"{source}@{item['name']}" if REPOSITORY.fullmatch(source) else item["name"],
                "source": source, "url": f"https://skills.sh/{source}/{item['name']}" if source else ""})
        except (OSError, SkillError, ValueError, TypeError) as cause:
            log.warning("跳过异常技能 %s：%s", folder.name, type(cause).__name__)
            continue
    return result


def extract_skill(archive, requested, destination):
    """仅提取目标技能及附件，防止路径越界、软链接和压缩炸弹。"""
    try:
        bundle = zipfile.ZipFile(io.BytesIO(archive))
        entries = bundle.infolist()
    except zipfile.BadZipFile as cause:
        raise SkillError("技能仓库下载内容无效。", 502) from cause
    with bundle:
        if len(entries) > 10000 or sum(item.file_size for item in entries) > 128 * 1024 * 1024:
            raise SkillError("技能仓库过大，请使用更小的技能仓库。", 413)
        candidates = []
        for entry in entries:
            if PurePosixPath(entry.filename).name != "SKILL.md":
                continue
            try:
                item = metadata(bundle.read(entry)) if entry.file_size <= 256 * 1024 else None
            except SkillError:
                continue
            if item and item["name"] == requested:
                candidates.append((PurePosixPath(entry.filename).parent, item))
        if len(candidates) != 1:
            raise SkillError("仓库中未找到唯一匹配的 SKILL.md，请检查技能名称。")
        parent, item = candidates[0]
        total = count = 0
        for entry in entries:
            path = PurePosixPath(entry.filename)
            if not path.is_relative_to(parent):
                continue
            relative = path.relative_to(parent)
            if path.is_absolute() or ".." in path.parts or "\\" in entry.filename or stat.S_ISLNK(entry.external_attr >> 16):
                raise SkillError("技能包含不支持的路径或符号链接。")
            if entry.is_dir():
                continue
            total += entry.file_size
            count += 1
            if total > 8 * 1024 * 1024 or count > 300:
                raise SkillError("单个技能不能超过 8 MB 或 300 个文件。", 413)
            target = destination.joinpath(*relative.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(bundle.read(entry))
            target.chmod(0o700 if entry.external_attr >> 16 & 0o111 else 0o600)
        return item


def existing_install(agent_code, repository, name):
    """检查相同技能是否已安装，并拒绝同名来源冲突。"""
    root = skill_directory(agent_code)
    if (root / name).exists() or (root / name).is_symlink():
        existing = next((item for item in installed(agent_code) if item["id"] == f"{repository}@{name}"), None)
        if existing:
            return existing
        raise SkillError("同名技能已存在，请先卸载后再安装其他来源。", 409)
    return None


def commit_install(agent_code, repository, name, archive):
    """在线程内完成解压、校验、写入与临时目录清理。"""
    root = skill_directory(agent_code)
    config.TEMP_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="skill-", dir=config.TEMP_DIR) as temporary:
        stage = Path(temporary) / name
        stage.mkdir()
        item = extract_skill(archive, name, stage)
        (stage / ".dp-work-skill.json").write_text(json.dumps({"source": repository}), encoding="utf-8")
        if (root / name).exists() or (root / name).is_symlink():
            raise SkillError("技能目录已改变，请刷新后重试。", 409)
        stage.rename(root / name)
    return {**item, "id": f"{repository}@{name}", "source": repository, "url": f"https://skills.sh/{repository}/{name}"}


async def install(agent_code, source, client=None):
    """异步下载仓库，文件操作交给线程并保留 Agent 安装锁。"""
    repository, name = parse_source(source)
    async with LOCKS.setdefault(agent_code, asyncio.Lock()):
        existing = await file_operation(existing_install, agent_code, repository, name)
        if existing:
            return existing
        if client is None:
            async with httpx.AsyncClient(timeout=90, follow_redirects=False) as owned:
                archive = await download(f"https://codeload.github.com/{repository}/zip/HEAD", MAX_ARCHIVE, owned)
        else:
            archive = await download(f"https://codeload.github.com/{repository}/zip/HEAD", MAX_ARCHIVE, client)
        return await file_operation(commit_install, agent_code, repository, name, archive)


def remove_install(agent_code, skill_id):
    """在线程内定位并删除指定 Agent 的技能。"""
    root = skill_directory(agent_code)
    item = next((row for row in installed(agent_code) if row["id"] == skill_id), None)
    if not item:
        raise SkillError("技能不存在或已卸载。", 404)
    shutil.rmtree(root / item["name"])
    return {"removed": True}


async def uninstall(agent_code, skill_id):
    """删除操作与安装共用 Agent 锁，取消时等待线程清理完成。"""
    async with LOCKS.setdefault(agent_code, asyncio.Lock()):
        return await file_operation(remove_install, agent_code, skill_id)
