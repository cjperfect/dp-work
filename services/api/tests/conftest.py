"""密码传输测试只用临时内存密钥，不读取开发或生产私钥。"""

import pytest
from jwcrypto import jwk

from app.utils import credential_transport


@pytest.fixture(scope="session")
def transport_test_key():
    return jwk.JWK.generate(kty="RSA", size=2048)


@pytest.fixture(autouse=True)
def isolated_transport_key(monkeypatch, transport_test_key):
    monkeypatch.setattr(
        credential_transport, "get_transport_key", lambda: transport_test_key
    )
