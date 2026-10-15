from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Serve the knowledge MCP server (stateless streamable HTTP) with uvicorn."

    def add_arguments(self, parser):
        parser.add_argument("--host", default="127.0.0.1")
        parser.add_argument("--port", type=int, default=8710)

    def handle(self, *args, **options):
        import uvicorn

        from mcp_server.server import build_app

        uvicorn.run(
            build_app(host=options["host"]),
            host=options["host"],
            port=options["port"],
            log_level="info",
        )
