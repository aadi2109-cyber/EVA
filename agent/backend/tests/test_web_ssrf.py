"""SSRF: DNS-resolution checks on every hop and connection pinning for web.fetch."""

from __future__ import annotations

import socket

import httpx
import pytest

from app.tools import web
from app.tools.base import ToolContext
from app.tools.web import UrlNotAllowed, WebFetchTool, resolve_public_ips, set_resolver, set_web_transport
from env.mock.state import state as mock_state

pytestmark = pytest.mark.asyncio
CTX = ToolContext(task_id="t", user_id="u", call_id="c")
OK = httpx.Response(200, headers={"content-type": "text/plain"}, text="hello")


def fake_dns(table: dict[str, list[str]]):
    async def resolve(host):
        if host not in table:
            raise socket.gaierror(f"no such host {host}")
        return table[host]

    return resolve


@pytest.fixture(autouse=True)
def _clean():
    mock_state.reset()
    yield
    set_resolver(None)
    set_web_transport(None)
    mock_state.reset()


class Net:
    def __init__(self, handler=lambda r: OK):
        self.seen: list[httpx.Request] = []

        def h(req):
            self.seen.append(req)
            return handler(req)

        set_web_transport(httpx.MockTransport(h))


@pytest.mark.parametrize("addr", [
    "127.0.0.1", "10.1.2.3", "172.16.0.9", "192.168.1.5", "169.254.169.254", "100.64.0.1",
    "0.0.0.0", "::1", "fe80::1", "fc00::1", "::ffff:127.0.0.1", "::ffff:169.254.169.254", "224.0.0.1",
])
async def test_private_resolution_blocked_and_no_request_made(addr):
    set_resolver(fake_dns({"evil.test": [addr]}))
    net = Net()
    with pytest.raises(UrlNotAllowed, match="non-public"):
        await WebFetchTool().run({"url": "https://evil.test/x"}, CTX)
    assert net.seen == [], "no socket may be opened for a non-public resolution"
    assert mock_state.blocked_http_requests


async def test_any_private_address_in_a_multi_answer_blocks():
    set_resolver(fake_dns({"mixed.test": ["93.184.216.34", "10.0.0.8"]}))
    Net()
    with pytest.raises(UrlNotAllowed):
        await WebFetchTool().run({"url": "https://mixed.test/"}, CTX)


async def test_unresolvable_host_blocked():
    set_resolver(fake_dns({}))
    net = Net()
    with pytest.raises(UrlNotAllowed, match="could not be resolved"):
        await WebFetchTool().run({"url": "https://nxdomain.test/"}, CTX)
    assert net.seen == []


async def test_public_host_is_pinned_to_checked_ip_with_host_and_sni_preserved():
    set_resolver(fake_dns({"docs.pub.test": ["93.184.216.34", "93.184.216.35"]}))
    net = Net()
    res = await WebFetchTool().run({"url": "https://docs.pub.test/a?q=1"}, CTX)
    assert res.scan_fields[0].text == "hello"
    req = net.seen[0]
    assert req.url.host == "93.184.216.34" and req.url.path == "/a" and req.url.query == b"q=1"
    assert req.headers["host"] == "docs.pub.test"
    assert req.extensions["sni_hostname"] == "docs.pub.test"


async def test_dns_rebinding_between_hops_is_caught():
    answers = {"first.test": ["93.184.216.34"], "second.test": ["93.184.216.40"]}
    set_resolver(fake_dns(answers))

    def handler(req):
        if req.headers["host"] == "first.test":
            answers["second.test"] = ["127.0.0.1"]  # attacker flips DNS before the next hop resolves
            return httpx.Response(302, headers={"Location": "https://second.test/admin"})
        return OK

    net = Net(handler)
    with pytest.raises(UrlNotAllowed):
        await WebFetchTool().run({"url": "https://first.test/"}, CTX)
    assert len(net.seen) == 1, "second hop never reaches the network"


async def test_redirect_to_name_resolving_private_is_blocked():
    set_resolver(fake_dns({"ok.test": ["93.184.216.34"], "internal.test": ["192.168.0.10"]}))
    net = Net(lambda r: httpx.Response(302, headers={"Location": "http://internal.test/secret"}))
    with pytest.raises(UrlNotAllowed):
        await WebFetchTool().run({"url": "https://ok.test/"}, CTX)
    assert [r.headers["host"] for r in net.seen] == ["ok.test"]


@pytest.mark.parametrize("host", ["2130706433", "0x7f.1", "017700000001", "127.1"])
async def test_numeric_ip_obfuscation_resolves_to_loopback_and_is_blocked(host):
    """The OS resolver normalises these to 127.0.0.1; the check runs on the resolved address."""
    try:
        resolved = [i[4][0] for i in socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)]
    except OSError:
        pytest.skip("platform resolver rejects this numeric form (also blocked: unresolvable)")
    assert resolved == ["127.0.0.1"]
    net = Net()
    with pytest.raises(UrlNotAllowed):
        await WebFetchTool().run({"url": f"http://{host}/"}, CTX)
    assert net.seen == []


async def test_resolve_public_ips_helper():
    set_resolver(fake_dns({"a.test": ["93.184.216.34"], "b.test": []}))
    assert await resolve_public_ips("a.test") == ["93.184.216.34"]
    with pytest.raises(UrlNotAllowed, match="did not resolve"):
        await resolve_public_ips("b.test")
    assert web._ip_is_public("2606:4700:4700::1111") and not web._ip_is_public("garbage")
