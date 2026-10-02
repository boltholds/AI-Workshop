# Forge integrations

AI Workshop keeps forge hosting APIs separate from Git transport and history. Git operations continue through the `git.*` subsystem; GitHub, GitLab, and Forgejo hosting operations use the provider-neutral `forge.*` subsystem.

## Profiles and credentials

A forge profile contains a provider kind, API base URL, and a credential profile ID. API tokens remain in `CredentialStore`; providers receive a scoped token context for the duration of a request and never receive the credential secret path.

External profiles require HTTPS. The `internal-http` transport is reserved for internal DNS names such as the optional embedded Forgejo service.

Projects are explicitly bound to a forge profile and repository. Mutating operations resolve the project binding first. Pull-request merge rejects a repository argument that does not exactly match the project's configured repository.

## MCP surface

The initial surface includes repository lookup, pull-request list/create/merge, issue list/create, release list/create, and confirmed repository deletion. Authorization is project-scoped through the existing identity/RBAC service.

Repository deletion is a two-step operation. First request a short-lived one-time confirmation, then submit that confirmation token. Reuse and expired confirmations are rejected.

## Embedded Forgejo

`infrastructure/forgejo/compose.yaml` provides an optional rootless Forgejo service. It has no host-published ports and joins the private Server Mode control network. External access should be added only through the authenticated ingress registry.

Persistent data is stored in named `ai-workshop-forgejo-data` and `ai-workshop-forgejo-config` volumes. Disabling or removing the service does not imply deleting those volumes. Data deletion must remain a separate explicit operation.

Use `config/forgejo.example.yaml` as the profile template. Create the referenced HTTPS-token credential separately and bind projects to `forge-internal` as needed.
