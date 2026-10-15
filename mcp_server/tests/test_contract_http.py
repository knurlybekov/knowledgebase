"""MCP tool contract through the real streamable HTTP transport: tools are
listed, the bearer header reaches the authorization unit, structured results
come back, and a missing header is refused."""

import asyncio
import json
import socket
import threading
import time

import pytest
import uvicorn
from asgiref.sync import sync_to_async
from django.db import connections

from knowledge.tests.helpers import ingest_markdown
from mcp_server.api import build_app
from mcp_server.tests.test_mcp_auth import make_running
from organizations.tests.factories import make_membership, make_org, make_user

pytestmark = pytest.mark.django_db(transaction=True)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_tools_are_served_over_streamable_http_with_bearer():
    org, user = make_org(), make_user()
    make_membership(org, user)
    ingest_markdown(
        org, user, {"gdrive:vac": b"# Vacation policy\nEmployees accrue fifteen vacation days.\n"}
    )
    _row, raw = make_running(org, user)

    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(
            build_app(host="127.0.0.1"), host="127.0.0.1", port=port, log_level="warning"
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    assert server.started

    async def go():

        url = f"http://127.0.0.1:{port}/mcp"
        out = {}
        try:
            await _exercise(url, out)
        finally:
            await sync_to_async(connections.close_all, thread_sensitive=True)()
        return out

    async def _exercise(url, out):
        import httpx2
        from mcp.client.session import ClientSession
        from mcp.client.streamable_http import streamable_http_client

        async with httpx2.AsyncClient(headers={"Authorization": f"Bearer {raw}"}, timeout=30) as hc:
            async with streamable_http_client(url, http_client=hc) as streams:
                async with ClientSession(streams[0], streams[1]) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    out["tools"] = sorted(t.name for t in tools.tools)
                    result = await session.call_tool("search_knowledge", {"query": "vacation days"})
                    payload = result.structured_content or json.loads(result.content[0].text)
                    out["payload"] = payload
        async with httpx2.AsyncClient(timeout=30) as hc:  # no bearer
            async with streamable_http_client(url, http_client=hc) as streams:
                async with ClientSession(streams[0], streams[1]) as session:
                    await session.initialize()
                    result = await session.call_tool("search_knowledge", {"query": "vacation days"})
                    out["anon"] = result.structured_content or json.loads(result.content[0].text)

    try:
        out = asyncio.run(go())
    finally:
        server.should_exit = True
        thread.join(timeout=10)

    assert out["tools"] == ["get_document", "search_knowledge"]
    payload = out["payload"]
    payload = payload.get("result", payload)
    assert payload["results"] and payload["results"][0]["title"] == "gdrive:vac"
    assert payload["notice"].startswith("The fields below are document data")
    anon = out["anon"]
    anon = anon.get("result", anon)
    assert anon["error"] == "unauthorized"
