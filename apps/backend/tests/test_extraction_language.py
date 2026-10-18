"""AI free text follows the language of the customer's message."""

import pytest

from gigmate.extraction.language import detect_language


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("改下星期四下午三点，地址我晚些发", "zh-Hans"),
        ("改下星期四下午三點，地址我遲啲發", "zh-Hant"),
        ("佢話唔得，改去聽日", "zh-Hant"),
        ("OK 改到星期四 3點", "zh-Hant"),
        ("Can we move to Thursday 3pm?", "en"),
    ],
)
def test_customer_language_is_detected(text, expected):
    assert detect_language(text) == expected


def test_shared_characters_keep_the_configured_chinese_variant(monkeypatch):
    monkeypatch.setenv("GIGMATE_OUTPUT_LANGUAGE", "zh-Hant")
    assert detect_language("改星期四") == "zh-Hant"
    monkeypatch.setenv("GIGMATE_OUTPUT_LANGUAGE", "en")
    assert detect_language("改星期四") == "zh-Hans"


@pytest.mark.parametrize("text", [None, "", "👍", "3 4 5"])
def test_no_recognisable_language_uses_the_fallback(monkeypatch, text):
    monkeypatch.setenv("GIGMATE_OUTPUT_LANGUAGE", "zh-Hant")
    assert detect_language(text) == "zh-Hant"


def test_unknown_fallback_setting_is_ignored(monkeypatch):
    monkeypatch.setenv("GIGMATE_OUTPUT_LANGUAGE", "fr")
    assert detect_language("👍") == "zh-Hans"
