from transcript_normalizer import normalize_segments


def _segment(number, start, end, text):
    return {"segment_id": f"seg_{number:04}", "start": start, "end": end, "text": text}


def test_overlapping_rolling_captions_form_non_overlapping_sentences():
    raw = [
        _segment(1, 3.679, 7.120, "Every time you explain your team's"),
        _segment(2, 5.200, 9.519, "coding standards to Claude, you're"),
        _segment(3, 7.120, 12.160, "repeating yourself."),
        _segment(4, 9.519, 13.840, "Every PR review, starts again."),
    ]
    units = normalize_segments(raw)
    assert len(units) == 2
    assert units[0]["source_end"] == 9.519
    assert units[0]["source_end"] <= units[1]["source_start"]
    assert units[0]["source_segment_ids"] == ["seg_0001", "seg_0002", "seg_0003"]


def test_rolling_caption_words_do_not_multiply():
    raw = [
        _segment(1, 0, 2, "We build reliable"),
        _segment(2, 1, 3, "We build reliable systems."),
    ]
    units = normalize_segments(raw)
    assert units[0]["source_text"] == "We build reliable systems."


def test_fragmented_sentence_is_joined_and_has_valid_duration():
    raw = [
        _segment(1, 0, 1, "This is"),
        _segment(2, 0.8, 2, "one sentence."),
        _segment(3, 3.5, 4.5, "Another one."),
    ]
    units = normalize_segments(raw)
    assert units[0]["source_text"] == "This is one sentence."
    assert all(unit["source_start"] < unit["source_end"] for unit in units)
    assert all(left["source_end"] <= right["source_start"] for left, right in zip(units, units[1:]))


def test_multiple_sentences_in_one_caption_keep_all_text():
    units = normalize_segments([_segment(1, 1, 4, "First sentence. Second sentence.")])
    assert [unit["source_text"] for unit in units] == ["First sentence.", "Second sentence."]
    assert units[0]["source_end"] == units[1]["source_start"]


def test_real_caption_regression_uses_in_caption_sentence_timing():
    raw = [
        _segment(1, 3.679, 7.120, "Every time you explain your team's"),
        _segment(2, 5.200, 9.519, "coding standards to Claude, you're"),
        _segment(3, 7.120, 12.160, "repeating yourself."),
        _segment(4, 9.519, 13.840, "Every PR review, you redescribe how you"),
        _segment(5, 12.160, 16.080, "want feedback [music] structured. Every"),
        _segment(6, 13.840, 18.320, "commit message, you remind Claude of"),
        _segment(7, 16.080, 21.439, "your preferred format,"),
        _segment(8, 18.320, 22.925, "and skills fix this. A skill is a"),
        _segment(9, 21.439, 24.720, "markdown file that teaches Claude"),
        _segment(10, 22.925, 26.320, "[music] how to do something once, and"),
        _segment(11, 24.720, 30.599, "Claude applies that knowledge"),
        _segment(12, 26.320, 30.599, "automatically whenever it's relevant."),
    ]

    units = normalize_segments(raw)
    texts = [unit["source_text"] for unit in units]
    first = texts.index("Every time you explain your team's coding standards to Claude, you're repeating yourself.")
    review = texts.index("Every PR review, you redescribe how you want feedback structured.")
    commit = texts.index("Every commit message, you remind Claude of your preferred format, and skills fix this.")

    assert first == 0
    assert units[review]["source_end"] != 12.160
    assert units[commit]["source_start"] != 12.160
    assert all(unit["source_start"] < unit["source_end"] for unit in units)
    assert all(left["source_end"] <= right["source_start"] for left, right in zip(units, units[1:]))

    expected_words = [
        word
        for segment in raw
        for word in segment["text"].split()
        if word.casefold() not in {"[music]", "[applause]", "[laughter]"}
    ]
    normalized_words = " ".join(texts).split()
    assert normalized_words == expected_words
    assert "[music]" not in normalized_words


def test_consecutive_micro_units_coalesce_in_order_with_outer_timing():
    units = normalize_segments([_segment(1, 0, 1.2, "A. B. C. End.")],
                               min_tts_unit_seconds=.71)
    assert [unit["unit_id"] for unit in units] == ["utt_0001"]
    assert units[0]["source_text"] == "A. B. C. End."
    assert units[0]["source_segment_ids"] == ["seg_0001"]
    assert (units[0]["source_start"], units[0]["source_end"]) == (0.0, 1.2)
    assert units[0]["source_unit_ids"] == ["utt_0001", "utt_0002", "utt_0003", "utt_0004"]
    assert units[0]["coalesced"] is True


def test_micro_unit_does_not_cross_real_pause():
    units = normalize_segments([_segment(1, 0, .5, "Tiny."),
                                _segment(2, 2, 4, "Later speech.")])
    assert [unit["source_text"] for unit in units] == ["Tiny.", "Later speech."]
    assert units[0]["coalesced"] is False


def test_micro_unit_does_not_create_overlong_unit():
    units = normalize_segments([_segment(1, 0, .5, "Tiny."),
                                _segment(2, .5, 2, "Long speech continues")],
                               max_duration=1.5)
    assert len(units) == 2
    assert all(unit["available_duration"] <= 1.5 for unit in units)


def test_boundary_cue_markers_are_removed_without_damaging_technical_text():
    raw = [
        _segment(1, 0, 1, ">>"),
        _segment(2, 1, 3, ">> leading speech."),
        _segment(3, 3, 5, "trailing speech. >>"),
        _segment(4, 5, 8, "x > 10; A >= B; foo -> bar."),
    ]
    units = normalize_segments(raw, min_tts_unit_seconds=0)

    assert [unit["source_text"] for unit in units] == [
        "leading speech.", "trailing speech.", "x > 10; A >= B; foo -> bar.",
    ]
    assert all(">>" not in unit["source_text"] for unit in units)
    assert units[0]["source_segment_ids"] == ["seg_0002"]
    assert (units[0]["source_start"], units[0]["source_end"]) == (1.667, 3.0)
    assert units[1]["source_segment_ids"] == ["seg_0003"]
    assert (units[1]["source_start"], units[1]["source_end"]) == (3.0, 4.333)
