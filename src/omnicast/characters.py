"""Fixed default character presets for OmniCast rev1."""

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
