from pathlib import Path

import pytest

from ai_workshop.supabase.vendor import SUPABASE_SOURCE_URL, SupabaseVendor


class FakeVendor:
    def __init__(self):
        self.calls = []

    def vendor(self, ref: str, destination: Path):
        self.calls.append((ref, destination))
        return {"ref": ref, "destination": str(destination)}


def test_supabase_vendor_requires_pinned_ref(tmp_path: Path):
    version = tmp_path / "version"
    version.write_text("\n", encoding="utf-8")
    with pytest.raises(ValueError, match="pinned ref"):
        SupabaseVendor(FakeVendor()).vendor_from_version_file(version, tmp_path / "out")


def test_supabase_vendor_uses_version_file(tmp_path: Path):
    version = tmp_path / "version"
    version.write_text("self-hosted/v0.8.2\n", encoding="utf-8")
    fake = FakeVendor()
    result = SupabaseVendor(fake).vendor_from_version_file(version, tmp_path / "out")
    assert fake.calls == [("self-hosted/v0.8.2", tmp_path / "out")]
    assert result["ref"] == "self-hosted/v0.8.2"
    assert SUPABASE_SOURCE_URL == "https://github.com/supabase/supabase.git"
