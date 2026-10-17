"""Zerodha Kite Connect — the OAuth flow, end to end.

Kite Connect is a *registered* app: the operator puts an ``api_key``/``api_secret``
in the deployment's secrets, the account holder logs in on Kite's own page and is
redirected back with a ``request_token``, and that token is exchanged for an
``access_token`` using a checksum. The access token is invalidated every morning
around 07:30 IST, so the flow is a daily one.

Nothing here ever holds a password: the login happens on ``kite.trade``, and all
this module ever sees is the ``request_token`` and the ``access_token``. The token
is a credential, so it is stored owner-read-only under ``sessions/`` — ignored by
git and by the image.

Every network call goes through an injectable ``transport`` so the whole flow is
testable without touching the network.
"""

from __future__ import annotations

import hashlib
import json
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Callable, Dict, Mapping, Optional

import pandas as pd

from utils.brokers import api

LOGIN_URL = "https://kite.trade/connect/login"
API_BASE = "https://api.kite.trade"
KITE_VERSION = "3"

#: Kite invalidates every access token at about 07:30 IST the next day.
IST = timezone(timedelta(hours=5, minutes=30))
TOKEN_RESET = time(7, 30)

#: Access tokens live here, on the operator's own disk, never in git or an image.
SESSION_DIR = (Path(__file__).resolve().parent.parent.parent / "sessions").resolve()

#: A transport takes (method, url, body, headers) and returns the parsed JSON.
Transport = Callable[[str, str, Optional[bytes], Dict[str, str]], Mapping]


def _transport(
    method: str, url: str, body: Optional[bytes], headers: Dict[str, str], *, timeout: int = 15
) -> Mapping:
    """The default transport: one urllib call to a documented Kite endpoint."""
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        return json.loads(response.read().decode("utf-8"))


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class KiteConfig:
    """The published Kite app's credentials, from secrets or the environment."""

    api_key: str = ""
    api_secret: str = ""
    redirect_url: str = ""

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.api_secret)

    @classmethod
    def from_secrets(cls, secrets: Optional[Mapping] = None) -> "KiteConfig":
        """Read the ``[kite]`` secrets table, falling back to ``KITE_*`` env vars."""
        table = secrets.get("kite") if isinstance(secrets, Mapping) else None
        if isinstance(table, Mapping):
            return cls(
                api_key=str(table.get("api_key", "") or ""),
                api_secret=str(table.get("api_secret", "") or ""),
                redirect_url=str(table.get("redirect_url", "") or ""),
            )
        return cls(
            api_key=os.environ.get("KITE_API_KEY", ""),
            api_secret=os.environ.get("KITE_API_SECRET", ""),
            redirect_url=os.environ.get("KITE_REDIRECT_URL", ""),
        )

    def login_url(self, redirect_params: str = "") -> str:
        """The URL to send the account holder to, to mint a request token."""
        query = {"api_key": self.api_key, "v": KITE_VERSION}
        if redirect_params:
            query["redirect_params"] = redirect_params
        return f"{LOGIN_URL}?{urllib.parse.urlencode(query)}"


def checksum(api_key: str, request_token: str, api_secret: str) -> str:
    """The SHA-256 checksum Kite requires, over ``api_key + request_token + secret``."""
    digest = f"{api_key}{request_token}{api_secret}".encode("utf-8")
    return hashlib.sha256(digest).hexdigest()


# --------------------------------------------------------------------------- #
# Sessions
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class KiteSession:
    """An access token and the account it belongs to."""

    api_key: str
    access_token: str
    user_id: str = ""
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def expires_at(self) -> datetime:
        """The next 07:30 IST after the token was minted."""
        moment = self.generated_at.astimezone(IST)
        reset = datetime.combine(moment.date(), TOKEN_RESET, tzinfo=IST)
        if moment.time() >= TOKEN_RESET:
            reset += timedelta(days=1)
        return reset

    def is_fresh(self, now: Optional[datetime] = None) -> bool:
        return (now or datetime.now(timezone.utc)) < self.expires_at()

    def to_dict(self) -> Dict[str, str]:
        return {
            "api_key": self.api_key,
            "access_token": self.access_token,
            "user_id": self.user_id,
            "generated_at": self.generated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, payload: Mapping) -> "KiteSession":
        generated = payload.get("generated_at")
        try:
            moment = datetime.fromisoformat(str(generated))
        except (TypeError, ValueError):
            moment = datetime.now(timezone.utc)
        return cls(
            api_key=str(payload.get("api_key", "") or ""),
            access_token=str(payload.get("access_token", "") or ""),
            user_id=str(payload.get("user_id", "") or ""),
            generated_at=moment,
        )


class TokenStore:
    """Access tokens on the operator's own disk, owner-read-only.

    A Kite token *is* a credential, so it is written under ``sessions/`` — which
    git and the image both ignore — with ``0600`` permissions, and never logged.
    """

    def __init__(self, root: Optional[Path] = None) -> None:
        self.root = (root or SESSION_DIR).resolve()

    def path(self) -> Path:
        return self.root / "kite.json"

    def load(self) -> Optional[KiteSession]:
        try:
            payload = json.loads(self.path().read_text())
        except (OSError, ValueError):
            return None
        return KiteSession.from_dict(payload) if isinstance(payload, Mapping) else None

    def save(self, session: KiteSession) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.path()
        path.write_text(json.dumps(session.to_dict(), indent=2))
        os.chmod(path, 0o600)
        return path

    def clear(self) -> None:
        try:
            self.path().unlink()
        except OSError:
            pass


def current_session(store: Optional[TokenStore] = None, now: Optional[datetime] = None) -> Optional[KiteSession]:
    """A stored session, but only while its token is still valid for the day."""
    session = (store or TokenStore()).load()
    if session is not None and session.is_fresh(now):
        return session
    return None


# --------------------------------------------------------------------------- #
# The flow
# --------------------------------------------------------------------------- #
def _raise_for_error(payload: Mapping) -> None:
    """Kite returns ``status: error`` with a readable message; surface it."""
    if not isinstance(payload, Mapping):
        return
    if payload.get("status") == "error" or payload.get("error_type"):
        message = payload.get("message") or payload.get("error_type") or "Kite rejected the request"
        raise ValueError(str(message))


def exchange_request_token(
    config: KiteConfig,
    request_token: str,
    *,
    transport: Transport = _transport,
    now: Optional[datetime] = None,
) -> KiteSession:
    """Trade a ``request_token`` for an access token — the redirect's second half."""
    if not config.configured:
        raise api.NotConfigured("Kite needs an api_key and api_secret.")
    if not request_token:
        raise ValueError("A request_token is required to complete the login.")

    body = urllib.parse.urlencode(
        {
            "api_key": config.api_key,
            "request_token": request_token,
            "checksum": checksum(config.api_key, request_token, config.api_secret),
        }
    ).encode("utf-8")
    headers = {
        "X-Kite-Version": KITE_VERSION,
        "Content-Type": "application/x-www-form-urlencoded",
    }
    payload = transport("POST", f"{API_BASE}/session/token", body, headers)
    _raise_for_error(payload)
    node = payload.get("data") or {}
    access_token = node.get("access_token")
    if not access_token:
        raise ValueError("Kite did not return an access token.")
    return KiteSession(
        api_key=config.api_key,
        access_token=str(access_token),
        user_id=str(node.get("user_id", "") or ""),
        generated_at=now or datetime.now(timezone.utc),
    )


def fetch_holdings(session: KiteSession, *, transport: Transport = _transport) -> pd.DataFrame:
    """The account's holdings, normalised into the canonical columns.

    Uses the registry's Zerodha entry for the endpoint and field aliases, so the
    API path and the file path land on the same schema.
    """
    provider = api.PROVIDERS_BY_NAME["Zerodha"]
    url, headers, body = api.build_request(provider, session.access_token, session.api_key)
    headers["X-Kite-Version"] = KITE_VERSION
    payload = transport(provider.method, url, body, headers)
    _raise_for_error(payload)
    return provider.normalise(api.records_from_payload(provider, payload))
