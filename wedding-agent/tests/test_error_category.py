from app import runner
from app.common.progress import store


def test_error_info_categories():
    store.create("t_err")
    store.update("t_err", step="framing")
    user = runner._error_info("t_err", "PHOTO_INVALID", "还缺新娘")
    assert user["category"] == "user_input" and not user["retryable"] and user["title"] == "上传的照片不符合要求"
    system = runner._error_info("t_err", "GENERATION_FAILED", "超时")
    assert system["category"] == "system" and system["retryable"]
    assert "摄影师" in system["title"] and "PHOTO" not in system["title"]
