# OmniCast v0.1 仕様・設計書

- **作成日**: 2026-11-13
- **ステータス**: Draft（PoC 検証完了後の v0.1 基本設計）
- **前提レポート**: [01_omnivoice_poc_report.md](../REPORT/01_omnivoice_poc_report.md)

---

## 1. コンセプトと設計思想

OmniCast は、`k2-fsa/OmniVoice` を推論エンジンとして用い、**ポッドキャストや汎用ナレーション音声を「台本・声・テイク・間」の反復調整を通じて仕上げる制作スタジオ**である。

### 解決すべき本質的課題
1. **非決定的な揺らぎと収束**：AI 音声合成は同じ入力でも毎回わずかに異なる結果になる。一括全再生成をすると、すでに納得できたセリフまで変わってしまうため、**区画（ブロック）単位で生成・テイク比較・確定（ロック）**できる必要がある。
2. **台本 ⇄ 音声の双方向ループ**：音を聴きながらセリフを直し、間（ポーズ）を調整し、気に入らない行だけリテイクする制作フローをストレスなく回せること。
3. **ベース音声の作り込み**：最終品質は参照音声（`ref_aud`）に大きく依存するため、録音素材の登録だけでなく OmniVoice の `design` 機能で試作した音声をベース音声として育て・使い回せること。

---

## 2. システム構成と配置トポロジー

### 技術スタック（v0.1）
- **バックエンド + UI 配信**: Python 3.10+ / `FastAPI` + `uvicorn`
- **OmniVoice 連携**: `gradio_client`（将来的な `omnivoice-server` 等への差し替えに備えアダプタ層で抽象化）
- **音声結合・書き出し**: `ffmpeg` / `ffprobe`
- **フロントエンド**: ビルド不要の軽量 Web UI（HTML / CSS / Vanilla JS + Web Audio API + PWA Manifest）

### 配置パターン（設定のみで両対応）
1. **同居構成（推奨）**: GPU マシン上で OmniVoice と OmniCast（FastAPI）を両方起動し、`OMNIVOICE_URL=http://127.0.0.1:8000` でローカル通信。LAN 内の別 PC やタブレット等のブラウザから OmniCast にアクセスする。
2. **分離構成**: 開発マシン等で OmniCast を起動し、`.env` の `OMNIVOICE_URL` 経由で GPU マシンの OmniVoice に接続する。

> [!NOTE]
> LAN 内の `http://<IP>:<PORT>` でも通常の Web アプリとしてはそのまま利用可能。ブラウザの PWA インストール（Service Worker）を有効にする場合は、`localhost` または HTTPS（リバースプロキシ / Tailscale 等）経由でのアクセスを想定する。

---

## 3. データ永続化とディレクトリ設計

外部データベースは使用せず、ローカルファイルシステム（`data/`、`.gitignore` 対象）にプロジェクト単位で完結させる。

```text
data/
  voices/
    <voice_id>/
      profile.json          # 声プロファイル定義
      ref_audio.wav         # ベース参照音声（clone用）
  projects/
    <project_id>/
      project.json          # エピソード設定・ブロック一覧・選択テイク・間の値
      takes/
        <block_id>_t001.wav # 生成済みテイク音声
        <block_id>_t002.wav
      exports/
        <title>.wav         # 書き出し済み完成音声
```

---

## 4. データモデル（rev1 / rev2）

### 4.1 デフォルトキャラクター（rev1 固定プリセット）
rev1 では独立したボイスプロファイル管理画面（Cast タブ）を後回しにし、以下の 5 名を OmniCast 標準キャラクターとして固定定義する（OmniVoice `/_design_fn` パラメータを使用）。

| 名前（`@Name`） | 役割イメージ | 性別 (`param_9`) | 年齢 (`param_10`) | 音調 (`param_11`) |
| --- | --- | --- | --- | --- |
| `Alice` | 明るいメインホスト／進行 | `Female / 女` | `Young Adult / 青年` | `Moderate Pitch / 中音调` |
| `Bob` | 落ち着いた相方／解説 | `Male / 男` | `Middle-aged / 中年` | `Low Pitch / 低音调` |
| `Carol` | 知的なニュース／朗読女性 | `Female / 女` | `Middle-aged / 中年` | `Low Pitch / 低音调` |
| `Dave` | テンポの良い若手ゲスト | `Male / 男` | `Young Adult / 青年` | `Moderate Pitch / 中音调` |
| `Narrator` | 汎用ナレーション（重厚め） | `Male / 男` | `Middle-aged / 中年` | `Very Low Pitch / 极低音调` |

- 言語（`lang`）はプロジェクト既定（`Auto` / `Japanese` / `English` 等）＋区画ごとの上書きで指定可能とする。
- rev2 では、これらのキャラクター名や新規キャラクターへユーザー独自のベース音声（`clone` 用 `ref_audio`）を割り当て・育成できる `VoiceProfile` 機能を追加する。

### 4.2 Project（エピソード）
| フィールド | 型 | 説明 |
| --- | --- | --- |
| `id` | `str` | プロジェクト ID |
| `title` | `str` | タイトル |
| `default_lang` | `str` | 既定の言語（例：`Auto`, `Japanese`, `English`） |
| `default_turn_pause` | `float` | インポート時の話者間デフォルトポーズ秒（例：`0.45`） |
| `trim_silence` | `bool` | 書き出し時に各クリップ前後の余分な無音を軽くトリムするか |
| `normalize_loudness` | `bool` | 書き出し時に音量を揃えるか（EBU R128 等） |
| `blocks` | `list[Block]` | 時系列の発話ブロック列 |

### 4.3 Block（発話区画）
台本の 1 発話と、その音声テイク・間を統合管理する最小単位。

| フィールド | 型 | 説明 |
| --- | --- | --- |
| `id` | `str` | 不変のブロック ID（行挿入・並び替えでもズレない） |
| `voice_id` | `str` | 紐づくキャラクター ID（`Alice`, `Bob`, `Carol`, `Dave`, `Narrator`） |
| `text` | `str` | 台本本文（画面表示・台本エクスポート用） |
| `tts_text` | `str \| null` | 読み上げ専用オーバーライド（漢字の読み誤り修正用。`null` 時は `text` を使用） |
| `lang` | `str \| null` | 区画単位の言語上書き |
| `speed` | `float \| null` | 区画単位の話速上書き |
| `style` | `str \| null` | 区画単位のスタイル上書き（`Auto` / `Whisper / 耳语`） |
| `pause_after` | `float` | この発話の後ろに入れる間（秒） |
| `takes` | `list[Take]` | 生成済みテイクの履歴リスト |
| `selected_take_id` | `str \| null` | 現在採用中のテイク ID |
| `locked` | `bool` | ロックフラグ（`true` の場合、一括 Generate の対象外） |

### 4.4 Take（生成テイク）
| フィールド | 型 | 説明 |
| --- | --- | --- |
| `id` | `str` | テイク ID（例：`t001`, `t002`） |
| `file` | `str` | WAV ファイル名 |
| `duration` | `float` | 音声長（秒、`ffprobe` 計測） |
| `input_hash` | `str` | 生成時の `(effective_tts_text, voice_snapshot, params)` ハッシュ |
| `created_at` | `str` | 生成日時（ISO 8601） |

**ブロック状態（算出プロパティ）**:
- `unbuilt`: `selected_take_id` が無い
- `locked`: `locked == true`
- `dirty`: 選択中テイクの `input_hash` と現在の設定から算出したハッシュが不一致（テキストや話者を編集済み）
- `ready`: 選択中テイクが存在し、現在の入力と一致

---

## 5. 台本インポート / エクスポート仕様

一括作成・LLM 連携の入口および確定テキストの出口として、`@Name: text` に特化したシンプルな行指向テキスト記法をサポートする。間（ポーズ）の調整はすべて GUI 側に一本化する。

### 5.1 インポート記法（v0.1）
```text
# コメント行は無視される
@Alice: こんにちは、OmniCast へようこそ！
@Bob: よろしくお願いします。
今日もいい天気ですね。
```

- `@<Name>: <Text>`: 新しい発話ブロックを開始する。`<Name>` は標準キャラクター（`Alice`, `Bob`, `Carol`, `Dave`, `Narrator`）を大文字小文字を緩やかに照合し、未知の名前の場合は警告を出しつつ `Alice` へフォールバックする。
- 直前の `@<Name>:` に続く通常行: 同一ブロックの `text` に改行付きで連結する（空行は無視または段落区切りとして整理）。
- 各ブロックの `pause_after` の初期値にはプロジェクトの `default_turn_pause` を設定し、調整は GUI 上で行う。

### 5.2 テキストエクスポート
- 各ブロックを `@<VoiceName>: <text>` 形式で 1 本の台本テキストとして出力する。

### 5.3 音声エクスポート（`ffmpeg`）
1. `selected_take` が存在する（または未生成警告を出した上で有効な）各ブロックを順に取得。
2. `trim_silence=true` の場合、各クリップ前後の極端な無音を軽くトリム（語頭・語尾の安全マージン＋約 10ms の微小フェードでクリックノイズ防止）。
3. 各ブロックの後ろに `pause_after` 秒の無音（`24000Hz / mono`）を挿入して連結。
4. `normalize_loudness=true` の場合、`loudnorm` 等で音量を均一化。
5. WAV（または MP3）として `exports/` に書き出し、ダウンロード可能にする。

---

## 6. Web UI 設計（v0.1）

### 6.1 Studio タブ（メイン制作画面）
- **トップバー**:
  - プロジェクト切替 / 新規作成
  - **台本インポート**ボタン（モーダルにテキスト貼り付け or ファイル選択）
  - **Generate** ボタン（`!locked` なすべてのブロックを順次生成・再生成し進捗表示）
  - **通し PLAY / 停止**ボタン（Web Audio API により、採用テイク＋現在の `pause_after` を即座に連続再生・再生中ブロックをハイライト。途中行からの再生も可）
  - **Export** ボタン（WAV / MP3 書き出し & ダウンロード）
- **ブロック一覧（1 本の台本として縦表示）**:
  - ドラッグまたは上下ボタンで並び替え、任意位置への行追加・削除
  - 各ブロックカードの構成：
    - 状態バッジ（`未生成` / `要再生成` / `準備完了` / `ロック`）
    - 話者セレクト + セリフテキスト（編集エリア）
    - 詳細トグル（任意：`読み(tts_text)` / `speed` / `style` / `lang`）
    - アクションバー：
      - **▶ 再生**（このブロックのみ即試聴）
      - **🔄 リテイク**（新テイクを生成して即採用）
      - **テイク切替ピル**（`T1`, `T2`, `T3`… クリックで過去テイクへ即切替）
      - **🔒 ロック**（確定保護トグル）
      - **後の間（秒）**（数値入力 + `-0.1 / +0.1` 等で微調整）

### 6.2 Cast タブ（rev2 で実装予定）
- 登録済みの声一覧・試聴・パラメータ編集・削除
- **ベース音声アップロード登録**：手元の WAV/MP3 等をアップロードして既存キャラ上書き・新規 Cast 作成
- **Voice Design ラボ**：OmniVoice の `/_design_fn` を使ってテスト音声を試作・試聴し、気に入った音声をベース音声（`clone` 用）として保存

---

## 7. バックエンド API 概要（FastAPI）

| 分類 | エンドポイント | 用途 |
| --- | --- | --- |
| ヘルス/設定 | `GET /api/health` | サーバー状態 & OmniVoice 接続設定確認 |
| キャラクター | `GET /api/characters` | デフォルトキャラクター 5 名の一覧取得（rev1） |
| プロジェクト | `GET /api/projects`, `POST /api/projects`, `GET /api/projects/{id}`, `PATCH /api/projects/{id}`, `DELETE /api/projects/{id}` | エピソード管理 |
| 台本入出力 | `POST /api/projects/{id}/import-script`, `GET /api/projects/{id}/export-script` | `@Name: text` 台本のインポート・エクスポート |
| ブロック操作 | `POST /api/projects/{id}/blocks`, `PATCH /api/projects/{id}/blocks/{bid}`, `DELETE ...`, `POST .../reorder` | 区画の追加・編集・並び替え |
| 音声生成 | `POST /api/projects/{id}/blocks/{bid}/generate`, `POST /api/projects/{id}/generate` | 単体リテイク・一括 Generate（非ロック全再生成） |
| 音声取得/出力 | `GET /api/projects/{id}/takes/{file}`, `POST /api/projects/{id}/export`, `GET /api/projects/{id}/exports/{file}` | 個別テイク再生用配信・結合ファイル書き出し |

---

## 8. 開発ロードマップ（rev1 / rev2）

### rev1（先行実装：台本パーサー ＋ Studio GUI）
1. **プロジェクト基盤整備**: `pyproject.toml`, `src/omnicast/`, `.gitignore` への `data/` 追加、OmniVoice クライアント層（`GradioOmniVoiceClient` + `MockOmniVoiceClient`）
2. **コアドメイン・パーサー・音声結合**: `Project` / `Block` / `Take` モデル、デフォルト 5 キャラクター定義、`@Name: text` 台本パーサー、`ffmpeg` 結合エクスポーター＋自動テスト
3. **FastAPI サーバー & Studio Web UI**: 全 API エンドポイント、台本インポート、区画ごとの再生/リテイク/テイク切替/ロック/間調整、Web Audio API 通し PLAY、WAV/MP3 Export、PWA Manifest

### rev2（拡張：ボイスプロファイル管理）
4. **Cast 管理 & Voice Cloning 統合**: `data/voices/` 永続化、音声アップロード、Voice Design ラボからのベース音声登録、`/_clone_fn` 切替対応
