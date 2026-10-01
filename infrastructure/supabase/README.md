# Optional Supabase adapter

Supabase is a reference external-stack adapter for AI Workshop. It is not required by the core runtime.

The pinned version lives in `config/supabase.version`. Vendoring copies only the upstream `docker/` subtree into private `.workshop/vendor/supabase` state and records a checksum manifest.

The Workshop override attaches the upstream API gateway to the shared `ai-workshop` network. Secrets must be generated into `.workshop/secrets/` and must never be committed.

Before enabling this adapter, validate the final merged Compose configuration against the pinned upstream release. AI Workshop's global rule remains that no container receives the host Docker socket.
