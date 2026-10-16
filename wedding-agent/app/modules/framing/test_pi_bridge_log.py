import logging

from pydantic import BaseModel, ValidationError

from app.modules.framing.pi_bridge import _describe


class _M(BaseModel):
    x: int


def test_describe_hides_validation_input_and_keys():
    try:
        _M(x="secret-user-text")
    except ValidationError as error:
        text = _describe(error)
    assert "ValidationError" in text and "x:" in text and "secret-user-text" not in text
    assert "abc123" not in _describe(RuntimeError("bad key sk-abc123"))


def test_find_node_skips_old_node(monkeypatch, tmp_path):
    from app.modules.framing import pi_bridge
    old = tmp_path / "node22"; old.write_text(""); new = tmp_path / "node24"; new.write_text("")
    monkeypatch.setenv("PI_NODE_BIN", str(old))
    monkeypatch.setattr(pi_bridge.Path, "home", lambda: tmp_path / "nohome")
    monkeypatch.setattr(pi_bridge.shutil, "which", lambda _: str(new))
    monkeypatch.setattr(pi_bridge, "_node_major", lambda n: 22 if n == str(old) else 24)
    pi_bridge._NODE_CACHE.clear()
    assert pi_bridge.find_node() == str(new)
    pi_bridge._NODE_CACHE.clear()


def test_no_suitable_node_gives_clear_error(monkeypatch):
    import pytest
    from app.common.errors import ModuleError
    from app.modules.framing import pi_bridge
    pi_bridge._NODE_CACHE.clear()
    pi_bridge._NODE_CACHE["node"] = None
    with pytest.raises(ModuleError, match="Node 版本过低"):
        pi_bridge.run_pi({}, None, lambda *a: None, 1)
    pi_bridge._NODE_CACHE.clear()
