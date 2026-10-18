import hashlib

import pytest

from scripts.desktop_checksums import manifest


def test_manifest_matches_actual_installer_bytes(tmp_path):
    (tmp_path / "SOURCE_COMMIT.txt").write_text("a" * 40 + "\n")
    (tmp_path / "GigMate-test.exe").write_bytes(b"synthetic installer")
    expected = hashlib.sha256(b"synthetic installer").hexdigest()
    first = manifest(tmp_path)
    assert f"{expected}  GigMate-test.exe\n" in first
    (tmp_path / "GigMate-test.exe").write_bytes(b"changed installer")
    assert manifest(tmp_path) != first


def test_no_installers_or_invalid_provenance_refuses_manifest(tmp_path):
    with pytest.raises(ValueError, match="NO_DESKTOP_INSTALLERS"):
        manifest(tmp_path)
    (tmp_path / "GigMate-test.exe").write_bytes(b"synthetic installer")
    (tmp_path / "SOURCE_COMMIT.txt").write_text("unknown")
    with pytest.raises(ValueError, match="INVALID_SOURCE_COMMIT"):
        manifest(tmp_path)
