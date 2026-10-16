"""参考图墙：鉴权、上传转码去 EXIF、容量上限、筛选、编辑删除、打包、导出。"""
import io
import zipfile

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import reference_wall
from app.api import app
from app.common.config import settings


def jpeg_with_exif(size=(3000, 1500)) -> bytes:
    exif = Image.Exif()
    exif[0x010F] = "SecretCam"  # Make
    out = io.BytesIO()
    Image.new("RGB", size, (200, 120, 110)).save(out, "JPEG", exif=exif.tobytes())
    return out.getvalue()


@pytest.fixture
def client(gallery_client):
    return gallery_client


def api(rel: str) -> str:
    return "/api/gallery/" + rel


def upload(c, verdict="good", style="02", n=1, **extra):
    files = [("files", (f"p{i}.jpg", jpeg_with_exif(), "image/jpeg")) for i in range(n)]
    return c.post("/api/gallery/refs", files=files, data={"style": style, "verdict": verdict, **extra})


def test_styles_from_style_data(client):
    names = [s["name"] for s in client.get("/api/gallery/refs/styles").json()["styles"]]
    assert names == ["来源链接", "大理", "中式", "韩式", "自然户外", "黑纱", "主纱", "城堡", "素材", "其他"]


def test_gallery_is_ip_only(client):
    outsider = TestClient(app, headers={"X-Portal-CSRF": "1", "X-Real-IP": "8.8.8.8"})
    assert outsider.get("/api/gallery/refs").status_code == 403
    assert outsider.post("/api/gallery/refs", data={"verdict": "good"}).status_code == 403
    assert outsider.get("/api/gallery/status").json() == {"authorized": False, "holder": None}
    assert client.get("/api/gallery/status").json() == {"authorized": True, "holder": "刘静"}
    assert TestClient(app).post("/api/gallery/redeem", json={"code": "X"}).status_code in (404, 405)


def test_upload_converts_and_strips_exif(client):
    r = upload(client, n=2, source_url="https://example.com/a", note="光线好")
    assert r.status_code == 200
    item = r.json()["items"][0]
    assert item["uploader"] == "刘静" and item["note"] == "光线好" and item["style"] == "02"
    large = Image.open(io.BytesIO(client.get(api(item["large_url"])).content))
    thumb = Image.open(io.BytesIO(client.get(api(item["thumb_url"])).content))
    original = Image.open(io.BytesIO(client.get(api(item["original_url"])).content))
    assert large.format == "WEBP" and max(large.size) == 2048
    assert thumb.format == "WEBP" and max(thumb.size) == 400
    assert original.size == (3000, 1500) and not original.getexif()
    assert b"SecretCam" not in client.get(api(item["original_url"])).content


def test_rejects_bad_input(client):
    assert upload(client, style="99").status_code == 400
    assert upload(client, style="00").status_code == 400  # 00 是链接分类，不放图片
    assert upload(client, source_url="javascript:alert(1)").status_code == 400
    bad = client.post("/api/gallery/refs", files=[("files", ("x.jpg", b"not image", "image/jpeg"))], data={"verdict": "good"})
    assert bad.status_code == 400


def test_file_size_limit(client, monkeypatch):
    monkeypatch.setattr(reference_wall, "MAX_FILE_BYTES", 1000)
    r = upload(client)
    assert r.status_code == 400 and r.json()["error"]["code"] == "FILE_INVALID"


def test_cap(client, monkeypatch):
    monkeypatch.setattr(settings, "reference_cap_gb", 1e-6)  # 约 1 KB
    r = upload(client)
    assert r.status_code == 413 and r.json()["error"]["code"] == "REFERENCE_FULL"
    assert client.get("/api/gallery/refs").json()["items"] == []


def test_filter_edit_delete(client):
    upload(client, verdict="good", style="02")
    bad = upload(client, verdict="bad", style="05").json()["items"][0]
    assert len(client.get("/api/gallery/refs").json()["items"]) == 2
    assert [i["id"] for i in client.get("/api/gallery/refs?verdict=bad").json()["items"]] == [bad["id"]]
    assert client.get("/api/gallery/refs?style=02&verdict=bad").json()["items"] == []
    edited = client.patch(f"/api/gallery/refs/{bad['id']}", json={"style": "09", "note": "手崩了"}).json()
    assert edited["style"] == "09" and edited["note"] == "手崩了"
    assert client.delete(f"/api/gallery/refs/{bad['id']}").status_code == 200
    assert client.get(api(bad["thumb_url"])).status_code == 404
    assert not list((settings.reference_dir / "images").glob(bad["id"] + "*"))


def test_zip_and_export(client):
    upload(client, verdict="good", n=2)
    upload(client, verdict="bad")
    z = zipfile.ZipFile(io.BytesIO(client.get("/api/gallery/refs/zip?verdict=good").content))
    assert len([n for n in z.namelist() if n.endswith(".webp")]) == 2 and "references.json" in z.namelist()
    assert client.get("/api/gallery/refs/zip?style=07").status_code == 404
    assert not list((settings.reference_dir / "tmp").glob("*.zip"))  # 临时 zip 发完即删
    csv_text = client.get("/api/gallery/refs/export?format=csv").text
    assert csv_text.splitlines()[0].startswith("id,style,verdict") and len(csv_text.strip().splitlines()) == 4
    assert len(client.get("/api/gallery/refs/export").json()) == 3
    single = client.get(api(client.get("/api/gallery/refs").json()["items"][0]["large_url"]) + "&download=1")
    assert "attachment" in single.headers["content-disposition"]


def test_not_touched_by_task_cleanup(client):
    from app.api import purge_all
    upload(client)
    purge_all()
    assert len(reference_wall.query()) == 1


def test_tags_search_paging_and_permissions(client, portal_env):
    from conftest import portal_login
    upload(client, style="03", title="白纱逆光", tags="逆光,白纱")
    upload(client, style="08", tags="证件照")
    items = client.get("/api/gallery/refs").json()
    assert items["total"] == 2 and items["counts"] == {"good": 2, "bad": 0}
    assert [i["title"] for i in client.get("/api/gallery/refs", params={"q": "逆光"}).json()["items"]] == ["白纱逆光"]
    assert client.get("/api/gallery/refs", params={"q": "韩式"}).json()["total"] == 1  # 分类名
    assert client.get("/api/gallery/refs", params={"q": "刘静"}).json()["total"] == 2  # 上传人
    assert client.get("/api/gallery/refs", params={"tag": "证件照"}).json()["total"] == 1
    assert client.get("/api/gallery/refs", params={"limit": 1, "offset": 1}).json()["items"][0]["style"] == "03"
    assert {t["tag"] for t in client.get("/api/gallery/refs/tags").json()["tags"]} == {"逆光", "白纱", "证件照"}
    ref_id = client.get("/api/gallery/refs", params={"tag": "证件照"}).json()["items"][0]["id"]
    other = portal_login("gallery", "何选")
    assert other.patch(f"/api/gallery/refs/{ref_id}", json={"tags": ["x"]}).status_code == 403
    assert other.delete(f"/api/gallery/refs/{ref_id}").status_code == 403
    lyk = portal_login("gallery", "lyk")
    assert lyk.patch(f"/api/gallery/refs/{ref_id}", json={"tags": ["合照", "合照", " "]}).json()["tags"] == ["合照"]
    assert client.patch(f"/api/gallery/refs/{ref_id}", json={"title": "新标题"}).json()["title"] == "新标题"
    assert lyk.delete(f"/api/gallery/refs/{ref_id}").status_code == 200


def test_old_uncategorized_migrates_to_other(client):
    item = upload(client, style="02").json()["items"][0]
    with reference_wall._db() as conn:
        conn.execute("UPDATE refs SET style = '00' WHERE id = ?", (item["id"],))
    assert reference_wall.get(item["id"])["style"] == "09"
