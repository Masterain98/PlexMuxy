import hashlib

from scripts.verify_release import verify


def test_release_verifier_accepts_valid_assets_and_rejects_traversal(tmp_path):
    artifact = tmp_path / "artifact.zip"
    artifact.write_bytes(b"release")
    checksums = tmp_path / "SHA256SUMS.txt"
    checksums.write_text(f"{hashlib.sha256(b'release').hexdigest()}  artifact.zip\n", encoding="ascii")
    assert verify(tmp_path, checksums) == []
    checksums.write_text(f"{'0' * 64}  ../secret\n", encoding="ascii")
    assert "unsafe artifact" in verify(tmp_path, checksums)[0]
