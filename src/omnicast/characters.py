"""Fixed default character presets and OmniVoice Voice Design option catalogs."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class CharacterPreset:
    """OmniVoice Voice Design preset for a built-in character."""

    id: str
    name: str
    role: str
    gender: str
    age: str
    pitch: str
    style: str = "Auto"
    english_accent: str = "Auto"
    chinese_dialect: str = "Auto"

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


OMNIVOICE_DESIGN_OPTIONS: dict[str, list[str]] = {
    "gender": [
        "Auto",
        "Female / 女",
        "Male / 男",
    ],
    "age": [
        "Auto",
        "Child / 儿童",
        "Teenager / 少年",
        "Young Adult / 青年",
        "Middle-aged / 中年",
        "Elderly / 老年",
    ],
    "pitch": [
        "Auto",
        "Very Low Pitch / 极低音调",
        "Low Pitch / 低音调",
        "Moderate Pitch / 中音调",
        "High Pitch / 高音调",
        "Very High Pitch / 极高音调",
    ],
    "style": [
        "Auto",
        "Whisper / 耳语",
    ],
    "english_accent": [
        "Auto",
        "American Accent / 美式口音",
        "British Accent / 英国口音",
        "Australian Accent / 澳大利亚口音",
        "Canadian Accent / 加拿大口音",
        "Japanese Accent / 日本口音",
        "Chinese Accent / 中国口音",
        "Korean Accent / 韩国口音",
        "Indian Accent / 印度口音",
        "Portuguese Accent / 葡萄牙口音",
        "Russian Accent / 俄罗斯口音",
    ],
    "chinese_dialect": [
        "Auto",
        "Henan Dialect / 河南话",
        "Shaanxi Dialect / 陕西话",
        "Sichuan Dialect / 四川话",
        "Guizhou Dialect / 贵州话",
        "Yunnan Dialect / 云南话",
        "Guilin Dialect / 桂林话",
        "Jinan Dialect / 济南话",
        "Shijiazhuang Dialect / 石家庄话",
        "Gansu Dialect / 甘肃话",
        "Ningxia Dialect / 宁夏话",
        "Qingdao Dialect / 青岛话",
        "Northeast Dialect / 东北话",
    ],
}

DEFAULT_CHARACTERS: tuple[CharacterPreset, ...] = (
    CharacterPreset(
        id="Alice",
        name="Alice",
        role="明るいメインホスト／進行",
        gender="Female / 女",
        age="Young Adult / 青年",
        pitch="Moderate Pitch / 中音调",
    ),
    CharacterPreset(
        id="Bob",
        name="Bob",
        role="落ち着いた相方／解説",
        gender="Male / 男",
        age="Middle-aged / 中年",
        pitch="Low Pitch / 低音调",
    ),
    CharacterPreset(
        id="Carol",
        name="Carol",
        role="知的なニュース／朗読女性",
        gender="Female / 女",
        age="Middle-aged / 中年",
        pitch="Low Pitch / 低音调",
    ),
    CharacterPreset(
        id="Dave",
        name="Dave",
        role="テンポの良い若手ゲスト",
        gender="Male / 男",
        age="Young Adult / 青年",
        pitch="Moderate Pitch / 中音调",
    ),
    CharacterPreset(
        id="Narrator",
        name="Narrator",
        role="汎用ナレーション（重厚め）",
        gender="Male / 男",
        age="Middle-aged / 中年",
        pitch="Very Low Pitch / 极低音调",
    ),
)

_CHARACTER_BY_LOWER: dict[str, CharacterPreset] = {
    preset.id.lower(): preset for preset in DEFAULT_CHARACTERS
}
FALLBACK_CHARACTER: CharacterPreset = DEFAULT_CHARACTERS[0]


def get_character(character_id: str) -> CharacterPreset:
    """Return a preset by ID (case-insensitive) or fall back to Alice."""
    preset, _ = resolve_character(character_id)
    return preset


def resolve_character(name: str) -> tuple[CharacterPreset, bool]:
    """Resolve a speaker name to a CharacterPreset and whether it matched."""
    key = name.strip().lower()
    preset = _CHARACTER_BY_LOWER.get(key)
    if preset is not None:
        return preset, True
    return FALLBACK_CHARACTER, False
