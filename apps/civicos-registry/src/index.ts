import { withCors, handleOptions } from "./cors";
import { handleServers, handleServerById, handleHealth } from "./api";
import { renderLandingPage } from "./html";

export default {
  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    const path = url.pathname;

    if (request.method === "OPTIONS") {
      return handleOptions();
    }

    if (request.method !== "GET") {
      return withCors(
        new Response(JSON.stringify({ error: "Method not allowed" }), {
          status: 405,
          headers: { "Content-Type": "application/json" },
        })
      );
    }

    // HTML landing page
    if (path === "/" || path === "") {
      return withCors(await renderLandingPage());
    }

    // JSON API
    if (path === "/api/v1/servers") {
      return withCors(await handleServers());
    }

    if (path.startsWith("/api/v1/servers/")) {
      const id = path.slice("/api/v1/servers/".length);
      if (id) {
        return withCors(await handleServerById(id));
      }
    }

    if (path === "/api/v1/health") {
      return withCors(await handleHealth());
    }

    return withCors(
      new Response(JSON.stringify({ error: "Not found" }), {
        status: 404,
        headers: { "Content-Type": "application/json" },
      })
    );
  },
};
