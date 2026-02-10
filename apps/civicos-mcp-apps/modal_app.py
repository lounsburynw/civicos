"""
Modal deployment for CivicOS MCP Apps Server.

Interactive UI widgets that render directly in AI hosts (Claude.ai, ChatGPT).
Enables real-time civic participation through embedded interfaces.

Widgets:
    - voice: Support/Oppose/Watch civic items with real-time counts
    - pulse: City dashboard (upcoming meetings, trending topics, local issues)

Endpoint:
    civicos--civicos-mcp-apps-mcp-apps-server.modal.run

Deploy:
    modal deploy apps/civicos-mcp-apps/modal_app.py

Architecture:
    AI Host (Claude.ai) → MCP Apps Server → Jurisdiction MCP (civic data)
                                         → Relay (real-time events)
"""

import modal
import os
from pathlib import Path

# Get directory containing this script for relative paths
APP_DIR = Path(__file__).parent

# Node.js image with TypeScript support
# Modal 1.0 API: use add_local_file/add_local_dir instead of copy_local_file/copy_local_dir
node_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("curl", "gnupg")
    .run_commands(
        # Install Node.js 20.x
        "curl -fsSL https://deb.nodesource.com/setup_20.x | bash -",
        "apt-get install -y nodejs",
    )
    .workdir("/app")
    # Copy package files first for better caching
    # copy=True required since we run build steps after adding files
    .add_local_file(str(APP_DIR / "package.json"), "/app/package.json", copy=True)
    .add_local_file(str(APP_DIR / "package-lock.json"), "/app/package-lock.json", copy=True)
    .run_commands("npm install")
    # Copy source files
    .add_local_dir(str(APP_DIR / "src"), "/app/src", copy=True)
    .add_local_file(str(APP_DIR / "tsconfig.json"), "/app/tsconfig.json", copy=True)
    .add_local_file(str(APP_DIR / "vite.config.ts"), "/app/vite.config.ts", copy=True)
    .add_local_file(str(APP_DIR / "server.ts"), "/app/server.ts", copy=True)
    # Service registry (URL config)
    .add_local_file(str(APP_DIR.parent.parent / "config" / "registry.json"), "/app/registry.json", copy=True)
    # Build widgets (generates dist/widgets/{voice,pulse}/...)
    .run_commands("npm run build")
)

app = modal.App("civicos-mcp-apps")


@app.function(
    image=node_image,
    secrets=[modal.Secret.from_name("civicos-env")],
    memory=512,
    timeout=300,
    min_containers=0,  # Scale to zero when not in use
    max_containers=20,  # Modal 1.0: renamed from concurrency_limit
)
@modal.web_server(port=3002, startup_timeout=30)
def mcp_apps_server():
    """
    Start the MCP Apps HTTP server.

    Modal's web_server decorator runs this function and proxies HTTP traffic
    to the specified port. The Node.js Express server handles requests directly.
    """
    import subprocess

    # Get URLs from environment, falling back to registry defaults
    import json
    registry = json.load(open("/app/registry.json")) if os.path.exists("/app/registry.json") else {}
    default_jur = registry.get("default_jurisdiction", "")
    jur_domain = registry.get("jurisdictions", {}).get(default_jur, {}).get("domain", "")
    jurisdiction_url = os.environ.get("JURISDICTION_MCP_URL") or (f"https://{jur_domain}" if jur_domain else "")
    relay_url = os.environ.get("RELAY_URL") or registry.get("relay", {}).get("url", "")
    personal_mcp_url = os.environ.get("PERSONAL_MCP_URL", "")

    # Set environment variables for the Node.js server
    env = os.environ.copy()
    env["PORT"] = "3002"
    env["JURISDICTION_MCP_URL"] = jurisdiction_url
    env["RELAY_URL"] = relay_url
    if personal_mcp_url:
        env["PERSONAL_MCP_URL"] = personal_mcp_url

    print(f"Starting MCP Apps Server on port 3002")
    print(f"Jurisdiction MCP URL: {jurisdiction_url}")
    print(f"Relay URL: {relay_url}")

    # Start the Node.js server using tsx (TypeScript execution)
    # tsx is installed as a devDependency and handles server.ts directly
    # Use Popen (non-blocking) instead of run() - Modal's @web_server requires this
    subprocess.Popen(
        ["npx", "tsx", "server.ts"],
        cwd="/app",
        env=env,
    )


@app.local_entrypoint()
def main():
    """Local entrypoint for testing."""
    print("CivicOS MCP Apps Server")
    print()
    print("Interactive UI widgets for AI hosts (Claude.ai, ChatGPT)")
    print()
    print("Deploy: modal deploy apps/civicos-mcp-apps/modal_app.py")
    print("Endpoint: civicos--civicos-mcp-apps-mcp-apps-server.modal.run")
    print()
    print("Widgets:")
    print("  voice - Support/Oppose/Watch civic items with real-time counts")
    print("  pulse - City dashboard (meetings, topics, issues)")
