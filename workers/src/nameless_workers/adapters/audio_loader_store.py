"""Real :class:`~nameless_workers.ports.AudioLoader` adapters over the content-addressed object store.

:class:`FilesystemAudioLoader` mirrors the Rust ``FilesystemObjectStore`` exactly: objects live flat
under a root directory, named by their lowercase-hex SHA-256 content hash (the ``audio_uri``). That is
the same layout the Phase-1 ``--local`` capture path writes (``.nameless-local/objects/<hash>``), so
the worker reads precisely the bytes the control plane stored — no format negotiation, addressed by id.

The key is validated to be pure lowercase hex before being joined to the root, so a malformed/hostile
id can never contain a path separator or ``..`` (traversal-safe — same property as the Rust store).

:class:`S3AudioLoader` is the production sibling over an S3/R2 bucket; it imports ``boto3`` lazily and
is env-gated. Both satisfy the one ``load`` method, so the worker is indifferent to which is wired.
"""

from __future__ import annotations

import os
from pathlib import Path


class InvalidObjectKey(ValueError):
    """The audio_uri is not a valid content-hash key (must be lowercase hex)."""


class ObjectNotFound(FileNotFoundError):
    """No object stored under the given content-hash key."""


def _validate_hex_key(audio_uri: str) -> str:
    if not audio_uri or not all(c in "0123456789abcdef" for c in audio_uri):
        raise InvalidObjectKey(f"invalid object key (must be lowercase hex content hash): {audio_uri!r}")
    return audio_uri


class FilesystemAudioLoader:
    """Read audio bytes from a content-addressed directory (the ``--local`` / on-disk store)."""

    def __init__(self, root: str | os.PathLike[str]) -> None:
        self._root = Path(root)

    def load(self, audio_uri: str) -> bytes:
        key = _validate_hex_key(audio_uri)
        path = self._root / key
        try:
            return path.read_bytes()
        except FileNotFoundError as exc:
            raise ObjectNotFound(audio_uri) from exc


class S3AudioLoader:
    """Read audio bytes from an S3/R2 bucket by content-hash key (production; env-gated).

    ``boto3`` is imported lazily so this module stays importable without it. Mirrors the Rust
    ``S3ObjectStore`` get-by-id contract.
    """

    def __init__(self, bucket: str, *, endpoint_url: str | None = None, prefix: str = "") -> None:
        self._bucket = bucket
        self._prefix = prefix
        self._endpoint_url = endpoint_url
        self._client = None  # built lazily on first load

    def _ensure_client(self):
        if self._client is None:
            import boto3  # lazy: only needed for the real S3 path

            self._client = boto3.client("s3", endpoint_url=self._endpoint_url)
        return self._client

    def load(self, audio_uri: str) -> bytes:
        key = _validate_hex_key(audio_uri)
        client = self._ensure_client()
        try:
            resp = client.get_object(Bucket=self._bucket, Key=f"{self._prefix}{key}")
            return resp["Body"].read()
        except Exception as exc:  # noqa: BLE001 - normalize botocore errors to the port's failure
            raise ObjectNotFound(audio_uri) from exc
