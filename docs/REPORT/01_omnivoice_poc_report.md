# OmniVoice 連携 PoC 検証レポート

- **実施日**: 2026-11-13
- **目的**: 別 GPU マシン上で稼働している `k2-fsa/OmniVoice`（Gradio Web UI）に対し、開発環境から `gradio_client` 経由で音声生成・声質クローン・音声結合までを一通り疎通検証し、OmniCast の仕様策定に必要な技術的知見を得る。

---

## 1. 検証環境

| 役割 | 構成 |
| --- | --- |
| クライアント（開発環境） | Python 3.10.12 / `gradio_client` 2.7.2 / `ffmpeg` 4.4.2 |
| 推論サーバー（別 GPU マシン） | `k2-fsa/OmniVoice` Gradio Web UI（環境変数 `OMNIVOICE_URL` で接続） |

---

## 2. 確認した API 仕様

Gradio API として以下の 2 エンドポイントが公開されていることを確認した。

1. **`/_design_fn`**（15 引数）
   - `text`, `lang`, `ns` (Inference Steps, default `32`), `gs` (Guidance Scale, default `2.0`), `dn` (Denoise, default `True`), `sp` (Speed, default `1.0`), `du` (Duration seconds), `pp` (Preprocess Prompt, default `True`), `po` (Postprocess Output, default `True`)
   - 属性指定：`param_9` (Gender), `param_10` (Age), `param_11` (Pitch), `param_12` (Style), `param_13` (English Accent), `param_14` (Chinese Dialect)
2. **`/_clone_fn`**（12 引数）
   - `text`, `lang`, `ref_aud` (`handle_file(...)`), `ref_text`, `instruct`, `ns`, `gs`, `dn`, `sp`, `du`, `pp`, `po`

出力音声はすべて **`pcm_s16le` / `24000 Hz` / モノラル WAV** として返却された。

---

## 3. 検証結果一覧

### 3.1 日本語 PoC（`lang="Japanese"`, `du=0`）

クライアント接続時間: `0.77s`

| # | エンドポイント | 条件概要 | 生成時間 | 出力尺 | Status |
| --- | --- | --- | ---: | ---: | --- |
| 01 | `/_design_fn` | Female / Young Adult / Moderate Pitch, 短文 (`du=0`) | `2.68s` | `5.52s` | `'Done.'` |
| 02 | `/_design_fn` | Male / Middle-aged / Low Pitch, 長め2文 (`du=0`) | `0.97s` | `11.67s` | `'Done.'` |
| 03 | `/_clone_fn` | 01 を `ref_aud` に指定, `ref_text` 指定, `instruct=""` | `1.94s` | `5.11s` | `'Done.'` |
| 04 | `/_clone_fn` | 01 を `ref_aud` に指定, `ref_text=""`, `instruct=""` | `2.22s` | `2.22s` | `'Done.'` |

### 3.2 英語 PoC ＋ 2話者掛け合い結合テスト（`lang="English"`, `du=0`）

| # | エンドポイント / 処理 | 条件概要 | 生成時間 | 出力尺 | Status |
| --- | --- | --- | ---: | ---: | --- |
| 05 | `/_design_fn` | Female / Young Adult / American Accent | `1.58s` | `5.65s` | `'Done.'` |
| 06 | `/_design_fn` | Male / Middle-aged / Low Pitch / British Accent | `1.53s` | `6.65s` | `'Done.'` |
| 07 | `/_clone_fn` | 05 を `ref_aud` に指定, `ref_text=""`, `instruct=""` | `1.49s` | `5.00s` | `'Done.'` |
| 08 | `ffmpeg` 結合 | `05` → 無音 `0.45s` → `06` → 無音 `0.45s` → `07` | - | `18.20s` | - |

---

## 4. 得られた知見

1. **`du=0` で文章量に応じた自動尺推定が機能する**
   - Required 扱いとなっている `du`（Duration）パラメータに `0` を渡したところ、短文（`5.52s`）から長文（`11.67s`）まで文章量に応じて自然な長さが生成された。
2. **推論速度が高速で実用レベル**
   - 1 セグメントあたり約 `1.0s〜2.7s` で生成完了しており、数十発話からなるポッドキャスト生成にも実用的な速度が出ている。
3. **`ref_text=""` 指定の Voice Cloning が自然**
   - 試聴評価として、日本語では `02`（Design）および `04`（`ref_text=""` での Clone）が特に自然な発話として良好だった。
   - 英語の 2 話者掛け合い結合（`08`）もアクセント差異と同一話者（`05` → `07`）の連続性が自然に成立した。
4. **品質の鍵は「ベース音声の作り込み」にある**
   - 最終的な声の魅力や安定性は、クローン元となるベース音声（参照音声）の品質に大きく左右される。
   - OmniCast としては、高品質なベース音声を話者プロファイルとして管理（録音素材または `/_design_fn` で事前に作り込んで登録）し、台本の各発話は `/_clone_fn` で安定生成する構成が有効と判断できる。

---

## 5. OmniCast 仕様策定に向けた次の論点

PoC の結果を受け、次フェーズ（`docs/PLAN/` での仕様策定）では以下を整理する。

- **話者プロファイル管理**: ベース音声（`ref_aud`）＋任意パラメータ（`ref_text`, `instruct`, `lang`, デフォルト `sp`/`ns`/`gs` 等）の定義方法
- **台本フォーマット**: ポッドキャスト（複数話者・ポーズ・BGM/SE）と汎用ナレーションの両方に対応しやすい入力形式（YAML / JSON / Markdown 等）
- **生成・キャッシュ機構**: セグメント単位のハッシュキャッシュ（途中失敗時の再実行・一部セリフ修正時の差分再生成）
- **音声ポスト処理**: `ffmpeg` 等を用いた話者間ポーズ挿入、音量・ラウドネス正規化、出力フォーマット（WAV / MP3 等）
- **バックエンド抽象化**: まずは `gradio_client` アダプタを実装しつつ、将来的な `omnivoice-server` 等への差し替えを見据えたクライアント境界設計
