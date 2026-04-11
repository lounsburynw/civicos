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

## Stateless tokens

Access tokens, refresh tokens, and authorization codes are all HMAC-signed
self-contained strings. Any container serving the MCP server can verify
them without shared state. This is required because Modal spins up
multiple containers: if we stored tokens in a per-container dict, a token
issued by container A would be unknown to container B, and MCP tool calls
would fail with 'open tier' errors even for OAuth-authenticated clients.

The signing secret is derived from DATABASE_URL (stable across all
containers of the same deployment) unless CIVICOS_OAUTH_SECRET is set
explicitly. If neither is available, we fall back to a random per-container
secret and log a warning (tokens won't work across restarts — local dev).
"""

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import time

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

logger = logging.getLogger("civicos-mcp.oauth")

# ─────────── TTLs ───────────

TOKEN_TTL = 7 * 24 * 3600  # 7 days
REFRESH_TTL = 30 * 24 * 3600  # 30 days
CODE_TTL = 300  # 5 minutes

# ─────────── Client registration store (in-memory, cosmetic only) ───────────
# Used to show the client_name on the consent page. Non-security-critical:
# the auth code signature encodes the client_id and redirect_uri, so the
# OAuth flow works even if the container doesn't have the registration.

_clients: dict[str, dict] = {}

# Lazy-initialized signing secret (see _get_signing_secret)
_signing_secret_cache: bytes | None = None


# ─────────── Signing secret ───────────

def _get_signing_secret() -> bytes:
    """Get the HMAC signing secret for OAuth tokens.

    Priority:
    1. CIVICOS_OAUTH_SECRET env var (explicit override)
    2. Derived from DATABASE_URL (stable across all containers of a deployment)
    3. Random per-container (WARNING: tokens won't work across containers or restarts)
    """
    global _signing_secret_cache
    if _signing_secret_cache is not None:
        return _signing_secret_cache

    explicit = os.getenv("CIVICOS_OAUTH_SECRET")
    if explicit:
        _signing_secret_cache = hashlib.sha256(explicit.encode()).digest()
        return _signing_secret_cache

    db_url = os.getenv("DATABASE_URL", "")
    if db_url:
        # Derive a stable 32-byte key from DATABASE_URL.
        # Fixed salt namespaces the derivation so the DB URL itself is not
        # the key material directly.
        _signing_secret_cache = hashlib.sha256(
            b"civicos-oauth-v1:" + db_url.encode()
        ).digest()
        return _signing_secret_cache

    logger.warning(
        "No CIVICOS_OAUTH_SECRET or DATABASE_URL available — using random "
        "signing key. OAuth tokens won't survive container restarts."
    )
    _signing_secret_cache = secrets.token_bytes(32)
    return _signing_secret_cache


# ─────────── Base64url helpers ───────────

def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64decode(s: str) -> bytes:
    # Add padding back for decode
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


# ─────────── Signed-token primitives ───────────

def _sign_payload(payload: dict) -> str:
    """Create a signed token string: <b64(payload_json)>.<b64(hmac_sig)>"""
    payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    payload_b64 = _b64encode(payload_bytes)
    sig = hmac.new(
        _get_signing_secret(), payload_b64.encode(), hashlib.sha256
    ).digest()
    return f"{payload_b64}.{_b64encode(sig)}"


def _verify_signed(token_body: str) -> dict | None:
    """Verify a signed token string and return the payload dict, or None.

    Does NOT check expiry — callers should check the 'exp' field themselves.
    """
    try:
        payload_b64, sig_b64 = token_body.split(".", 1)
    except ValueError:
        return None

    expected_sig = hmac.new(
        _get_signing_secret(), payload_b64.encode(), hashlib.sha256
    ).digest()
    try:
        provided_sig = _b64decode(sig_b64)
    except (ValueError, Exception):
        return None

    if not hmac.compare_digest(expected_sig, provided_sig):
        return None

    try:
        return json.loads(_b64decode(payload_b64))
    except (ValueError, json.JSONDecodeError):
        return None


# ─────────── Public: token verification (called by BearerAuthMiddleware) ───────────

def verify_oauth_token(token: str) -> dict | None:
    """Verify an OAuth access token. Returns token info dict or None.

    Token format: cos_<payload_b64>.<sig_b64>
    Payload: {"sub": client_id, "typ": "at", "iat": ..., "exp": ..., "scope": "mcp"}
    """
    if not token.startswith("cos_"):
        return None
    payload = _verify_signed(token[4:])
    if payload is None:
        return None
    if payload.get("typ") != "at":
        return None
    if time.time() > payload.get("exp", 0):
        return None
    return {
        "client_id": payload.get("sub"),
        "issued_at": payload.get("iat"),
        "expires_at": payload.get("exp"),
    }


def _verify_refresh_token(token: str) -> dict | None:
    """Verify a refresh token. Returns payload dict or None."""
    if not token.startswith("cosr_"):
        return None
    payload = _verify_signed(token[5:])
    if payload is None:
        return None
    if payload.get("typ") != "rt":
        return None
    if time.time() > payload.get("exp", 0):
        return None
    return payload


def _verify_auth_code(code: str) -> dict | None:
    """Verify a signed authorization code. Returns payload dict or None."""
    if not code.startswith("cosc_"):
        return None
    payload = _verify_signed(code[5:])
    if payload is None:
        return None
    if payload.get("typ") != "ac":
        return None
    if time.time() > payload.get("exp", 0):
        return None
    return payload


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
    """Issue a new stateless access token and refresh token."""
    now = int(time.time())

    access_payload = {
        "sub": client_id,
        "typ": "at",
        "iat": now,
        "exp": now + TOKEN_TTL,
        "scope": "mcp",
    }
    refresh_payload = {
        "sub": client_id,
        "typ": "rt",
        "iat": now,
        "exp": now + REFRESH_TTL,
        "scope": "mcp",
    }

    return {
        "access_token": f"cos_{_sign_payload(access_payload)}",
        "token_type": "bearer",
        "expires_in": TOKEN_TTL,
        "refresh_token": f"cosr_{_sign_payload(refresh_payload)}",
        "scope": "mcp",
    }


def _issue_auth_code(
    client_id: str,
    redirect_uri: str,
    code_challenge: str,
    code_challenge_method: str,
) -> str:
    """Issue a stateless authorization code.

    The code is signed and encodes everything needed for exchange:
    client_id, redirect_uri, PKCE challenge + method, expiry. A nonce is
    added so the same (client_id, challenge) pair generates different
    codes each time.

    Note on single-use: stateless codes cannot be marked as "consumed"
    without shared storage. We rely on the short TTL (5 minutes), HTTPS
    transport, and PKCE verifier binding to mitigate replay risk. The
    OAuth client (Claude.ai) exchanges codes within seconds of issue.
    """
    now = int(time.time())
    payload = {
        "sub": client_id,
        "typ": "ac",
        "iat": now,
        "exp": now + CODE_TTL,
        "ru": redirect_uri,
        "cc": code_challenge,
        "ccm": code_challenge_method,
        "nonce": secrets.token_urlsafe(8),
    }
    return f"cosc_{_sign_payload(payload)}"


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
        # Cached locally for cosmetic consent-page lookup only.
        # The OAuth flow doesn't depend on this; auth codes and tokens are
        # stateless and don't need the registration to verify.
        _clients[client_id] = registration
        logger.info(
            "OAuth client registered: %s (%s)",
            client_id, registration["client_name"],
        )
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

        if not client_id or not code_challenge:
            return JSONResponse(
                {"error": "invalid_request",
                 "error_description": "client_id and code_challenge required"},
                status_code=400,
            )

        # If the client was registered on this container, validate its
        # redirect_uri allow-list. If not registered (multi-container or
        # cold start), skip — we cannot distinguish "unregistered" from
        # "registered on another container" without shared storage. The
        # PKCE verifier still protects code exchange.
        client = _clients.get(client_id)
        if client and redirect_uri not in client.get("redirect_uris", []):
            return JSONResponse(
                {"error": "invalid_request",
                 "error_description": "redirect_uri mismatch"},
                status_code=400,
            )

        code = _issue_auth_code(
            client_id=client_id,
            redirect_uri=redirect_uri,
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method,
        )

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

            payload = _verify_auth_code(code)
            if payload is None:
                return JSONResponse({"error": "invalid_grant"}, status_code=400)

            # Validate client_id matches the one the code was issued for
            if payload.get("sub") != client_id:
                return JSONResponse({"error": "invalid_grant"}, status_code=400)

            # Verify PKCE
            challenge = payload.get("cc", "")
            method = payload.get("ccm", "S256")
            if challenge and not _verify_pkce(code_verifier, challenge, method):
                return JSONResponse({"error": "invalid_grant"}, status_code=400)

            logger.info("OAuth token issued for client %s", client_id)
            return JSONResponse(_issue_tokens(client_id))

        if grant_type == "refresh_token":
            refresh = str(form.get("refresh_token", ""))
            payload = _verify_refresh_token(refresh)
            if payload is None:
                return JSONResponse({"error": "invalid_grant"}, status_code=400)

            client_id = payload.get("sub", "")
            logger.info("OAuth token refreshed for client %s", client_id)
            return JSONResponse(_issue_tokens(client_id))

        return JSONResponse({"error": "unsupported_grant_type"}, status_code=400)

    return router
