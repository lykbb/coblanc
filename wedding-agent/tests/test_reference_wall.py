"""参考图墙：鉴权、上传转码去 EXIF、容量上限、筛选、编辑删除、打包、导出。"""
import io
import zipfile

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import access, reference_wall
from app.api import app
from app.common.config import settings


def jpeg_with_exif(size=(3000, 1500)) -> bytes:
    exif = Image.Exif()
    exif[0x010F] = "SecretCam"  # Make
    out = io.BytesIO()
    Image.new("RGB", size, (200, 120, 110)).save(out, "JPEG", exif=exif.tobytes())
    return out.getvalue()


@pytest.fixture
def client(admin_client):
    return admin_client


def upload(c, verdict="good", style="02", n=1, **extra):
    files = [("files", (f"p{i}.jpg", jpeg_with_exif(), "image/jpeg")) for i in range(n)]
    return c.post("/api/admin/refs", files=files, data={"style": style, "verdict": verdict, **extra})


def test_styles_from_style_data(client):
    names = [s["name"] for s in client.get("/api/admin/refs/styles").json()["styles"]]
    assert names == ["待分类", "大理", "中式", "韩式", "自然户外", "黑纱", "主纱", "城堡"]


def test_requires_admin(client):
    anon = TestClient(app, headers={"X-Admin-CSRF": "1"})
    assert anon.get("/api/admin/refs").status_code == 401
    assert anon.post("/api/admin/refs", data={"verdict": "good"}).status_code == 401
    [(_, code)] = access.create(["小王"])  # 用户站设备凭证进不了后台
    anon.post("/api/access/redeem", json={"code": code})
    assert anon.get("/api/admin/refs").status_code == 401


def test_upload_converts_and_strips_exif(client):
    r = upload(client, n=2, source_url="https://example.com/a", note="光线好")
    assert r.status_code == 200
    item = r.json()["items"][0]
    assert item["uploader"] == "lyk" and item["note"] == "光线好" and item["style"] == "02"
    large = Image.open(io.BytesIO(client.get(item["large_url"]).content))
    thumb = Image.open(io.BytesIO(client.get(item["thumb_url"]).content))
    original = Image.open(io.BytesIO(client.get(item["original_url"]).content))
    assert large.format == "WEBP" and max(large.size) == 2048
    assert thumb.format == "WEBP" and max(thumb.size) == 400
    assert original.size == (3000, 1500) and not original.getexif()
    assert b"SecretCam" not in client.get(item["original_url"]).content


def test_rejects_bad_input(client):
    assert upload(client, style="99").status_code == 400
    assert upload(client, source_url="javascript:alert(1)").status_code == 400
    bad = client.post("/api/admin/refs", files=[("files", ("x.jpg", b"not image", "image/jpeg"))], data={"verdict": "good"})
    assert bad.status_code == 400


def test_file_size_limit(client, monkeypatch):
    monkeypatch.setattr(reference_wall, "MAX_FILE_BYTES", 1000)
    r = upload(client)
    assert r.status_code == 400 and r.json()["error"]["code"] == "FILE_INVALID"


def test_cap(client, monkeypatch):
    monkeypatch.setattr(settings, "reference_cap_gb", 1e-6)  # 约 1 KB
    r = upload(client)
    assert r.status_code == 413 and r.json()["error"]["code"] == "REFERENCE_FULL"
    assert client.get("/api/admin/refs").json()["items"] == []


def test_filter_edit_delete(client):
    upload(client, verdict="good", style="02")
    bad = upload(client, verdict="bad", style="05").json()["items"][0]
    assert len(client.get("/api/admin/refs").json()["items"]) == 2
    assert [i["id"] for i in client.get("/api/admin/refs?verdict=bad").json()["items"]] == [bad["id"]]
    assert client.get("/api/admin/refs?style=02&verdict=bad").json()["items"] == []
    edited = client.patch(f"/api/admin/refs/{bad['id']}", json={"style": "00", "note": "手崩了"}).json()
    assert edited["style"] == "00" and edited["note"] == "手崩了"
    assert client.delete(f"/api/admin/refs/{bad['id']}").status_code == 200
    assert client.get(bad["thumb_url"]).status_code == 404
    assert not list((settings.reference_dir / "images").glob(bad["id"] + "*"))


def test_zip_and_export(client):
    upload(client, verdict="good", n=2)
    upload(client, verdict="bad")
    z = zipfile.ZipFile(io.BytesIO(client.get("/api/admin/refs/zip?verdict=good").content))
    assert len([n for n in z.namelist() if n.endswith(".webp")]) == 2 and "references.json" in z.namelist()
    assert client.get("/api/admin/refs/zip?style=07").status_code == 404
    assert not list((settings.reference_dir / "tmp").glob("*.zip"))  # 临时 zip 发完即删
    csv_text = client.get("/api/admin/refs/export?format=csv").text
    assert csv_text.splitlines()[0].startswith("id,style,verdict") and len(csv_text.strip().splitlines()) == 4
    assert len(client.get("/api/admin/refs/export").json()) == 3
    single = client.get(client.get("/api/admin/refs").json()["items"][0]["large_url"] + "&download=1")
    assert "attachment" in single.headers["content-disposition"]


def test_not_touched_by_task_cleanup(client):
    from app.api import purge_all
    upload(client)
    purge_all()
    assert len(reference_wall.query()) == 1
