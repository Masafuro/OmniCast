"""Tests for the @Name: text script parser and exporter."""

from omnicast.models import Project
from omnicast.parser import export_script, parse_script


def test_parse_basic_dialogue_and_comments() -> None:
    script = """
    # Opening comment
    @Alice: こんにちは！時刻は 12:30 です。
    @bob: よろしくお願いします。
    今日はいい天気ですね。
    # Another comment
    @Narrator: こうして物語は始まった。
    """
    blocks, warnings = parse_script(script, default_pause=0.6)
    assert warnings == []
    assert len(blocks) == 3

    assert blocks[0].voice_id == "Alice"
    assert blocks[0].text == "こんにちは！時刻は 12:30 です。"
    assert blocks[0].pause_after == 0.6

    assert blocks[1].voice_id == "Bob"
    assert blocks[1].text == "よろしくお願いします。\n今日はいい天気ですね。"

    assert blocks[2].voice_id == "Narrator"
    assert blocks[2].text == "こうして物語は始まった。"


def test_parse_unknown_speaker_and_leading_text_warnings() -> None:
    script = """
    冒頭のナレーション。
    @UnknownHero: テスト発話
    @Carol: 確認しました。
    """
    blocks, warnings = parse_script(script)
    assert len(blocks) == 3
    assert blocks[0].voice_id == "Alice"
    assert blocks[1].voice_id == "Alice"
    assert blocks[2].voice_id == "Carol"
    assert len(warnings) == 2


def test_export_script_roundtrip() -> None:
    blocks, _ = parse_script("@Alice: Hello\n@Dave: World")
    proj = Project(title="Demo", blocks=blocks)
    out = export_script(proj)
    assert out == "@Alice: Hello\n\n@Dave: World\n"
