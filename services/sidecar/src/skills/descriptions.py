"""从技能公开页面读取简短简介，按技能缓存，避免下载整个仓库。"""
import asyncio
import codecs
import hashlib
from html.parser import HTMLParser
import json
import re
import time

import httpx

from .. import config
from .service import parse_source, SkillError, file_operation


class DescriptionParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.description = ""

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "meta" and values.get("name", "").lower() == "description":
            self.description = re.sub(r"\s+", " ", values.get("content", "")).strip()[:400]


def cache_file(source):
    root = config.DATA_ROOT / "cache/skills-descriptions"
    return root / (hashlib.sha256(source.encode()).hexdigest() + ".json")


def read_cache(file):
    try:
        data = json.loads(file.read_text(encoding="utf-8"))
        if data["expires_at"] > time.time() and isinstance(data["description"], str):
            return data["description"]
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None


def save_cache(file, description):
    try:
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(json.dumps({"description": description, "expires_at": time.time() + (86400 if description else 120)}), encoding="utf-8")
        files = list(file.parent.glob("*.json"))
        if len(files) > 500:
            for stale in sorted(files, key=lambda item: item.stat().st_mtime)[:-500]:
                stale.unlink(missing_ok=True)
    except OSError:
        pass


async def descriptions(sources, client=None):
    """批量读取公开简介；单项失败不影响其他技能展示。"""
    if client is None:
        async with httpx.AsyncClient(timeout=6, follow_redirects=False) as owned:
            return await descriptions(sources, owned)
    semaphore = asyncio.Semaphore(8)

    async def read(source):
        try:
            repository, name = parse_source(source)
        except SkillError:
            return source, ""
        file = cache_file(source)
        cached = await file_operation(read_cache, file)
        if cached is not None:
            return source, cached
        parser = DescriptionParser()
        async with semaphore:
            try:
                async with client.stream("GET", f"https://www.skills.sh/{repository}/{name}") as response:
                    if response.status_code == 200:
                        size = 0
                        decoder = codecs.getincrementaldecoder("utf-8")("replace")
                        async for block in response.aiter_bytes(chunk_size=8192):
                            size += len(block)
                            parser.feed(decoder.decode(block))
                            if parser.description or size >= 65536:
                                break
            except (httpx.HTTPError, ValueError):
                pass
        await file_operation(save_cache, file, parser.description)
        return source, parser.description

    return dict(await asyncio.gather(*(read(source) for source in dict.fromkeys(sources[:24]))))
