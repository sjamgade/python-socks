import ssl

import pytest
from unittest.mock import patch
from yarl import URL

from python_socks import ProxyType, ProxyError, ProxyTimeoutError, ProxyConnectionError


from tests.config import (
    PROXY_HOST_IPV4,
    SOCKS5_PROXY_PORT,
    LOGIN,
    PASSWORD,
    SKIP_IPV6_TESTS,
    SOCKS5_IPV4_URL,
    SOCKS5_IPV4_URL_WO_AUTH,
    SOCKS5_IPV6_URL,
    SOCKS4_URL,
    HTTP_PROXY_URL,
    TEST_URL_IPV4,
    SOCKS5_IPV4_HOSTNAME_URL,
    TEST_HOST_PEM_FILE,
    TEST_URL_IPV4_HTTPS,
    PROXY_HOST_PEM_FILE,
    HTTPS_PROXY_URL,
)

from tests.mocks import getaddrinfo_async_mock

trio = pytest.importorskip('trio')

from python_socks.async_.trio._resolver import Resolver  # noqa: E402
from python_socks.async_.trio.v2 import Proxy  # noqa: E402
from python_socks.async_.trio.v2 import ProxyChain  # noqa: E402
from python_socks.async_.trio.v2._proxy import TrioProxy  # noqa: E402


async def make_request(
    proxy: TrioProxy,
    url: str,
    resolve_host=False,
    timeout=None,
):
    with patch(
        'trio._highlevel_open_tcp_stream.getaddrinfo',
        new=getaddrinfo_async_mock(trio.socket.getaddrinfo),
    ):
        url = URL(url)

        dest_host = url.host
        if resolve_host:
            resolver = Resolver()
            _, dest_host = await resolver.resolve(url.host)

        ssl_context = None
        if url.scheme == 'https':
            ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS)
            ssl_context.verify_mode = ssl.CERT_REQUIRED
            ssl_context.load_verify_locations(TEST_HOST_PEM_FILE)

        stream = await proxy.connect(
            dest_host=dest_host,
            dest_port=url.port,
            dest_ssl=ssl_context,
            timeout=timeout,
        )

        # fmt: off
        request = (
            'GET {rel_url} HTTP/1.1\r\n'
            'Host: {host}\r\n'
            'Connection: close\r\n\r\n'
        )
        # fmt: on

        request = request.format(rel_url=url.path_qs, host=url.host)
        request = request.encode('ascii')

        await stream.write_all(request)

        response = await stream.read(1024)

        status_line = response.split(b'\r\n', 1)[0]
        version, status_code, *reason = status_line.split()

        await stream.close()

        return int(status_code)


@pytest.mark.parametrize('url', (TEST_URL_IPV4, TEST_URL_IPV4_HTTPS))
@pytest.mark.parametrize('rdns', (True, False))
@pytest.mark.parametrize('resolve_host', (True, False))
@pytest.mark.trio
async def test_socks5_proxy_ipv4(url, rdns, resolve_host):
    proxy = Proxy.from_url(SOCKS5_IPV4_URL, rdns=rdns)
    status_code = await make_request(proxy=proxy, url=url, resolve_host=resolve_host)
    assert status_code == 200


@pytest.mark.parametrize('url', (TEST_URL_IPV4, TEST_URL_IPV4_HTTPS))
@pytest.mark.trio
async def test_socks5_proxy_hostname_ipv4(url):
    proxy = Proxy.from_url(SOCKS5_IPV4_HOSTNAME_URL)
    status_code = await make_request(proxy=proxy, url=url)
    assert status_code == 200


@pytest.mark.parametrize('url', (TEST_URL_IPV4, TEST_URL_IPV4_HTTPS))
@pytest.mark.parametrize('rdns', (None, True, False))
@pytest.mark.trio
async def test_socks5_proxy_ipv4_with_auth_none(url, rdns):
    proxy = Proxy.from_url(SOCKS5_IPV4_URL_WO_AUTH, rdns=rdns)
    status_code = await make_request(proxy=proxy, url=url)
    assert status_code == 200


@pytest.mark.trio
async def test_socks5_proxy_with_invalid_credentials():
    proxy = Proxy.create(
        proxy_type=ProxyType.SOCKS5,
        host=PROXY_HOST_IPV4,
        port=SOCKS5_PROXY_PORT,
        username=LOGIN,
        password=PASSWORD + 'aaa',
    )
    with pytest.raises(ProxyError):
        await make_request(proxy=proxy, url=TEST_URL_IPV4)


@pytest.mark.trio
async def test_socks5_proxy_with_connect_timeout():
    proxy = Proxy.create(
        proxy_type=ProxyType.SOCKS5,
        host=PROXY_HOST_IPV4,
        port=SOCKS5_PROXY_PORT,
        username=LOGIN,
        password=PASSWORD,
    )
    with pytest.raises(ProxyTimeoutError):
        await make_request(proxy=proxy, url=TEST_URL_IPV4, timeout=0.0001)


@pytest.mark.trio
async def test_socks5_proxy_with_invalid_proxy_port(unused_tcp_port):
    proxy = Proxy.create(
        proxy_type=ProxyType.SOCKS5,
        host=PROXY_HOST_IPV4,
        port=unused_tcp_port,
        username=LOGIN,
        password=PASSWORD,
    )
    with pytest.raises(ProxyConnectionError):
        await make_request(proxy=proxy, url=TEST_URL_IPV4)


@pytest.mark.parametrize('url', (TEST_URL_IPV4, TEST_URL_IPV4_HTTPS))
@pytest.mark.skipif(SKIP_IPV6_TESTS, reason="TravisCI doesn't support ipv6")
@pytest.mark.trio
async def test_socks5_proxy_ipv6(url):
    proxy = Proxy.from_url(SOCKS5_IPV6_URL)
    status_code = await make_request(proxy=proxy, url=url)
    assert status_code == 200


@pytest.mark.parametrize('url', (TEST_URL_IPV4, TEST_URL_IPV4_HTTPS))
@pytest.mark.parametrize('rdns', (None, True, False))
@pytest.mark.parametrize('resolve_host', (True, False))
@pytest.mark.trio
async def test_socks4_proxy(url, rdns, resolve_host):
    proxy = Proxy.from_url(SOCKS4_URL, rdns=rdns)
    status_code = await make_request(proxy=proxy, url=url, resolve_host=resolve_host)
    assert status_code == 200


@pytest.mark.parametrize('url', (TEST_URL_IPV4, TEST_URL_IPV4_HTTPS))
@pytest.mark.trio
async def test_http_proxy(url):
    proxy = Proxy.from_url(HTTP_PROXY_URL)
    status_code = await make_request(proxy=proxy, url=url)
    assert status_code == 200


@pytest.mark.parametrize('url', (TEST_URL_IPV4, TEST_URL_IPV4_HTTPS))
@pytest.mark.trio
async def test_secure_proxy(url):
    proxy_ssl = ssl.SSLContext(ssl.PROTOCOL_TLS)
    proxy_ssl.verify_mode = ssl.CERT_REQUIRED
    proxy_ssl.load_verify_locations(PROXY_HOST_PEM_FILE)

    proxy = Proxy.from_url(HTTPS_PROXY_URL, proxy_ssl=proxy_ssl)
    status_code = await make_request(proxy=proxy, url=url)
    assert status_code == 200


@pytest.mark.parametrize('url', (TEST_URL_IPV4, TEST_URL_IPV4_HTTPS))
@pytest.mark.trio
async def test_proxy_chain(url):
    proxy = ProxyChain(
        [
            Proxy.from_url(SOCKS5_IPV4_URL),
            Proxy.from_url(SOCKS4_URL),
            Proxy.from_url(HTTP_PROXY_URL),
        ]
    )
    # noinspection PyTypeChecker
    status_code = await make_request(proxy=proxy, url=url)
    assert status_code == 200
