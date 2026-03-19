#!/usr/bin/env python3
"""Deploy Cloudflare proxy workers for jurisdiction domains.

Routes:
  /relay/*        → Relay origin (strip /relay prefix)
  everything else → MCP origin (handles /mcp, /api/tools/*, /health, /openapi.json)

Usage:
  python3 scripts/deploy_proxy_workers.py             # Deploy all 3
  python3 scripts/deploy_proxy_workers.py san-rafael   # Deploy one
"""

import json
import os
import sys
import urllib.request
import urllib.error

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

CF_ACCOUNT = "2bdd8aed2560f0a2632f4178adfe6d9f"
CF_API = "https://api.cloudflare.com/client/v4"
TOKEN = os.environ.get("CLOUDFLARE_CIVICOS_TOKEN", "")

RELAY_ORIGIN = "https://civicos--civicos-relay-relayserver-relay-endpoint.modal.run"

JURISDICTIONS = {
    "san-rafael": {
        "worker": "civicos-san-rafael-proxy",
        "mcp_origin": "https://civicos--civicos-san-rafael-mcpserver-mcp-endpoint.modal.run",
    },
    "california": {
        "worker": "civicos-california-proxy",
        "mcp_origin": "https://civicos--civicos-california-mcpserver-mcp-endpoint.modal.run",
    },
    "federal": {
        "worker": "civicos-federal-proxy",
        "mcp_origin": "https://civicos--civicos-federal-mcpserver-mcp-endpoint.modal.run",
    },
    "county-marin": {
        "worker": "civicos-county-marin-proxy",
        "mcp_origin": "https://civicos--civicos-county-marin-mcpserver-mcp-endpoint.modal.run",
    },
}


def generate_worker_js(mcp_origin: str, relay_origin: str) -> str:
    return f'''export default {{
  async fetch(request) {{
    const url = new URL(request.url);

    // Handle CORS preflight
    if (request.method === "OPTIONS") {{
      return new Response(null, {{
        headers: {{
          "Access-Control-Allow-Origin": "*",
          "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
          "Access-Control-Allow-Headers": "Content-Type, Authorization, Accept, X-Requested-With",
          "Access-Control-Max-Age": "86400",
        }},
      }});
    }}

    let modalBase, pathname;

    if (url.pathname.startsWith("/relay")) {{
      // Relay — strip /relay prefix
      modalBase = "{relay_origin}";
      pathname = url.pathname.slice("/relay".length) || "/";
    }} else {{
      // Everything else → MCP origin (handles /mcp, /api/tools/*, /health, /openapi.json)
      modalBase = "{mcp_origin}";
      pathname = url.pathname;
    }}

    const modalUrl = modalBase + pathname + url.search;
    const headers = new Headers(request.headers);
    headers.set("Host", new URL(modalBase).host);

    const response = await fetch(modalUrl, {{
      method: request.method,
      headers: headers,
      body: request.body,
    }});

    const newResponse = new Response(response.body, response);
    newResponse.headers.set("Access-Control-Allow-Origin", "*");
    return newResponse;
  }}
}}
'''


def deploy_worker(slug: str) -> bool:
    config = JURISDICTIONS[slug]
    worker_name = config["worker"]
    js = generate_worker_js(config["mcp_origin"], RELAY_ORIGIN)

    print(f"Deploying {worker_name}...")

    boundary = "----WorkerUploadBoundary"
    metadata = json.dumps({"main_module": "worker.js"})
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="worker.js"; filename="worker.js"\r\n'
        f"Content-Type: application/javascript+module\r\n\r\n"
        f"{js}\r\n"
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="metadata"; filename="metadata.json"\r\n'
        f"Content-Type: application/json\r\n\r\n"
        f"{metadata}\r\n"
        f"--{boundary}--\r\n"
    )

    req = urllib.request.Request(
        f"{CF_API}/accounts/{CF_ACCOUNT}/workers/scripts/{worker_name}",
        data=body.encode(),
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="PUT",
    )

    try:
        resp = urllib.request.urlopen(req)
        result = json.loads(resp.read())
        if result.get("success"):
            print(f"  ✓ {worker_name} deployed")
            return True
        else:
            print(f"  ✗ {worker_name} FAILED: {result.get('errors', [])}")
            return False
    except urllib.error.HTTPError as e:
        print(f"  ✗ {worker_name} HTTP {e.code}: {e.read().decode()[:300]}")
        return False


def main():
    if not TOKEN:
        print("Error: CLOUDFLARE_CIVICOS_TOKEN not set in .env")
        sys.exit(1)

    target = sys.argv[1] if len(sys.argv) > 1 else "all"
    slugs = list(JURISDICTIONS.keys()) if target == "all" else [target]

    if target != "all" and target not in JURISDICTIONS:
        print(f"Unknown jurisdiction: {target}")
        print(f"Valid: {', '.join(JURISDICTIONS.keys())}")
        sys.exit(1)

    failed = []
    for slug in slugs:
        if not deploy_worker(slug):
            failed.append(slug)

    print()
    if failed:
        print(f"FAILED: {', '.join(failed)}")
        sys.exit(1)
    else:
        print("All deployed. Verify:")
        print("  curl -s https://san-rafael.civicosproject.org/mcp/health")
        print("  curl -s -o /dev/null -w '%{http_code}' https://san-rafael.civicosproject.org/health")


if __name__ == "__main__":
    main()
