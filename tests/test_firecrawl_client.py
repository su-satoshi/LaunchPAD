import httpx
import pytest
import respx

from agent.tools import firecrawl_client as fc


@pytest.mark.asyncio
@respx.mock
async def test_search_parses_v2_and_falls_back_on_400():
    route = respx.post(f"{fc.FIRECRAWL_URL}/v2/search")
    route.side_effect = [
        httpx.Response(400, json={"error": "bad"}),
        httpx.Response(200, json={"success": True, "data": {"web": [
            {"url": "https://seek.com.au/job/1", "title": "SOC", "markdown": "# SOC"}]}}),
    ]
    res = await fc.search("soc analyst", include_domains=["seek.com.au"])
    assert res == [{"url": "https://seek.com.au/job/1", "title": "SOC", "description": "", "markdown": "# SOC"}]
    assert "site:seek.com.au" in route.calls[1].request.content.decode()


@pytest.mark.asyncio
@respx.mock
async def test_search_returns_empty_when_down():
    respx.post(f"{fc.FIRECRAWL_URL}/v2/search").mock(side_effect=httpx.ConnectError("down"))
    assert await fc.search("x") == []
