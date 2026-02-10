"""
Modal deployment for CivicOS Personal MCP Server.

User's edge agent for personalized civic participation.
Handles identity, signing, context, and personalization.

Tools (17):
    - Identity: status, create, import, unlock, lock
    - Signing: voice, commitment, completion, event
    - Context: set_neighborhood, set_interests, follow/unfollow, get_context
    - Queries: get_relevant_now, get_suggestions, explain_relevance

Endpoint:
    civicos-personal-mcp--personal-mcp-server-web.modal.run

Deploy:
    modal deploy apps/civicos-personal-mcp/modal_app.py

Architecture:
    Open WebUI → Personal MCP (HTTP) → Jurisdiction MCP (for civic data)

    - Queries Jurisdiction MCP for civic data (read-only)
    - Stores user context locally (never sent to server)
    - Signs actions with user's keys (client-side only)
"""

import modal
import os

# Node.js image with TypeScript support
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
    .add_local_file("package.json", "/app/package.json", copy=True)
    .add_local_file("package-lock.json", "/app/package-lock.json", copy=True)
    .run_commands("npm install")
    # Copy source files
    .add_local_dir("src", "/app/src", copy=True)
    .add_local_dir("lib", "/app/lib", copy=True)
    .add_local_file("tsconfig.json", "/app/tsconfig.json", copy=True)
    # Service registry (URL config)
    .add_local_file("config/registry.json", "/app/registry.json", copy=True)
    .run_commands("npm run build")
)

app = modal.App("civicos-personal-mcp")


@app.function(
    image=node_image,
    secrets=[modal.Secret.from_name("civicos-env")],
    memory=512,
    timeout=300,
    min_containers=0,  # Scale to zero when not in use
    max_containers=20,
)
@modal.web_server(port=8081, startup_timeout=120)
def personal_mcp_server():
    """
    Start the Personal MCP HTTP server.

    Modal's web_server decorator runs this function and proxies HTTP traffic
    to the specified port. The Node.js Express server handles requests directly.
    """
    import subprocess

    # Get jurisdiction MCP URL from environment, falling back to registry
    import json
    registry = json.load(open("/app/registry.json")) if os.path.exists("/app/registry.json") else {}
    default_jur = registry.get("default_jurisdiction", "")
    jur_domain = registry.get("jurisdictions", {}).get(default_jur, {}).get("domain", "")
    jurisdiction_url = os.environ.get("JURISDICTION_MCP_URL") or (f"https://{jur_domain}/mcp" if jur_domain else "")

    # Set environment variables for the Node.js server
    env = os.environ.copy()
    env["PORT"] = "8081"
    env["JURISDICTION_MCP_URL"] = jurisdiction_url

    print(f"Starting Personal MCP HTTP Server on port 8081")
    print(f"Jurisdiction MCP URL: {jurisdiction_url}")

    # Start the Node.js HTTP server (non-blocking for Modal web_server)
    subprocess.Popen(
        ["node", "dist/src/http-server.js"],
        cwd="/app",
        env=env,
    )


@app.local_entrypoint()
def main():
    """Local entrypoint for testing."""
    print("CivicOS Personal MCP Server")
    print()
    print("User's edge agent for personalized civic participation.")
    print()
    print("Deploy: modal deploy apps/civicos-personal-mcp/modal_app.py")
    print("Endpoint: civicos-personal-mcp--personal-mcp-server-web.modal.run")
    print()
    print("Tools (17):")
    print("  Identity: status, create, import, unlock, lock")
    print("  Signing:  voice, commitment, completion, event")
    print("  Context:  set_neighborhood, set_interests, follow/unfollow, get_context")
    print("  Queries:  get_relevant_now, get_suggestions, explain_relevance")
