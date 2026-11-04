import httpx

from haytile import web_gateway


def test_web_gateway_streams_html_query_and_multiple_cookies(client, monkeypatch):
    original = httpx.AsyncClient
    seen = []

    class Chunks(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b"<html>private "
            yield b"web shell</html>"

    def handler(request):
        seen.append(request)
        return httpx.Response(
            200,
            stream=Chunks(),
            headers=[
                ("content-type", "text/html"),
                ("set-cookie", "one=1; Path=/"),
                ("set-cookie", "two=2; Path=/"),
            ],
        )

    monkeypatch.setenv("HAYTILE_WEB_UPSTREAM", "http://127.0.0.1:3010")
    monkeypatch.setattr(
        web_gateway.httpx,
        "AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )
    response = client.get("/?language=ht", headers={"cookie": "private=session"})
    assert response.status_code == 200 and "private web shell" in response.text
    assert len(response.headers.get_list("set-cookie")) == 2
    assert str(seen[0].url) == "http://127.0.0.1:3010/?language=ht"
    assert seen[0].headers["cookie"] == "private=session"
    assert client.get("/v1/not-a-route").status_code == 404
    assert len(seen) == 1


def test_web_gateway_is_disabled_without_internal_upstream(client, monkeypatch):
    monkeypatch.delenv("HAYTILE_WEB_UPSTREAM", raising=False)
    assert client.get("/not-an-api-route").status_code == 404
    assert client.get("/v1/health").status_code == 200


def test_old_render_html_redirects_to_canonical_without_redirecting_api(client, monkeypatch):
    monkeypatch.setenv("HAYTILE_PUBLIC_ORIGIN", "https://ai.haytiles.com")
    response = client.get(
        "https://haytile-ai.onrender.com/?billing=success&purchase=owned", follow_redirects=False
    )
    assert response.status_code == 307
    assert response.headers["location"] == "https://ai.haytiles.com/?billing=success&purchase=owned"
    assert (
        client.get("https://haytile-ai.onrender.com/v1/health", follow_redirects=False).status_code
        == 200
    )
    assert (
        client.get(
            "https://haytile-ai.onrender.com/api/v1/not-found", follow_redirects=False
        ).status_code
        != 307
    )
    assert (
        client.post(
            "https://haytile-ai.onrender.com/api/v1/billing/webhook", follow_redirects=False
        ).status_code
        != 307
    )
    assert client.get("https://ai.haytiles.com/", follow_redirects=False).status_code != 307
