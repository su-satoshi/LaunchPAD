import pytest

from agent.utils import host_matches, is_public_url, one_line, parse_llm_json, safe_http_url


@pytest.mark.parametrize("url,ok", [
    ("https://seek.com.au/job/1", True),
    ("http://example.com", True),
    ("javascript:alert(1)", False),
    ("data:text/html,hi", False),
    ("file:///etc/passwd", False),
    ("https://", False),
    ("https://a.com/\r\nx", False),
    (None, False),
])
def test_safe_http_url(url, ok):
    assert bool(safe_http_url(url)) is ok


def test_host_matches_is_not_substring_based():
    assert host_matches("https://www.seek.com.au/login", ["seek.com.au"])
    assert host_matches("https://seek.com.au/", ["seek.com.au"])
    assert not host_matches("https://evil.example/seek.com.au/login", ["seek.com.au"])
    assert not host_matches("https://seek.com.au.evil.example/", ["seek.com.au"])
    assert not host_matches("https://notseek.com.au/", ["seek.com.au"])


@pytest.mark.asyncio
@pytest.mark.parametrize("url", [
    "http://localhost:8000/api", "http://127.0.0.1/", "http://10.0.0.5/", "http://192.168.1.1/",
    "http://169.254.169.254/latest/meta-data", "http://[::1]/", "http://foo.local/", "ftp://example.com",
])
async def test_is_public_url_blocks_internal(url):
    assert await is_public_url(url) is False


@pytest.mark.asyncio
async def test_is_public_url_allows_public_ip_literal():
    assert await is_public_url("https://8.8.8.8/") is True


def test_one_line_strips_header_injection():
    assert one_line("Hi\r\nBcc: victim@x.com") == "Hi Bcc: victim@x.com"


def test_parse_llm_json_variants():
    assert parse_llm_json('```json\n[1, 2]\n```') == [1, 2]
    assert parse_llm_json('Sure! Here it is: {"a": 1} hope that helps') == {"a": 1}
    with pytest.raises(ValueError):
        parse_llm_json("no json here")
