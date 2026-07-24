"""Reference QuestLog catalog updater for the Windows EldenTracker app.

Copy this into the current app (for example as ``questlog/catalog_sync.py``),
wire its logger into the app logger, and call ``refresh()`` on a worker thread.
Only JSON is downloaded.  A failed or incompatible refresh never replaces a
previously verified cache.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


SUPPORTED_API_VERSION = 1
SUPPORTED_SCHEMA_VERSIONS = {1}
SUPPORTED_CALCULATION_CONTRACTS = {1}
MAX_DATASET_BYTES = 32 * 1024 * 1024
DEFAULT_TIMEOUT_SECONDS = 5


class CatalogSyncError(RuntimeError):
    pass


@dataclass
class SyncResult:
    updated: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    offline: bool = False
    app_update_required: bool = False


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _read_json(path: Path, default: Any = None) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (FileNotFoundError, OSError, ValueError):
        return default


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


class CatalogStore:
    """Content-addressed catalog cache with bundled/offline fallback."""

    def __init__(
        self,
        base_url: str,
        cache_dir: str | Path,
        bundled_dir: str | Path,
        app_version: str,
        logger,
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.cache_dir = Path(cache_dir)
        self.bundled_dir = Path(bundled_dir)
        self.app_version = app_version
        self.log = logger
        self.timeout = timeout
        self.manifest_path = self.cache_dir / "manifest.json"
        self.state_path = self.cache_dir / "state.json"

    def _request(self, url: str, etag: str | None = None) -> tuple[int, bytes, str | None]:
        headers = {
            "Accept": "application/json",
            "User-Agent": f"QuestLog-EldenTracker/{self.app_version}",
        }
        if etag:
            headers["If-None-Match"] = etag
        request = Request(url, headers=headers, method="GET")
        try:
            with urlopen(request, timeout=self.timeout) as response:
                content_length = response.headers.get("Content-Length")
                if content_length and int(content_length) > MAX_DATASET_BYTES:
                    raise CatalogSyncError("download exceeds the 32 MiB safety limit")
                body = response.read(MAX_DATASET_BYTES + 1)
                if len(body) > MAX_DATASET_BYTES:
                    raise CatalogSyncError("download exceeds the 32 MiB safety limit")
                return response.status, body, response.headers.get("ETag")
        except HTTPError as error:
            if error.code == 304:
                return 304, b"", error.headers.get("ETag")
            raise CatalogSyncError(f"HTTP {error.code} for {url}") from error
        except (URLError, TimeoutError, OSError) as error:
            raise CatalogSyncError(f"cannot reach {url}: {error}") from error

    @staticmethod
    def _decode_json(body: bytes, label: str) -> Any:
        try:
            return json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as error:
            raise CatalogSyncError(f"{label} is not valid UTF-8 JSON") from error

    def _validate_manifest(self, manifest: Any) -> None:
        if not isinstance(manifest, dict):
            raise CatalogSyncError("manifest must be an object")
        if manifest.get("api_version") != SUPPORTED_API_VERSION:
            raise CatalogSyncError(
                f"unsupported catalog API version {manifest.get('api_version')!r}"
            )
        if manifest.get("schema_version") not in SUPPORTED_SCHEMA_VERSIONS:
            raise CatalogSyncError(
                f"unsupported catalog schema {manifest.get('schema_version')!r}"
            )
        if manifest.get("account_required") is not False:
            raise CatalogSyncError("public catalog unexpectedly requires an account")
        if not isinstance(manifest.get("datasets"), dict):
            raise CatalogSyncError("manifest has no datasets object")

    def _download_dataset(self, name: str, metadata: dict[str, Any]) -> bytes:
        revision = metadata.get("revision")
        expected_hash = metadata.get("sha256")
        expected_size = metadata.get("bytes")
        url = metadata.get("url")
        if not all(isinstance(v, str) and v for v in (revision, expected_hash, url)):
            raise CatalogSyncError(f"{name}: incomplete manifest entry")
        if revision != expected_hash or len(expected_hash) != 64:
            raise CatalogSyncError(f"{name}: invalid content revision")
        if not isinstance(expected_size, int) or not 0 < expected_size <= MAX_DATASET_BYTES:
            raise CatalogSyncError(f"{name}: invalid declared byte length")
        if not url.startswith(f"{self.base_url}/api/soulslike/data/"):
            raise CatalogSyncError(f"{name}: rejected download origin")

        status, body, _ = self._request(url)
        if status != 200:
            raise CatalogSyncError(f"{name}: unexpected HTTP {status}")
        if len(body) != expected_size:
            raise CatalogSyncError(f"{name}: byte length does not match manifest")
        if hashlib.sha256(body).hexdigest() != expected_hash:
            raise CatalogSyncError(f"{name}: SHA-256 does not match manifest")

        payload = self._decode_json(body, name)
        if payload.get("dataset") != name:
            raise CatalogSyncError(f"{name}: dataset identity mismatch")
        if payload.get("schema_version") not in SUPPORTED_SCHEMA_VERSIONS:
            raise CatalogSyncError(f"{name}: unsupported schema version")
        return body

    def refresh(self) -> SyncResult:
        """Refresh verified datasets; preserve the old cache on every failure."""
        result = SyncResult()
        state = _read_json(self.state_path, {}) or {}
        cached_manifest = _read_json(self.manifest_path)
        manifest_url = f"{self.base_url}/api/soulslike/data/manifest/"

        try:
            status, body, response_etag = self._request(
                manifest_url, state.get("manifest_etag")
            )
            if status == 304:
                if not cached_manifest:
                    raise CatalogSyncError("server returned 304 but no cached manifest exists")
                manifest = cached_manifest
            else:
                manifest = self._decode_json(body, "catalog manifest")
                self._validate_manifest(manifest)
                _atomic_write(self.manifest_path, _canonical_json(manifest))
                state["manifest_etag"] = response_etag

            self._validate_manifest(manifest)
            calculation_contract = manifest.get("calculation_contract_version")
            if calculation_contract not in SUPPORTED_CALCULATION_CONTRACTS:
                result.app_update_required = True
                result.warnings.append(
                    "The server calculation contract is newer than this app; "
                    "cached calculations were retained."
                )

            installed = state.setdefault("datasets", {})
            for name, metadata in manifest["datasets"].items():
                if not isinstance(metadata, dict):
                    result.warnings.append(f"{name}: invalid manifest entry")
                    continue
                if (
                    name in {"vanilla_calculations", "err_calculations"}
                    and result.app_update_required
                ):
                    continue
                destination = self.cache_dir / "datasets" / f"{name}.json"
                if installed.get(name) == metadata.get("revision") and destination.exists():
                    result.unchanged.append(name)
                    continue
                try:
                    content = self._download_dataset(name, metadata)
                    _atomic_write(destination, content)
                    installed[name] = metadata["revision"]
                    result.updated.append(name)
                except CatalogSyncError as error:
                    result.warnings.append(str(error))

            state["last_successful_check_unix"] = int(time.time())
            state["poll_after_seconds"] = manifest.get("poll_after_seconds", 21600)
            _atomic_write(self.state_path, _canonical_json(state))
        except CatalogSyncError as error:
            result.offline = True
            result.warnings.append(str(error))
            self.log.warning("Catalog refresh failed; using verified cache: %s", error)

        return result

    def refresh_live_resources(self, names: set[str]) -> SyncResult:
        """Refresh selected DB-backed resources no more than once per poll window."""
        result = SyncResult()
        manifest = _read_json(self.manifest_path, {}) or {}
        resources = manifest.get("live_resources", {})
        state = _read_json(self.state_path, {}) or {}
        now = int(time.time())
        next_check = state.get("live_resources_checked_unix", 0) + int(
            manifest.get("live_resource_poll_seconds", 21600)
        )
        if now < next_check:
            result.unchanged.extend(sorted(names))
            return result

        hashes = state.setdefault("live_resource_hashes", {})
        for name in sorted(names):
            url = resources.get(name)
            if not isinstance(url, str) or not url.startswith(
                f"{self.base_url}/api/soulslike/"
            ):
                result.warnings.append(f"{name}: unavailable or rejected resource URL")
                continue
            try:
                status, body, _ = self._request(url)
                if status != 200:
                    raise CatalogSyncError(f"{name}: unexpected HTTP {status}")
                payload = self._decode_json(body, name)
                canonical = _canonical_json(payload)
                digest = hashlib.sha256(canonical).hexdigest()
                destination = self.cache_dir / "live" / f"{name}.json"
                if digest == hashes.get(name) and destination.exists():
                    result.unchanged.append(name)
                    continue
                _atomic_write(destination, canonical)
                hashes[name] = digest
                result.updated.append(name)
            except CatalogSyncError as error:
                result.warnings.append(str(error))

        # A partial outage should be retried on the next launch instead of
        # suppressing retries for the full six-hour success interval.
        if not result.warnings:
            state["live_resources_checked_unix"] = now
        _atomic_write(self.state_path, _canonical_json(state))
        return result

    def load(self, name: str) -> Any:
        """Read the verified cache, falling back to the app-bundled snapshot."""
        cached = _read_json(self.cache_dir / "datasets" / f"{name}.json")
        if cached is not None:
            return cached
        bundled = _read_json(self.bundled_dir / f"{name}.json")
        if bundled is not None:
            return bundled
        raise CatalogSyncError(f"no cached or bundled {name} dataset is available")

    def load_live(self, name: str) -> Any:
        cached = _read_json(self.cache_dir / "live" / f"{name}.json")
        if cached is not None:
            return cached
        bundled = _read_json(self.bundled_dir / "live" / f"{name}.json")
        if bundled is not None:
            return bundled
        raise CatalogSyncError(f"no cached or bundled {name} resource is available")
