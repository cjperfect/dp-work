import json
import time

from jwcrypto import jwe

from app.utils import credential_transport
from app.utils.credential_transport import ALGORITHM, ENCRYPTION


def auth_payload(username, password, /, purpose="login", **changes):
    key = credential_transport.get_transport_key()
    payload = {
        "username": username.strip(),
        "password": password,
        "purpose": purpose,
        "issued_at": int(time.time()),
        **changes,
    }
    token = jwe.JWE(
        json.dumps(payload, ensure_ascii=False).encode(),
        protected={"alg": ALGORITHM, "enc": ENCRYPTION, "kid": key.thumbprint()},
        recipient=key,
    )
    return {"username": username, "encrypted_password": token.serialize(compact=True)}


def protect(payload, purpose):
    return {
        **{name: value for name, value in payload.items() if name != "password"},
        **auth_payload(payload["username"], payload["password"], purpose),
    }
