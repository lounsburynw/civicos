"""
OAuth 2.1 provider for CivicOS MCP servers.

Enables Claude.ai web/mobile users to connect via Settings > Connectors.
Implements the MCP OAuth authorization spec (2025-03-26) with PKCE.

Flow:
1. Claude POSTs to /mcp without auth → 401 with WWW-Authenticate
2. Claude discovers /.well-known/oauth-protected-resource
3. Claude fetches /.well-known/oauth-authorization-server
4. Claude registers via /register (DCR) → gets client_id
5. Claude opens /authorize in browser → user sees consent page
6. User clicks Allow → auth code issued → redirect to Claude callback
7. Claude exchanges code at /token → gets access_token + refresh_token
8. Claude includes Bearer <token> on all MCP requests → free tier
"""

import base64
import hashlib
import logging
import secrets
import time

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

logger = logging.getLogger("civicos-mcp.oauth")

# ─────────── In-memory stores ───────────
# Reset on container restart → users re-authenticate (acceptable for free tier)

_clients: dict[str, dict] = {}
_auth_codes: dict[str, dict] = {}
_access_tokens: dict[str, dict] = {}
_refresh_tokens: dict[str, dict] = {}

TOKEN_TTL = 7 * 24 * 3600  # 7 days
REFRESH_TTL = 30 * 24 * 3600  # 30 days
CODE_TTL = 300  # 5 minutes


# ─────────── Token verification (called by BearerAuthMiddleware) ───────────

def verify_oauth_token(token: str) -> dict | None:
    """Check if a token is a valid OAuth access token. Returns token info or None."""
    _prune_expired()
    info = _access_tokens.get(token)
    if not info:
        return None
    if time.time() > info["expires_at"]:
        del _access_tokens[token]
        return None
    return info


def _prune_expired():
    """Remove expired tokens and codes. Called periodically."""
    now = time.time()
    for code in [k for k, v in _auth_codes.items() if now > v["expires_at"]]:
        del _auth_codes[code]
    for token in [k for k, v in _access_tokens.items() if now > v["expires_at"]]:
        del _access_tokens[token]
    for token in [k for k, v in _refresh_tokens.items()
                  if now - v["issued_at"] > REFRESH_TTL]:
        del _refresh_tokens[token]


# ─────────── PKCE helpers ───────────

def _verify_pkce(code_verifier: str, code_challenge: str, method: str) -> bool:
    """Verify PKCE code_verifier against stored code_challenge."""
    if method != "S256":
        return False
    digest = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode()).digest()
    ).rstrip(b"=").decode()
    return digest == code_challenge


def _html_redirect(url: str) -> HTMLResponse:
    """Return a 200 HTML response that redirects the browser client-side.

    We use 200+HTML+JS instead of a 302 redirect because the Cloudflare
    Worker in front of *.civicosproject.org throws error 1101 ("Worker
    threw exception") on 302 responses with external Location headers.
    Browsers handle this identically to a server-side redirect, and the
    MCP OAuth client (Claude.ai) also follows it since it's implemented
    with a browser window (webbrowser.open()).
    """
    # Escape for use in attribute/JS contexts
    import html as html_mod
    safe_url_attr = html_mod.escape(url, quote=True)
    safe_url_js = url.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "")
    body = (
        "<!DOCTYPE html><html><head>"
        f'<meta http-equiv="refresh" content="0; url={safe_url_attr}">'
        "<title>Redirecting…</title></head><body>"
        f'<p>Redirecting to <a href="{safe_url_attr}">{safe_url_attr}</a>…</p>'
        f"<script>window.location.replace('{safe_url_js}');</script>"
        "</body></html>"
    )
    return HTMLResponse(body, status_code=200)


# ─────────── Token issuance ───────────

def _issue_tokens(client_id: str) -> dict:
    """Issue a new access token and refresh token."""
    access_token = f"cos_{secrets.token_urlsafe(32)}"
    refresh_token = f"cosr_{secrets.token_urlsafe(32)}"
    now = time.time()

    _access_tokens[access_token] = {
        "client_id": client_id,
        "issued_at": now,
        "expires_at": now + TOKEN_TTL,
    }
    _refresh_tokens[refresh_token] = {
        "client_id": client_id,
        "issued_at": now,
        "access_token": access_token,
    }

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": TOKEN_TTL,
        "refresh_token": refresh_token,
        "scope": "mcp",
    }


# ─────────── Consent page HTML ───────────

_CONSENT_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Authorize — CivicOS</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: #f8f9fa;
    display: flex;
    justify-content: center;
    align-items: center;
    min-height: 100vh;
    padding: 20px;
  }}
  .card {{
    background: white;
    border-radius: 12px;
    box-shadow: 0 2px 12px rgba(0,0,0,0.08);
    max-width: 420px;
    width: 100%;
    padding: 32px;
  }}
  .logo {{ font-size: 28px; font-weight: 700; color: #1a1a2e; margin-bottom: 4px; }}
  .subtitle {{ color: #666; font-size: 14px; margin-bottom: 24px; }}
  .prompt {{ font-size: 16px; color: #333; margin-bottom: 8px; line-height: 1.5; }}
  .client-name {{ font-weight: 600; color: #1a1a2e; }}
  .jurisdiction {{ color: #4a6fa5; font-weight: 500; }}
  .scopes {{
    background: #f0f4f8;
    border-radius: 8px;
    padding: 16px;
    margin: 16px 0;
    font-size: 14px;
    color: #444;
  }}
  .scopes ul {{ list-style: none; padding: 0; }}
  .scopes li {{ padding: 4px 0; }}
  .scopes li::before {{ content: "\\2713\\0020"; color: #4a6fa5; font-weight: bold; }}
  .actions {{ display: flex; gap: 12px; margin-top: 24px; }}
  button {{
    flex: 1;
    padding: 12px;
    border-radius: 8px;
    font-size: 15px;
    font-weight: 500;
    cursor: pointer;
    border: none;
  }}
  .allow {{
    background: #1a1a2e;
    color: white;
  }}
  .allow:hover {{ background: #2a2a4e; }}
  .deny {{
    background: #e9ecef;
    color: #333;
  }}
  .deny:hover {{ background: #dee2e6; }}
  .note {{ font-size: 12px; color: #999; margin-top: 16px; text-align: center; }}
</style>
</head>
<body>
<div class="card">
  <div class="logo">CivicOS</div>
  <div class="subtitle">Local government data for AI assistants</div>
  <p class="prompt">
    <span class="client-name">{client_name}</span> wants to access
    civic data from <span class="jurisdiction">{display_name}</span>.
  </p>
  <div class="scopes">
    <ul>
      <li>Search meeting history and decisions</li>
      <li>View upcoming meetings and agendas</li>
      <li>Search legislation and municipal code</li>
      <li>Access public testimony and 311 reports</li>
    </ul>
  </div>
  <form method="post">
    <input type="hidden" name="state" value="{state}">
    <input type="hidden" name="redirect_uri" value="{redirect_uri}">
    <input type="hidden" name="code_challenge" value="{code_challenge}">
    <input type="hidden" name="code_challenge_method" value="{code_challenge_method}">
    <input type="hidden" name="client_id" value="{client_id}">
    <div class="actions">
      <button type="submit" name="action" value="deny" class="deny">Deny</button>
      <button type="submit" name="action" value="allow" class="allow">Allow</button>
    </div>
  </form>
  <p class="note">Free tier &middot; Public data only &middot; No account required</p>
</div>
</body>
</html>"""


# ─────────── Router factory ───────────

def create_oauth_router(server_url: str, display_name: str) -> APIRouter:
    """Create FastAPI router with MCP OAuth 2.1 endpoints.

    Args:
        server_url: Base URL of the server (e.g. https://san-rafael.civicosproject.org)
        display_name: Jurisdiction display name for the consent page
    """
    router = APIRouter(tags=["OAuth"])
    mcp_resource = f"{server_url}/mcp"

    # ── Protected Resource Metadata (RFC 9728) ──

    @router.get("/.well-known/oauth-protected-resource")
    async def protected_resource_metadata():
        return JSONResponse({
            "resource": mcp_resource,
            "authorization_servers": [server_url],
            "bearer_methods_supported": ["header"],
            "scopes_supported": ["mcp"],
        })

    # ── Authorization Server Metadata (RFC 8414) ──

    @router.get("/.well-known/oauth-authorization-server")
    async def authorization_server_metadata():
        return JSONResponse({
            "issuer": server_url,
            "authorization_endpoint": f"{server_url}/authorize",
            "token_endpoint": f"{server_url}/token",
            "registration_endpoint": f"{server_url}/register",
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code", "refresh_token"],
            "code_challenge_methods_supported": ["S256"],
            "token_endpoint_auth_methods_supported": ["none", "client_secret_post"],
            "scopes_supported": ["mcp"],
        })

    # Also serve at the OIDC well-known path (fallback discovery)
    @router.get("/.well-known/openid-configuration")
    async def oidc_configuration():
        return await authorization_server_metadata()

    # ── Dynamic Client Registration (RFC 7591) ──

    @router.post("/register")
    async def register_client(request: Request):
        body = await request.json()
        client_id = f"civic_{secrets.token_urlsafe(16)}"
        registration = {
            "client_id": client_id,
            "client_name": body.get("client_name", "Unknown"),
            "redirect_uris": body.get("redirect_uris", []),
            "grant_types": body.get("grant_types", ["authorization_code"]),
            "response_types": body.get("response_types", ["code"]),
            "token_endpoint_auth_method": body.get(
                "token_endpoint_auth_method", "none"
            ),
            "registered_at": time.time(),
        }
        _clients[client_id] = registration
        logger.info("OAuth client registered: %s (%s)", client_id, registration["client_name"])
        return JSONResponse(registration, status_code=201)

    # ── Authorization endpoint ──

    @router.get("/authorize")
    async def authorize_get(request: Request):
        """Show the consent page."""
        params = dict(request.query_params)
        client_id = params.get("client_id", "")
        client = _clients.get(client_id, {})
        client_name = client.get("client_name", "An application")

        html = _CONSENT_HTML.format(
            client_name=client_name,
            display_name=display_name,
            state=params.get("state", ""),
            redirect_uri=params.get("redirect_uri", ""),
            code_challenge=params.get("code_challenge", ""),
            code_challenge_method=params.get("code_challenge_method", "S256"),
            client_id=client_id,
        )
        return HTMLResponse(html)

    @router.post("/authorize")
    async def authorize_post(request: Request):
        """Process consent form submission."""
        form = await request.form()
        action = form.get("action", "deny")
        redirect_uri = str(form.get("redirect_uri", ""))
        state = str(form.get("state", ""))

        if action != "allow":
            sep = "&" if "?" in redirect_uri else "?"
            return _html_redirect(
                f"{redirect_uri}{sep}error=access_denied&state={state}"
            )

        client_id = str(form.get("client_id", ""))
        code_challenge = str(form.get("code_challenge", ""))
        code_challenge_method = str(form.get("code_challenge_method", "S256"))

        # Validate redirect_uri against client registration
        client = _clients.get(client_id)
        if client and redirect_uri not in client.get("redirect_uris", []):
            return JSONResponse(
                {"error": "invalid_request", "error_description": "redirect_uri mismatch"},
                status_code=400,
            )

        code = secrets.token_urlsafe(32)
        _auth_codes[code] = {
            "challenge": code_challenge,
            "method": code_challenge_method,
            "redirect_uri": redirect_uri,
            "client_id": client_id,
            "expires_at": time.time() + CODE_TTL,
        }

        sep = "&" if "?" in redirect_uri else "?"
        logger.info("OAuth authorization code issued for client %s", client_id)
        return _html_redirect(f"{redirect_uri}{sep}code={code}&state={state}")

    # ── Token endpoint ──

    @router.post("/token")
    async def token_endpoint(request: Request):
        """Exchange authorization code or refresh token for access token."""
        form = await request.form()
        grant_type = form.get("grant_type", "")

        if grant_type == "authorization_code":
            code = str(form.get("code", ""))
            code_verifier = str(form.get("code_verifier", ""))
            client_id = str(form.get("client_id", ""))

            entry = _auth_codes.pop(code, None)
            if not entry or time.time() > entry["expires_at"]:
                return JSONResponse({"error": "invalid_grant"}, status_code=400)

            # Validate client_id matches
            if entry.get("client_id") and entry["client_id"] != client_id:
                return JSONResponse({"error": "invalid_grant"}, status_code=400)

            # Verify PKCE
            if entry["challenge"]:
                if not _verify_pkce(code_verifier, entry["challenge"], entry["method"]):
                    return JSONResponse({"error": "invalid_grant"}, status_code=400)

            logger.info("OAuth token issued for client %s", client_id)
            return JSONResponse(_issue_tokens(client_id))

        if grant_type == "refresh_token":
            refresh = str(form.get("refresh_token", ""))
            entry = _refresh_tokens.pop(refresh, None)
            if not entry:
                return JSONResponse({"error": "invalid_grant"}, status_code=400)
            if time.time() - entry["issued_at"] > REFRESH_TTL:
                return JSONResponse({"error": "invalid_grant"}, status_code=400)

            # Revoke the old access token
            old_access = entry.get("access_token")
            if old_access and old_access in _access_tokens:
                del _access_tokens[old_access]

            client_id = entry.get("client_id", "")
            logger.info("OAuth token refreshed for client %s", client_id)
            return JSONResponse(_issue_tokens(client_id))

        return JSONResponse({"error": "unsupported_grant_type"}, status_code=400)

    return router
