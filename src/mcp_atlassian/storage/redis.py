"""Encrypted Redis-backed OAuth client storage factory."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, urlparse

if TYPE_CHECKING:
    from key_value.aio.protocols import AsyncKeyValue


def factory(config: dict[str, Any] | None = None) -> AsyncKeyValue:
    """Create an encrypted Redis-backed OAuth client storage instance.

    Args:
        config: Redis connection options accepted by ``redis.asyncio.Redis``
            plus ``encryption_key``. The key must be a stable Fernet key from
            a secret, and is used to encrypt values before they reach Redis.

    Returns:
        An encrypted async key-value store compatible with FastMCP OAuth proxy
        storage.

    Raises:
        ValueError: If the encryption key or Redis configuration is invalid.
    """
    from cryptography.fernet import Fernet
    from key_value.aio.stores.redis import RedisStore
    from key_value.aio.wrappers.encryption import FernetEncryptionWrapper
    from redis.asyncio import Redis

    options = dict(config or {})
    raw_encryption_key = options.pop("encryption_key", None)
    if not isinstance(raw_encryption_key, str) or not raw_encryption_key.strip():
        raise ValueError(
            "Redis OAuth client storage requires a non-empty 'encryption_key'"
        )

    try:
        encryption_key = Fernet(raw_encryption_key.encode("ascii"))
    except (UnicodeEncodeError, ValueError, TypeError) as exc:
        raise ValueError(
            "Redis OAuth client storage 'encryption_key' must be a valid Fernet key"
        ) from exc

    default_collection = options.pop("default_collection", None)
    client = options.pop("client", None)
    url = options.pop("url", None)

    if client is not None and (url is not None or options):
        raise ValueError(
            "Redis OAuth client storage accepts either 'client' or Redis "
            "connection options, not both"
        )

    if client is None:
        options["decode_responses"] = True
        if url is not None:
            if not isinstance(url, str):
                raise ValueError("Redis OAuth client storage 'url' must be a string")

            parsed_url = urlparse(url)
            if parsed_url.scheme not in {"redis", "rediss"}:
                raise ValueError(
                    "Redis OAuth client storage 'url' must use redis:// or rediss://"
                )

            if parsed_url.scheme == "rediss":
                query = parse_qs(parsed_url.query)
                for option_name in ("ssl_cert_reqs", "ssl_check_hostname"):
                    if option_name in query:
                        msg = (
                            f"Redis OAuth client storage URL must not override "
                            f"{option_name} for rediss://"
                        )
                        raise ValueError(msg)
                options["ssl_cert_reqs"] = "required"
                options["ssl_check_hostname"] = True

            client = Redis.from_url(url, **options)
        else:
            client = Redis(**options)

    redis_store = RedisStore(client=client, default_collection=default_collection)

    return FernetEncryptionWrapper(key_value=redis_store, fernet=encryption_key)
