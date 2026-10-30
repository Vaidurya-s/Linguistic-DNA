import hashlib
import importlib.util
import io

from app.config import REPO_ROOT

spec = importlib.util.spec_from_file_location("fetch_data", REPO_ROOT / "scripts" / "fetch_data.py")
fetch_data = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fetch_data)


def test_unpinned_file_is_downloaded_once_and_its_checksum_reported(tmp_path, monkeypatch):
    payload = b"PK\x03\x04 archive"
    calls = []

    def urlopen(req, timeout):
        calls.append(req.full_url)
        return io.BytesIO(payload)

    monkeypatch.setattr(fetch_data.urllib.request, "urlopen", urlopen)
    entry = {
        "id": "starling-ie",
        "url": "https://example.org/IE.exe",
        "sha256": None,
        "unpinned": True,
        "dest": "starling/IE.exe",
    }
    digest = hashlib.sha256(payload).hexdigest()
    first = fetch_data.fetch_http(entry, tmp_path)
    assert first.startswith("downloaded (unpinned") and digest in first
    assert (tmp_path / "starling" / "IE.exe").read_bytes() == payload
    again = fetch_data.fetch_http(entry, tmp_path)
    assert again == f"ok (cached; unpinned, sha256 {digest})"
    assert len(calls) == 1
