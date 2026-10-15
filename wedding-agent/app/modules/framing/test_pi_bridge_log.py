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
