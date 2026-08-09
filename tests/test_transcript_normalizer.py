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
    assert len(units) == 1
    assert units[0]["source_text"] == "First sentence. Second sentence."
