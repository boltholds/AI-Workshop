from __future__ import annotations

from pathlib import Path

from ai_workshop.adapters.vendor import GitSubtreeVendor


SUPABASE_SOURCE_URL = "https://github.com/supabase/supabase.git"


class SupabaseVendor:
    def __init__(self, vendor=None):
        self.vendor = vendor or GitSubtreeVendor(
            adapter_id="supabase",
            source_url=SUPABASE_SOURCE_URL,
            subtree="docker",
        )

    def vendor_from_version_file(self, version_file: Path, destination: Path):
        ref = version_file.read_text(encoding="utf-8").strip()
        if not ref:
            raise ValueError("a pinned ref is required")
        if not ref.startswith("self-hosted/v"):
            raise ValueError("Supabase adapter requires a self-hosted/v* pinned ref")
        return self.vendor.vendor(ref, destination)
