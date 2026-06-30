"""Tests for server constants module."""

import string

from constants import (
    compute_file_hash,
    generate_rcon_password,
    sanitize_filename,
)


class TestSanitizeFilename:
    def test_valid_filename(self):
        assert sanitize_filename("r.0.0.mca") == "r.0.0.mca"

    def test_rejects_path_traversal(self):
        try:
            sanitize_filename("../../etc/passwd")
            raise AssertionError("Should have raised ValueError")
        except ValueError:
            pass

    def test_rejects_absolute_path(self):
        try:
            sanitize_filename("/etc/passwd")
            raise AssertionError("Should have raised ValueError")
        except ValueError:
            pass

    def test_strips_directory(self):
        assert sanitize_filename("some/dir/file.txt") == "file.txt"

    def test_rejects_dotdot_in_parts(self):
        try:
            sanitize_filename("foo/../bar.txt")
            raise AssertionError("Should have raised ValueError")
        except ValueError:
            pass


class TestGenerateRconPassword:
    def test_length(self):
        pw = generate_rcon_password()
        assert len(pw) == 32

    def test_alphanumeric(self):
        pw = generate_rcon_password()
        assert all(c in string.ascii_letters + string.digits for c in pw)

    def test_unique(self):
        passwords = {generate_rcon_password() for _ in range(100)}
        assert len(passwords) == 100


class TestComputeFileHash:
    def test_hash(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_bytes(b"hello world")
        h = compute_file_hash(f)
        assert len(h) == 64
        assert isinstance(h, str)
