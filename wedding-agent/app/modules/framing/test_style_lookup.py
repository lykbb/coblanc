from app.modules.framing import style_lookup as sl


def test_mapping_picks_cases_for_every_mapped_style():
    for style in sl.STYLE_MAP:
        ids = sl.pick_cases(style)
        assert 1 <= len(ids) <= sl.MAX_CASES, style


def test_unmapped_and_missing_style_fall_back_to_nothing():
    assert sl.style_references("keep_original") == ([], "")
    assert sl.style_references(None) == ([], "")
    assert sl.style_references("unknown_style") == ([], "")


def test_flagged_cases_are_skipped():
    flagged = {"SET000029", "SET000030", "SET000038", "SET000054", "SET000061", "SET000070", "SET000071", "SET000073"}
    for style in sl.STYLE_MAP:
        assert not flagged & set(sl.pick_cases(style, limit=50))
    assert sl._flagged("SET000071") and sl._flagged("SET000030")
    assert not sl._flagged("SET000022")


def test_duplicate_versions_skipped():
    assert "SET000075" not in sl.pick_cases("french_editorial", limit=50)


def test_prompt_text_bounded_and_link_free():
    for style in sl.STYLE_MAP:
        ids, text = sl.style_references(style)
        assert ids and len(text) <= sl.MAX_TOTAL_CHARS
        for bad in ("http", "feishu", "weibo", "xiaohongshu", "service_url"):
            assert bad not in text


def test_missing_data_dir_is_harmless(monkeypatch, tmp_path):
    monkeypatch.setattr(sl, "DATA_ROOT", tmp_path / "nope")
    assert sl.style_references("korean_studio") == ([], "")
