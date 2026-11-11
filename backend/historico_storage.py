from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Dict, Optional, Tuple


ROOT = Path(__file__).resolve().parent
BLOB_PATH = "edge-latam/historico_partidos.json"
_LOCK = threading.RLock()


def _load_root_env() -> None:
    """Load storage credentials from the local root .env without overriding exports."""
    env_path = ROOT.parent / ".env"
    try:
        lines = env_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for line in lines:
        entry = line.strip()
        if not entry or entry.startswith("#"):
            continue
        if entry.startswith("export "):
            entry = entry[len("export "):].strip()
        name, separator, value = entry.partition("=")
        if not separator or name.strip() not in {"BLOB_READ_WRITE_TOKEN", "BLOB_STORE_ID", "VERCEL_OIDC_TOKEN"}:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ.setdefault(name.strip(), value)


def _blob_configured() -> bool:
    _load_root_env()
    return bool(
        os.environ.get("BLOB_READ_WRITE_TOKEN")
        or (os.environ.get("BLOB_STORE_ID") and os.environ.get("VERCEL_OIDC_TOKEN"))
    )


def _blob_client():
    try:
        from vercel.blob import sync as blob
    except ImportError as error:
        raise RuntimeError("Vercel Blob necesita Python 3.10+ y el paquete vercel-blob") from error
    return blob


def _read_local(local_path: Optional[Path]) -> Tuple[Dict[str, object], Optional[str]]:
    path = local_path or ROOT / "historico_partidos.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        payload = {"partidos": []}
    if not isinstance(payload, dict) or not isinstance(payload.get("partidos"), list):
        payload = {"partidos": []}
    return payload, None


def read_history(local_path: Optional[Path] = None) -> Tuple[Dict[str, object], Optional[str]]:
    """Read Vercel Blob when configured; otherwise use the local JSON for development."""
    if not _blob_configured():
        return _read_local(local_path)
    with _LOCK:
        blob = _blob_client()
        try:
            result = blob.get_blob(BLOB_PATH, access="private")
            payload = json.loads(result.body.decode("utf-8"))
            if not isinstance(payload, dict) or not isinstance(payload.get("partidos"), list):
                raise ValueError("El histórico de Vercel Blob no tiene el formato esperado")
            return payload, result.metadata.etag
        except (FileNotFoundError, getattr(blob, "BlobNotFoundError", FileNotFoundError)):
            # Bootstrap the private store from any local records on first connection.
            payload, _ = _read_local(local_path)
            write_history(payload, local_path, expected_etag=None, creating=True)
            return payload, None


def write_history(
    payload: Dict[str, object],
    local_path: Optional[Path] = None,
    expected_etag: Optional[str] = None,
    creating: bool = False,
) -> None:
    """Persist the snapshot in Blob with conditional writes; local JSON is dev fallback."""
    data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    if _blob_configured():
        with _LOCK:
            blob = _blob_client()
            kwargs = {
                "access": "private",
                "content_type": "application/json; charset=utf-8",
                "allow_overwrite": not creating,
                "cache_control_max_age": 60,
            }
            if expected_etag:
                kwargs["if_match"] = expected_etag
            blob.put_blob(BLOB_PATH, data, **kwargs)
        return

    path = local_path or ROOT / "historico_partidos.json"
    temporal = path.with_name(path.name + ".tmp")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporal.write_bytes(data)
    temporal.replace(path)
