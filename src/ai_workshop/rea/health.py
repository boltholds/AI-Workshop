"""Probe the sidecar's authenticated health endpoint through its Unix socket."""
import os
import httpx2


def main():
    transport = httpx2.HTTPTransport(uds='/run/rea/mcp.sock', trust_env=False)
    with httpx2.Client(transport=transport, timeout=5, trust_env=False) as client:
        response = client.get('http://rea-mcp:8796/health', headers={
            'Authorization': 'Bearer ' + os.environ['AI_WORKSHOP_REA_TOKEN'],
        })
        response.raise_for_status()


if __name__ == '__main__':
    main()
