"""
serve.py takes its port from whichever web server started it.

    python -m pytest tests -q
"""


def test_port_comes_from_the_web_server(monkeypatch):
    import serve
    for name in ("KTS_PORT", "HTTP_PLATFORM_PORT", "ASPNETCORE_PORT", "PORT"):
        monkeypatch.delenv(name, raising=False)
    assert serve.port() == 8905
    # IIS with the ASP.NET Core Module
    monkeypatch.setenv("ASPNETCORE_PORT", "23456")
    assert serve.port() == 23456
    # IIS with the HttpPlatformHandler
    monkeypatch.setenv("HTTP_PLATFORM_PORT", "34567")
    assert serve.port() == 34567
    # a placeholder of web.config that the web server did not fill in is not a port
    monkeypatch.setenv("KTS_PORT", "%HTTP_PLATFORM_PORT%")
    assert serve.port() == 34567
    # an explicit port wins
    monkeypatch.setenv("KTS_PORT", "9000")
    assert serve.port() == 9000
