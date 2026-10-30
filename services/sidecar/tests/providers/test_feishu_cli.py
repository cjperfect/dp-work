"""飞书 CLI 授权任务使用本地替身，不发起真实授权。"""
import asyncio
import json
from unittest.mock import AsyncMock
from pathlib import Path

import pytest

from src.connectors.errors import ConnectorError as ApiError
from src.connectors import cli, service


@pytest.fixture(autouse=True)
def isolated_cli(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "DATA_ROOT", tmp_path / "data")
    monkeypatch.setattr(cli, "binary", lambda: "/fixture/lark-cli")
    service._jobs.clear()
    yield
    service._jobs.clear()


def test_profile_and_environment_do_not_reuse_other_accounts(monkeypatch):
    monkeypatch.setenv("FEISHU_APP_SECRET", "must-not-inherit")
    monkeypatch.setenv("LARK_USER_ACCESS_TOKEN", "must-not-inherit")
    monkeypatch.setenv("OPENCLAW_HOME", "/another-agent")
    first, second = cli.environment(1), cli.environment(2)
    assert first["LARKSUITE_CLI_CONFIG_DIR"] != second["LARKSUITE_CLI_CONFIG_DIR"]
    assert "FEISHU_APP_SECRET" not in first
    assert "LARK_USER_ACCESS_TOKEN" not in first
    assert "OPENCLAW_HOME" not in first
    with pytest.raises(ValueError):
        cli.profile(-1)


def test_only_official_https_authorization_links_are_allowed():
    assert cli.safe_url("https://accounts.feishu.cn/oauth?code=sample")
    for value in ("http://accounts.feishu.cn", "https://feishu.cn.attacker.example", "https://user:secret@accounts.feishu.cn", "javascript:alert(1)"):
        assert not cli.safe_url(value)


def test_public_flow_never_contains_device_code_or_completed_link():
    flow = service.Authorization(action="login", state="waiting", url="https://accounts.feishu.cn/auth")
    assert "device_code" not in flow.public()
    flow.state = "completed"
    assert flow.public()["url"] is None


def test_bot_identity_does_not_count_as_user_authorization(monkeypatch):
    (cli.profile(1) / "config.json").write_text("{}")
    monkeypatch.setattr(cli, "run", AsyncMock(return_value={"identity": "bot", "verified": True,
        "identities": {"user": {"available": False}, "bot": {"available": True}}}))
    data = asyncio.run(service.status(1, verify=True))
    assert data["configured"] is True
    assert data["connected"] is False
    assert data["account"] is None


def test_login_requests_docs_drive_scopes_and_verifies_after_completion(monkeypatch):
    (cli.profile(1) / "config.json").write_text("{}")
    run = AsyncMock(side_effect=[
        {"verification_url": "https://accounts.feishu.cn/auth?code=fixture", "device_code": "private-code", "expires_in": 300},
        {"authenticated": True},
        {"verified": True, "identities": {"user": {"available": True, "verified": True, "userName": "测试用户"}}},
    ])
    monkeypatch.setattr(cli, "run", run)
    monkeypatch.setattr(cli, "qrcode", AsyncMock(return_value="data:image/png;base64,fixture"))
    async def case():
        await service.start(1, "login")
        await service._jobs[1].task
        assert service._jobs[1].state == "completed"
        assert service._jobs[1].url is None
    asyncio.run(case())
    assert run.await_args_list[0].args == (1, "auth", "login", "--scope", cli.LOGIN_SCOPE, "--domain", "docs,drive", "--no-wait", "--json")
    assert "docs" not in cli.LOGIN_SCOPE and "im:" not in cli.LOGIN_SCOPE
    assert "--verify" in run.await_args_list[-1].args


def test_configuration_is_separate_and_pending_flow_can_be_cancelled(monkeypatch):
    async def configure(owner, on_url):
        await on_url("https://accounts.feishu.cn/configure")
        await asyncio.Future()
    monkeypatch.setattr(cli, "configure", configure)
    monkeypatch.setattr(cli, "qrcode", AsyncMock(return_value=None))
    async def case():
        await service.start(1, "configure")
        await asyncio.sleep(0)
        assert service._jobs[1].state == "waiting"
        with pytest.raises(ApiError):
            await service.start(1, "configure")
        other = await service.status(2)
        assert other["flow"] is None
        await service.cancel(1)
        assert 1 not in service._jobs
    asyncio.run(case())


def test_untrusted_url_and_errors_never_reach_browser(monkeypatch):
    (cli.profile(1) / "config.json").write_text("{}")
    monkeypatch.setattr(cli, "run", AsyncMock(return_value={"verification_url": "https://attacker.example", "device_code": "private-code"}))
    async def case():
        await service.start(1, "login")
        await service._jobs[1].task
        result = service._jobs[1].public()
        assert result["state"] == "failed"
        assert "private-code" not in json.dumps(result)
        assert "attacker" not in json.dumps(result)
    asyncio.run(case())


def test_credentials_are_local_and_only_this_users_ciphertexts_are_migrated(tmp_path, monkeypatch):
    monkeypatch.setattr(cli.sys, "platform", "darwin")
    old_home = tmp_path / "old-home"
    monkeypatch.setattr(cli, "SYSTEM_HOME", old_home)
    source = old_home / "Library/Application Support/lark-cli"
    source.mkdir(parents=True)
    (source / "appsecret_cli_one.enc").write_bytes(b"encrypted-app-secret")
    (source / "cli_one_ou_one.enc").write_bytes(b"encrypted-user-token")
    (source / "cli_other_ou_other.enc").write_bytes(b"other-account")
    (cli.profile(1) / "config.json").write_text(json.dumps({"apps": [{"appId": "cli_one", "users": [{"userOpenId": "ou_one"}]}]}))
    env = cli.environment(1)
    target = cli.credentials_directory(1)
    assert target.is_relative_to(cli.profile(1))
    assert target == Path(env["HOME"]) / "Library/Application Support/lark-cli"
    assert (target / "appsecret_cli_one.enc").read_bytes() == b"encrypted-app-secret"
    assert (target / "cli_one_ou_one.enc").read_bytes() == b"encrypted-user-token"
    assert not (target / "cli_other_ou_other.enc").exists()
    assert (target / "cli_one_ou_one.enc").stat().st_mode & 0o777 == 0o600
    # 退出登录后不允许旧系统目录中的副本被再次导入。
    (target / "cli_one_ou_one.enc").unlink()
    cli.environment(1)
    assert not (target / "cli_one_ou_one.enc").exists()


def test_verified_connection_is_restored_after_restart_without_verifying_again(monkeypatch):
    (cli.profile(1) / "config.json").write_text("{}")
    identity = {"appId": "cli_app", "identities": {"user": {"available": True, "verified": True,
        "openId": "ou_user", "userName": "测试用户", "tokenStatus": "valid"}}}
    run = AsyncMock(return_value=identity)
    monkeypatch.setattr(cli, "run", run)
    async def case():
        first = await service.status(1, verify=True)
        assert first["verified"] is True
        record = cli.read_connection(1)
        assert record["last_verified_at"]
        assert "token" not in json.dumps(record).lower()
        service._jobs.clear()
        run.return_value = {"appId": "cli_app", "identities": {"user": {"available": True,
            "openId": "ou_user", "userName": "测试用户", "tokenStatus": "valid"}}}
        restored = await service.status(1)
        assert restored["connected"] and restored["verified"]
        assert restored["last_verified_at"] == first["last_verified_at"]
        assert "--verify" not in run.await_args_list[-1].args
    asyncio.run(case())


def test_old_verification_cannot_override_expired_or_different_identity(monkeypatch):
    (cli.profile(1) / "config.json").write_text("{}")
    cli.save_connection(1, {"app_id": "cli_app", "user_id": "ou_user", "last_verified_at": "2026-10-25T00:00:00Z"})
    run = AsyncMock(return_value={"appId": "cli_app", "identities": {"user": {"available": True,
        "openId": "ou_user", "tokenStatus": "expired"}}})
    monkeypatch.setattr(cli, "run", run)
    expired = asyncio.run(service.status(1))
    assert not expired["connected"] and not expired["verified"]
    run.return_value = {"appId": "cli_app", "identities": {"user": {"available": True,
        "openId": "ou_other", "tokenStatus": "valid"}}}
    changed = asyncio.run(service.status(1))
    assert changed["verified"] is False
    assert changed["last_verified_at"] is None


def test_expiring_token_is_refreshed_automatically_without_new_scan(monkeypatch):
    (cli.profile(1) / "config.json").write_text("{}")
    run = AsyncMock(side_effect=[
        {"appId": "cli_app", "identities": {"user": {"available": False, "tokenStatus": "needs_refresh"}}},
        {"appId": "cli_app", "identities": {"user": {"available": True, "verified": True,
            "openId": "ou_user", "tokenStatus": "valid"}}},
    ])
    monkeypatch.setattr(cli, "run", run)
    restored = asyncio.run(service.status(1))
    assert restored["connected"] and restored["verified"]
    assert "--verify" in run.await_args_list[-1].args
    assert not any("login" in call.args for call in run.await_args_list)


def test_logout_clears_persisted_verification(monkeypatch):
    cli.save_connection(1, {"app_id": "cli_app", "user_id": "ou_user", "last_verified_at": "2026-10-25T00:00:00Z"})
    monkeypatch.setattr(cli, "run", AsyncMock(return_value={"loggedOut": True}))
    asyncio.run(service.logout(1))
    assert cli.read_connection(1) == {}
