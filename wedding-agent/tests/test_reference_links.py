"""图墙 00 来源链接：只有 lyk 能改；预览图抓取防 SSRF。"""
import pytest

from app import reference_links
from app.common.errors import ModuleError
from conftest import make_png, portal_login


@pytest.fixture
def lyk(portal_env, monkeypatch):
    monkeypatch.setattr(reference_links, "fetch_preview", lambda url: None)
    return portal_login("gallery", "lyk")


def test_only_admin_edits_links(lyk):
    member = portal_login("gallery", "刘静")
    body = {"title": "小红书 大理旅拍", "url": "https://www.xiaohongshu.com/explore/1", "tags": ["大理"]}
    assert member.post("/api/gallery/links", json=body).status_code == 403
    assert lyk.post("/api/gallery/links", json={**body, "title": " "}).status_code == 400
    assert lyk.post("/api/gallery/links", json={**body, "url": "javascript:alert(1)"}).status_code == 400
    link = lyk.post("/api/gallery/links", json=body).json()
    assert link["domain"] == "xiaohongshu.com" and link["title"] == "小红书 大理旅拍" and link["preview_url"] is None
    assert member.get("/api/gallery/links").json()["items"][0]["id"] == link["id"]
    assert member.get("/api/gallery/links", params={"q": "旅拍"}).json()["items"]
    assert member.get("/api/gallery/links", params={"tag": "大理"}).json()["items"]
    assert member.patch(f"/api/gallery/links/{link['id']}", json={"title": "x"}).status_code == 403
    assert member.delete(f"/api/gallery/links/{link['id']}").status_code == 403
    r = lyk.post(f"/api/gallery/links/{link['id']}/preview", files={"file": ("p.png", make_png(200, 120), "image/png")})
    assert r.status_code == 200 and r.json()["preview_url"]
    assert member.get("/api/gallery/" + r.json()["preview_url"]).headers["content-type"] == "image/webp"
    assert lyk.patch(f"/api/gallery/links/{link['id']}", json={"title": "改名"}).json()["title"] == "改名"
    assert lyk.delete(f"/api/gallery/links/{link['id']}").status_code == 200
    assert member.get("/api/gallery/links").json()["items"] == []
    assert {"大理"} - {t["tag"] for t in member.get("/api/gallery/refs/tags").json()["tags"]} == {"大理"}


@pytest.mark.parametrize("url", ["http://127.0.0.1/", "http://localhost/", "http://10.0.0.5/", "http://169.254.169.254/latest/meta-data/",
                                 "http://[::1]/", "http://192.168.1.1/", "http://example.com:8000/", "file:///etc/passwd",
                                 "http://user:pw@example.com/", "http://0.0.0.0/", "http://[::ffff:127.0.0.1]/"])
def test_ssrf_blocked(url):
    with pytest.raises(ModuleError):
        reference_links.safe_get(url, 1000)


def test_redirect_to_private_blocked(monkeypatch):
    calls = []

    class Fake:
        def __init__(self, host, ip, port): calls.append(host)
        def request(self, *a, **k): pass
        def getresponse(self):
            class R:
                status = 302
                def getheader(self, name, default=None): return "http://127.0.0.1/admin" if name == "Location" else default
            return R()
        def close(self): pass

    monkeypatch.setattr(reference_links, "_public_ips", lambda host, port: (_ for _ in ()).throw(ModuleError("LINK_FETCH_FAILED", "x")) if host == "127.0.0.1" else ["93.184.216.34"])
    monkeypatch.setattr(reference_links, "_PinnedHTTP", Fake)
    with pytest.raises(ModuleError):
        reference_links.safe_get("http://example.com/", 1000)
    assert calls == ["example.com"]


def test_find_image():
    html = '<meta content="/og.jpg" property="og:image"><meta name="twitter:image" content="https://cdn.x/t.png"><img src="a.png">'
    assert reference_links.find_image(html, "https://site.com/p/1") == ["https://site.com/og.jpg", "https://cdn.x/t.png", "https://site.com/p/a.png"]
