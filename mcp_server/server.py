"""MCPServer (official SDK v2) in stateless streamable-HTTP mode. Each tool
handler delegates to the synchronous authorization unit through
`sync_to_async`, so Django ORM work runs in one thread per call."""

from __future__ import annotations

from asgiref.sync import sync_to_async
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.transport_security import TransportSecuritySettings

from .auth import authorize_and_run
from .tools import get_document, search_knowledge

INSTRUCTIONS = (
    "Read-only tools over an organization's documents. Every call is authorized by the capability "
    "token of the running investigation; results are limited to what the requesting user may see."
)


def build_server() -> MCPServer:
    server = MCPServer(name="knowledge", instructions=INSTRUCTIONS)

    @server.tool(
        name="search_knowledge",
        description="Hybrid search over authorized documents. Returns passages with evidence ids, titles, source URLs and locators.",
    )
    async def _search_knowledge(
        query: str, ctx: Context, source_types: list[str] | None = None, limit: int = 10
    ) -> dict:
        args = {"query": query, "source_types": source_types or [], "limit": limit}
        return await sync_to_async(authorize_and_run, thread_sensitive=True)(
            ctx.headers, "search_knowledge", args, search_knowledge
        )

    @server.tool(
        name="get_document",
        description="Bounded excerpt of one authorized document (8,000 characters per call), its sections, version and evidence ids.",
    )
    async def _get_document(document_id: str, ctx: Context, section: int | None = None) -> dict:
        args = {"document_id": document_id, "section": section}
        return await sync_to_async(authorize_and_run, thread_sensitive=True)(
            ctx.headers, "get_document", args, get_document
        )

    _register_sprint3_tools(server)
    return server


def _register_sprint3_tools(server: MCPServer) -> None:
    try:
        from decisions.api import register_mcp_tools
    except ImportError:
        return
    register_mcp_tools(server, authorize_and_run)


def build_app(host: str = "0.0.0.0"):
    """Starlette app with the MCP endpoint at /mcp and a liveness route at /healthz."""
    from starlette.responses import JSONResponse
    from starlette.routing import Route

    server = build_server()
    security = TransportSecuritySettings(enable_dns_rebinding_protection=False)
    app = server.streamable_http_app(
        json_response=True, stateless_http=True, transport_security=security, host=host
    )
    app.router.routes.insert(
        0, Route("/healthz", lambda request: JSONResponse({"status": "ok"}), methods=["GET"])
    )
    return app
