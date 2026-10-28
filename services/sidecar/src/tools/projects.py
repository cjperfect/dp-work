"""将项目 ID 解析为用户在本机原生选择器中确认的目录。"""
import json
import os
from pathlib import Path
from uuid import UUID
from .. import config
from ..providers.llm.schemas import ModelError


def project_workspace(project_id: str, owner: int | None) -> Path:
    """云端只传项目 ID，实际路径以本机授权记录为准。"""
    try:
        UUID(project_id)
        if type(owner) is not int or owner <= 0:
            raise ValueError('invalid owner')
        file = config.WORKSPACE_DIR.parent / 'data/projects.json'
        if file.is_symlink() or file.stat().st_size > 4 * 1024 * 1024:
            raise ValueError('invalid registry')
        entry = json.loads(file.read_text(encoding='utf-8'))['projects'][project_id]
        if not isinstance(entry, dict) or entry.get('owner_id') != owner:
            raise ValueError('not authorized')
        original = Path(entry['path'])
        resolved = original.resolve(strict=True)
        if not original.is_absolute() or not resolved.is_dir() or os.path.normcase(str(resolved)) != os.path.normcase(str(original)):
            raise ValueError('project directory moved')
        return resolved
    except (OSError, ValueError, KeyError, TypeError) as cause:
        raise ModelError('PROJECT_DIRECTORY_UNAVAILABLE', '项目工作目录未在当前设备授权、已移动或不存在，请重新选择本地文件夹。') from cause
