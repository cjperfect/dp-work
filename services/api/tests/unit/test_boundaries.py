"""约束依赖方向，防止业务重新回流到 Router 或公共目录。"""

import ast
from pathlib import Path

APP = Path(__file__).resolve().parents[2] / "app"


def imports(path):
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.ImportFrom):
            yield node.module or ""
        elif isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)


def test_services_do_not_depend_on_http_framework():
    for path in (APP / "modules").glob("*/service.py"):
        assert not any(
            name.startswith(("fastapi", "starlette")) for name in imports(path)
        ), path


def test_routers_do_not_access_database():
    for path in (APP / "modules").glob("*/router.py"):
        assert not any(
            "repository" in name or "database" in name or name == "asyncpg"
            for name in imports(path)
        ), path
        assert (
            "SELECT " not in path.read_text() and "INSERT " not in path.read_text()
        ), path


def test_modules_do_not_import_another_modules_repository():
    for path in (APP / "modules").rglob("*.py"):
        module = path.relative_to(APP / "modules").parts[0]
        for name in imports(path):
            if name.startswith("app.modules.") and name.endswith(".repository"):
                assert name.split(".")[2] == module, path


def test_repositories_do_not_manage_connection_lifecycle():
    for path in (APP / "modules").glob("*/repository.py"):
        source = path.read_text()
        assert (
            "get_pool" not in source
            and ".transaction(" not in source
            and ".commit(" not in source
        ), path


def test_core_has_no_business_module_dependencies():
    for path in (APP / "core").glob("*.py"):
        assert not any(name.startswith("app.modules") for name in imports(path)), path
