import base64
import copy
import json
import shutil
import threading
import time

import pytest

from app.common.config import settings
from app.common.errors import ModuleError
from app.contracts import validate_update
from app.modules.generation import client, node


@pytest.fixture
def real_settings(monkeypatch):
    monkeypatch.setattr(settings, "fake", False)
    monkeypatch.setattr(settings, "llm_api_key", "test-key")
    monkeypatch.setattr(settings, "seedream_model", "injected-test-model")
    monkeypatch.setattr(settings, "runninghub_api_key", "")


def _response(png_bytes):
    return {"model": "injected-test-model",
            "data": [{"b64_json": base64.b64encode(png_bytes).decode(), "size": "1024x1024"}]}


def test_seedream_payload_and_unsupported_seed(real_settings, load_state, png_bytes, monkeypatch):
    calls = []
    def post(url, payload, key):
        calls.append(copy.deepcopy(payload))
        return _response(png_bytes)
    monkeypatch.setattr(client, "_post_json", post)
    state = load_state("after_generation")
    assert client.generate_image(state["photo_urls"], state["prompt"], 42, []) == png_bytes
    payload = calls[0]
    assert payload["prompt"] == state["prompt"]
    assert payload["image"][0].startswith("data:image/png;base64,")
    assert "seed" not in payload and "n" not in payload and "sequential_image_generation" not in payload
    assert payload["watermark"] is False  # 不要方舟角标水印
    assert payload["size"] == "2K"


def test_seedream_size_from_scope_wins(real_settings, load_state, png_bytes, monkeypatch):
    calls = []
    monkeypatch.setattr(client, "_post_json", lambda url, payload, key: calls.append(payload) or _response(png_bytes))
    state = load_state("after_generation")
    scope = client._Scope(client._Budget(2), time.monotonic() + 30, parameters={"size": "1K"})
    with client._call_scope(scope):
        client.generate_image(state["photo_urls"], state["prompt"], 1, [])
    assert calls[0]["size"] == "1K" and calls[0]["watermark"] is False


def test_seedream_uses_asset_reference_bytes(real_settings, load_state, asset_catalog, png_bytes, monkeypatch):
    from app.modules.assets import search_assets
    payloads = []
    def post(url, payload, key):
        payloads.append(payload)
        return _response(png_bytes)
    monkeypatch.setattr(client, "_post_json", post)
    state = load_state("after_generation")
    reference = search_assets("pose", ["medium"])[0]
    client.generate_image(state["photo_urls"], state["prompt"], 1, [{"url": reference["url"], "role": "pose"}])
    assert len(payloads[0]["image"]) == 2


def test_transient_primary_failure_uses_backup(real_settings, png_bytes, monkeypatch):
    seen = []
    monkeypatch.setattr(client, "_runninghub_ready", lambda: True)
    def primary(*args):
        seen.append("primary")
        raise client._ProviderFailure("http_503", retryable=True)
    def backup(photos, prompt, seed, references):
        seen.append("backup")
        scope = client._ACTIVE_SCOPE.get()
        scope.engine, scope.effective_seed = "runninghub", seed
        return png_bytes
    monkeypatch.setattr(client, "_seedream_image", primary)
    monkeypatch.setattr(client, "_runninghub_image", backup)
    scope = client._Scope(client._Budget(4), time.monotonic() + 5)
    with client._call_scope(scope):
        assert client.generate_image(["unused"], "unchanged", 91, []) == png_bytes
    assert seen == ["primary", "backup"] and scope.budget.used == 2
    assert scope.engine == "runninghub" and scope.effective_seed == 91


@pytest.mark.parametrize("code,unknown", [("http_401", False), ("outcome_unknown", True)])
def test_does_not_resubmit_rejected_or_unknown_calls(real_settings, monkeypatch, code, unknown):
    seen = []
    monkeypatch.setattr(client, "_runninghub_ready", lambda: True)
    def primary(*args):
        seen.append("primary")
        raise client._ProviderFailure(code, unknown=unknown)
    monkeypatch.setattr(client, "_seedream_image", primary)
    monkeypatch.setattr(client, "_runninghub_image", lambda *a: seen.append("backup"))
    with pytest.raises(client.ImageCallFailure) as caught:
        client.generate_image(["unused"], "unchanged", 1, [])
    assert not caught.value.retryable
    assert seen == ["primary"]


@pytest.mark.skipif(shutil.which("node") is None, reason="Pi 集成测试需要 Node.js")
def test_actual_pi_runs_sample_then_set(real_settings, load_state, png_bytes, monkeypatch):
    """样片 1 张、套图 9 张；套图阶段用屏障确认并行。"""
    state = load_state("after_generation")
    state["generation"] = {}
    before = copy.deepcopy(state)

    def post_sample(url, payload, key):
        return _response(png_bytes)

    monkeypatch.setattr(client, "_post_json", post_sample)
    sample = node.generate(state)
    validate_update("generate", sample)
    assert len(sample["candidates"]) == 1
    assert sample["generation"]["stage"] == "sample"
    assert sample["generation"]["total_images"] == 1
    assert sample["candidates"][0]["seed"] == -1
    assert sample["generation"]["engine"] == "seedream"
    assert state == before

    prompts = []
    threads = set()
    lock = threading.Lock()
    barrier = threading.Barrier(9)

    def post_set(url, payload, key):
        with lock:
            prompts.append(payload["prompt"])
            threads.add(threading.get_ident())
        barrier.wait(timeout=5)  # 串行实现会失败
        return _response(png_bytes)

    monkeypatch.setattr(client, "_post_json", post_set)
    monkeypatch.setattr(settings, "max_agent_steps", 9)  # 套图 9 张各一次工具调用
    monkeypatch.setattr(settings, "image_timeout_seconds", 60)
    set_state = copy.deepcopy(state)
    set_state["generation"] = {**sample["generation"], "stage": "set"}
    suite = node.generate(set_state)
    validate_update("generate", suite)
    assert len(suite["candidates"]) == 9 and len(threads) == 9
    assert suite["generation"]["stage"] == "set"
    assert suite["generation"]["total_images"] == 10
    assert all(item["seed"] == -1 for item in suite["candidates"])
    assert prompts == [state["prompt"]] * 9


@pytest.mark.skipif(shutil.which("node") is None, reason="Pi 集成测试需要 Node.js")
def test_retry_budget_is_global_for_the_batch(real_settings, load_state, png_bytes, monkeypatch):
    calls = []
    def post(url, payload, key):
        calls.append(1)
        raise client._ProviderFailure("http_503", retryable=True)
    monkeypatch.setattr(client, "_post_json", post)
    monkeypatch.setattr(settings, "max_images_per_task", 5)
    state = load_state("after_generation")
    state["generation"] = {}
    with pytest.raises(ModuleError):
        node.generate(state)
    assert len(calls) <= 5


def test_retouch_parameters_preserve_prompt():
    assert node._parameters("size=1K")["size"] == "1K"
    assert node._parameters("加强人脸一致性") == {"optimize_prompt_options": {"mode": "standard"}}
    with pytest.raises(ModuleError):
        node._parameters("size=512x512")


def test_attempt_logs_do_not_contain_key_or_photos(real_settings, load_state, png_bytes, monkeypatch):
    events = []
    monkeypatch.setattr(client.log, "info", lambda pattern, data: events.append(json.loads(data)))
    monkeypatch.setattr(client, "_post_json", lambda *args: _response(png_bytes))
    state = load_state("after_generation")
    client.generate_image(state["photo_urls"], state["prompt"], 1, [])
    serialized = json.dumps(events)
    assert "test-key" not in serialized
    assert state["photo_urls"][0] not in serialized
    assert "base64" not in serialized
    assert events[0]["seed_supported"] is False
def test_insufficient_budget_never_reduces_target(load_state, monkeypatch):
    # 样片已累计 4 张，套图还要 9 张；上限 10 时剩余不够，不能偷偷少交。
    monkeypatch.setattr(settings, "max_images_per_task", 10)
    state = load_state("after_generation")
    state["generation"] = {**(state.get("generation") or {}), "stage": "set", "total_images": 4}
    with pytest.raises(ModuleError):
        node.generate(state)


@pytest.mark.skipif(shutil.which("node") is None, reason="Pi 集成测试需要 Node.js")
def test_two_tasks_keep_their_pi_results_separate(real_settings, load_state, png_bytes, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    monkeypatch.setattr(client, "_post_json", lambda *a: _response(png_bytes))
    first = load_state("after_generation")
    second = load_state("after_generation")
    first.update(task_id="t_first", generation={})
    second.update(task_id="t_second", generation={})
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(node.generate, [first, second]))
    assert all(result["generation"]["stage"] == "sample" for result in results)
    assert all(result["generation"]["total_images"] == 1 for result in results)
    first_urls = {item["url"] for item in results[0]["candidates"]}
    second_urls = {item["url"] for item in results[1]["candidates"]}
    assert len(first_urls) == len(second_urls) == 1
    assert not first_urls & second_urls


@pytest.mark.skipif(shutil.which("node") is None, reason="Pi 集成测试需要 Node.js")
def test_set_uses_each_slot_prompt(real_settings, load_state, png_bytes, monkeypatch):
    """有分镜提示词时，套图每张用自己 slot 的提示词。"""
    state = load_state("after_generation")
    state["generation"] = {"stage": "set", "total_images": 1, "engine": "seedream", "workflow": "x", "seconds": 1}
    state["shot_prompts"] = [{"slot": slot, "prompt": f"镜头{slot}"} for slot in range(9)]
    prompts, lock = [], threading.Lock()

    def post(url, payload, key):
        with lock:
            prompts.append(payload["prompt"])
        return _response(png_bytes)

    monkeypatch.setattr(client, "_post_json", post)
    monkeypatch.setattr(settings, "max_agent_steps", 9)
    monkeypatch.setattr(settings, "image_timeout_seconds", 60)
    suite = node.generate(state)
    assert len(suite["candidates"]) == 9
    assert sorted(prompts) == sorted(f"镜头{slot}" for slot in range(9))
