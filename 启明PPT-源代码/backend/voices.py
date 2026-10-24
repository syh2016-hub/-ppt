"""Curated neural voice catalog and language-aware routing."""
from __future__ import annotations

import re
from typing import Any

DEFAULT_ZH_VOICE = "zh-CN-XiaoxiaoNeural"
DEFAULT_EN_VOICE = "en-US-JennyNeural"

VOICE_CATALOG: list[dict[str, Any]] = [
    {
        "id": "zh-CN-XiaoxiaoNeural",
        "name": "晓晓 · 温柔女声",
        "language": "zh",
        "role": "成人女声",
        "gender": "female",
        "description": "温暖、清晰，适合讲课、汇报和课文朗读。",
        "sample": "同学们好，今天我们一起走进这篇课文，慢慢读，认真听。",
    },
    {
        "id": "zh-CN-XiaoyiNeural",
        "name": "晓伊 · 活泼女声",
        "language": "zh",
        "role": "活泼女声",
        "gender": "female",
        "description": "轻快、有亲和力，适合小学课堂和故事讲述。",
        "sample": "小朋友们，准备好了吗？我们要开始读课文啦。",
    },
    {
        "id": "zh-CN-YunxiaNeural",
        "name": "云夏 · 可爱童声",
        "language": "zh",
        "role": "童声",
        "gender": "male",
        "description": "偏童声的可爱音色，适合低年级课文和对话。",
        "sample": "大家好，我是云夏，今天由我陪大家一起读课文。",
    },
    {
        "id": "zh-CN-YunxiNeural",
        "name": "云希 · 阳光男声",
        "language": "zh",
        "role": "成人男声",
        "gender": "male",
        "description": "年轻、阳光，适合课堂讲解和知识分享。",
        "sample": "这一页我们讲清楚三个关键问题，然后用一个例子验证。",
    },
    {
        "id": "zh-CN-YunyangNeural",
        "name": "云扬 · 沉稳男声",
        "language": "zh",
        "role": "成人男声",
        "gender": "male",
        "description": "稳重、专业，适合正式汇报和教研分享。",
        "sample": "接下来，我们从目标、方法和评价三个层面展开分析。",
    },
    {
        "id": "en-US-AnaNeural",
        "name": "Ana · 英文童声",
        "language": "en",
        "role": "英文童声",
        "gender": "female",
        "description": "清晰可爱的英文童声，适合英语课文和低龄教学。",
        "sample": "Hello, boys and girls. Let us read the story together, slowly and clearly.",
    },
    {
        "id": "en-US-JennyNeural",
        "name": "Jenny · 英文女声",
        "language": "en",
        "role": "英文女声",
        "gender": "female",
        "description": "自然、友好，适合英语课堂和讲解。",
        "sample": "Welcome to today's lesson. We will read the passage and find the key idea.",
    },
    {
        "id": "en-US-AvaNeural",
        "name": "Ava · 英文温柔女声",
        "language": "en",
        "role": "英文女声",
        "gender": "female",
        "description": "柔和、有表现力，适合阅读和叙事。",
        "sample": "Take a deep breath, and let the story begin.",
    },
    {
        "id": "en-US-AndrewNeural",
        "name": "Andrew · 英文男声",
        "language": "en",
        "role": "英文男声",
        "gender": "male",
        "description": "温暖、自信，适合课程讲解。",
        "sample": "Let us look at the passage and identify the writer's main argument.",
    },
    {
        "id": "en-GB-SoniaNeural",
        "name": "Sonia · 英音女声",
        "language": "en",
        "role": "英音女声",
        "gender": "female",
        "description": "英式发音，适合英语课文和听力材料。",
        "sample": "Good morning. Today we are going to read a short passage together.",
    },
    {
        "id": "en-GB-RyanNeural",
        "name": "Ryan · 英音男声",
        "language": "en",
        "role": "英音男声",
        "gender": "male",
        "description": "英式发音，沉稳清晰。",
        "sample": "Let us begin with the first paragraph and read it aloud.",
    },
]

VOICE_BY_ID = {item["id"]: item for item in VOICE_CATALOG}
EDGE_VOICE_IDS = set(VOICE_BY_ID)


def public_voices() -> list[dict[str, Any]]:
    return [{k: v for k, v in item.items() if k != "sample"} for item in VOICE_CATALOG]


def get_voice(voice_id: str | None) -> dict[str, Any] | None:
    return VOICE_BY_ID.get(str(voice_id or "").strip())


def default_voice(language: str = "zh") -> str:
    return DEFAULT_EN_VOICE if language == "en" else DEFAULT_ZH_VOICE


def is_english_text(text: str) -> bool:
    sample = re.sub(r"\s+", "", (text or "")[:500])
    if not sample:
        return False
    letters = sum(1 for ch in sample if ("a" <= ch.lower() <= "z"))
    cjk = sum(1 for ch in sample if "\u4e00" <= ch <= "\u9fff")
    return letters > cjk * 2 and letters >= 12


def voice_for_text(text: str, zh_voice: str | None, en_voice: str | None = None) -> str:
    if is_english_text(text):
        return en_voice if get_voice(en_voice) else DEFAULT_EN_VOICE
    return zh_voice if get_voice(zh_voice) else DEFAULT_ZH_VOICE


def normalize_voice(voice_id: str | None, language: str = "zh") -> str:
    voice = get_voice(voice_id)
    if not voice:
        return default_voice(language)
    return voice["id"]
