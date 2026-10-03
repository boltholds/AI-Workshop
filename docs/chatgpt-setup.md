# Connect AI Workshop to ChatGPT

AI Workshop keeps its MCP server private on http://127.0.0.1:8765/mcp. ChatGPT does not connect directly to localhost. For a developer machine or another private network, use OpenAI Secure MCP Tunnel so the MCP server stays off the public internet.

Current OpenAI references:

- Secure MCP Tunnel: https://developers.openai.com/api/docs/guides/secure-mcp-tunnels
- ChatGPT developer mode / MCP apps: https://help.openai.com/en/articles/12584461-developer-mode-and-mcp-apps-in-chatgpt
- tunnel-client releases: https://github.com/openai/tunnel-client/releases/latest

## 1. Bootstrap AI Workshop

Windows:

~~~powershell
.\scripts\bootstrap.ps1 -Project C:\Code\MyProject
~~~

macOS/Linux:

~~~bash
bash scripts/bootstrap.sh --project /path/to/MyProject
~~~

The first run creates:

- .env.local with independent random Workshop control tokens;
- config/projects.local.yaml for the supplied project folder;
- config/recovery.local.yaml from the generic safe example;
- generated Compose files and runtime state under .workshop/.

Existing local secrets and YAML files are preserved on later runs.

After bootstrap, the private MCP endpoint is:

~~~text
http://127.0.0.1:8765/mcp
~~~

Do not expose this port directly to the public internet.

## 2. Create an OpenAI Secure MCP Tunnel

In OpenAI Platform tunnel settings, create a tunnel and associate it with the ChatGPT workspace that should use AI Workshop. The machine running tunnel-client needs outbound HTTPS access to OpenAI and local access to http://127.0.0.1:8765/mcp.

Download the current tunnel-client from Platform tunnel settings or the latest public release. Do not pin a release URL in automation; OpenAI's tunnel documentation recommends using the latest release.

You need:

- a tunnel ID such as tunnel_...;
- a runtime control-plane API key;
- tunnel-client on your PATH.

The runtime key is supplied through CONTROL_PLANE_API_KEY. AI Workshop does not generate, store, or commit this OpenAI credential.

## 3. Initialize the local tunnel profile

Windows:

~~~powershell
$env:CONTROL_PLANE_API_KEY = "..."
$env:AI_WORKSHOP_TUNNEL_ID = "tunnel_..."
.\scripts\tunnel.ps1 -Init
~~~

macOS/Linux:

~~~bash
export CONTROL_PLANE_API_KEY="..."
export AI_WORKSHOP_TUNNEL_ID="tunnel_..."
bash scripts/tunnel.sh --init
~~~

The helper configures the tunnel profile against:

~~~text
http://127.0.0.1:8765/mcp
~~~

Before running the tunnel it executes tunnel-client doctor --profile ai-workshop --explain.

For later sessions, the profile already exists.

Windows:

~~~powershell
$env:CONTROL_PLANE_API_KEY = "..."
.\scripts\tunnel.ps1
~~~

macOS/Linux:

~~~bash
export CONTROL_PLANE_API_KEY="..."
bash scripts/tunnel.sh
~~~

Keep tunnel-client run alive while ChatGPT is using the app.

## 4. Add AI Workshop in ChatGPT

Enable Developer mode for the target ChatGPT workspace/account. In ChatGPT Plugins, create a developer-mode app, choose Tunnel as the connection type, and select the tunnel associated with the workspace or provide its tunnel ID when the UI offers that option.

OpenAI's current product availability matters:

- full MCP, including write/modify actions, is currently available in beta for ChatGPT Business, Enterprise, and Edu workspaces;
- Pro users can connect custom MCP apps in developer mode for read/fetch permissions, but full write/modify MCP is not currently available there.

AI Workshop intentionally exposes mutation tools such as filesystem writes, shell execution, service restart/rebuild, and confirmed restore. To use that full surface from ChatGPT, use a workspace tier that supports full MCP write/modify actions. Otherwise keep the same Workshop server and use only the capabilities allowed by the OpenAI surface you are connecting from.

## 5. Verify the connection

Locally, verify Workshop first:

~~~bash
uv run ai-workshop doctor \
  --projects config/projects.local.yaml \
  --workspace-url http://127.0.0.1:8766 \
  --gateway-host 127.0.0.1 \
  --gateway-port 8765 \
  --browser-url http://127.0.0.1:8767
~~~

Then verify the tunnel:

~~~bash
tunnel-client doctor --profile ai-workshop --explain
~~~

The tunnel client also exposes local health/readiness/admin surfaces. Keep those loopback-only unless you deliberately need remote operator access.

## Security model

Secure MCP Tunnel is outbound-only from the machine running AI Workshop. The Workshop MCP port remains bound to loopback and does not require an inbound firewall rule or a public reverse proxy.

Only connect AI Workshop to OpenAI workspaces and Platform organizations you control and trust. AI Workshop has intentionally powerful development tools; ChatGPT may ask for confirmation before write/modify actions depending on app permissions and action context.


## Server Mode (recommended for a dedicated host)

Server Mode exposes a private MCP gateway on host loopback:

~~~text
http://127.0.0.1:8765/mcp
~~~

The production Compose service is named `gateway`. It uses the canonical Server Mode project registry, credential store, and Git services from the same persistent `/state` and `/var/lib/ai-workshop/storage` domains as the rest of Server Mode.

Start or recreate it:

~~~bash
cd /opt/ai-workshop
docker-compose -f deploy/server/compose.yaml up -d --build gateway
docker-compose -f deploy/server/compose.yaml ps gateway
~~~

Verify the local listener:

~~~bash
curl -i http://127.0.0.1:8765/mcp
~~~

A plain GET may return a method/protocol response rather than an MCP session; the important deployment check is that the loopback listener is reachable. For protocol validation, use MCP Inspector or the Secure MCP Tunnel doctor.

The Server Mode gateway intentionally does not mount the rootless Docker socket. Runtime/container control remains behind the Server Mode control boundary.

### Create the Secure MCP Tunnel

Create a tunnel in OpenAI Platform tunnel settings and associate it with the ChatGPT workspace that will use AI Workshop.

On the AI Workshop host:

~~~bash
export CONTROL_PLANE_API_KEY="..."
export AI_WORKSHOP_TUNNEL_ID="tunnel_..."

tunnel-client init   --profile ai-workshop-server   --tunnel-id "$AI_WORKSHOP_TUNNEL_ID"   --mcp-server-url http://127.0.0.1:8765/mcp

tunnel-client doctor   --profile ai-workshop-server   --explain

tunnel-client run   --profile ai-workshop-server
~~~

Keep `tunnel-client run` healthy while ChatGPT is using the app. The tunnel is outbound-only; do not publish port 8765 to the LAN or Internet.

### Add the Server Mode app in ChatGPT

1. Enable Developer mode for the target ChatGPT workspace/account.
2. Open ChatGPT Plugins and choose the plus button to create a developer-mode app.
3. Choose **Tunnel** as the connection type.
4. Select the tunnel associated with the workspace, or provide `AI_WORKSHOP_TUNNEL_ID` if the UI asks for it.
5. Name the app `AI Workshop`.
6. Review the discovered MCP tools before saving the connection.

The initial Server Mode gateway exposes server-native project and Git operations, including confirmation-gated destructive Git actions. Desktop-only workspace filesystem/shell tools are not exposed by this Server Mode composition.

As more Server Mode AgentRun and dynamic MCP services are composed into the same gateway, the app endpoint and tunnel stay unchanged; only the discovered tool catalog expands.


### Private Git repositories through the plugin

The Server Mode plugin exposes write-only credential tools:

~~~text
credentials_list
credentials_get
credentials_create_ssh
credentials_create_https_token
~~~

Credential secrets are accepted only on create calls. Tool responses contain metadata only and never return the stored secret material.

For GitHub over SSH, create a profile such as `github-main` with `credentials_create_ssh`, then clone with:

~~~text
git_clone(
  project_id="plc-web",
  remote_url="git@github.com:boltholds/PLC-web.git",
  credential_id="github-main"
)
~~~

For HTTPS token authentication, use `credentials_create_https_token`, then pass the same `credential_id` to `git_clone`.

The credential secret is stored under the Server Mode credential secret root with owner-only permissions and is not exposed through `credentials_list` or `credentials_get`.
