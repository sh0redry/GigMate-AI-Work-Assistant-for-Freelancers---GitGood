"""Pick the language AI free text is written in: the customer's own language.

The merchant reads the AI's reasons, questions and order summaries next to the
customer's message, so they are written in the language that message uses.
Detection is deliberately simple and deterministic (no model call):

* any Chinese character → Chinese; Traditional when Cantonese particles or
  Traditional-only characters outnumber Simplified-only ones, else Simplified;
* otherwise Latin letters → English;
* nothing recognisable (emoji, digits, empty) → the configured fallback.

Code-mixed Hong Kong messages ("OK 改星期四 3點") count as Chinese.
"""

from __future__ import annotations

import os
import re

SUPPORTED = ("zh-Hans", "zh-Hant", "en")

_CJK = re.compile(r"[㐀-鿿]")
_LATIN = re.compile(r"[A-Za-z]")
# Characters that only appear in one script, chosen from words customers
# actually type when booking (time, place, change, confirm, send).
_TRADITIONAL = set("這個們嗎時間會說還發點裡麼條號樓區議將對預約與實現認確從邊開關幾鐘後覺歡請謝")
_SIMPLIFIED = set("这个们吗时间会说还发点里么条号楼区议将对预约与实现认确从边开关几钟后觉欢请谢")
_CANTONESE = set("嘅咗唔冇啲喺嚟佢係噉咁嘢啱乜嗰睇")


def fallback_language() -> str:
    value = os.environ.get("GIGMATE_OUTPUT_LANGUAGE", "zh-Hans")
    return value if value in SUPPORTED else "zh-Hans"


def detect_language(text: str | None, fallback: str | None = None) -> str:
    default = fallback if fallback in SUPPORTED else fallback_language()
    if not text:
        return default
    if _CJK.search(text):
        traditional = sum(ch in _TRADITIONAL or ch in _CANTONESE for ch in text)
        simplified = sum(ch in _SIMPLIFIED for ch in text)
        if traditional > simplified:
            return "zh-Hant"
        if simplified > traditional:
            return "zh-Hans"
        # Only shared characters (e.g. "改星期四"): keep the configured
        # Chinese variant, or Simplified if the fallback is English.
        return default if default.startswith("zh") else "zh-Hans"
    if _LATIN.search(text):
        return "en"
    return default
