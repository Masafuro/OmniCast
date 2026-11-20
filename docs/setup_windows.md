# Windows GPU マシン導入・運用リファレンス

Windows の GPU マシン上で **`k2-fsa/OmniVoice`** と **`OmniCast`** を同居させ、必要なときだけ起動して **LAN 内の別 PC・タブレット等からブラウザで利用する**ための導入ガイドです。

---

## 1. 想定構成

```text
[LAN 内の別 PC / Mac / タブレット]
        │  http://<WindowsマシンのIP>:8080
        ▼
┌─────────────────────────────────────────────────┐
│ Windows GPU マシン                              │
│                                                 │
│  OmniCast Studio (FastAPI + Web UI)             │
│    Listen: 0.0.0.0:8080                         │
│        │  http://127.0.0.1:8000 (gradio_client) │
│        ▼                                        │
│  k2-fsa/OmniVoice (Gradio Web UI / GPU 推論)    │
└─────────────────────────────────────────────────┘
```

- **運用スタイル**: 常駐サービス化はせず、利用時のみ `OmniVoice` → `OmniCast` の順に手動起動し、使い終わったら終了します。
- **仮想環境の分離**: 依存パッケージ競合を防ぐため、OmniCast は OmniVoice とは別の専用 Python 仮想環境（`.venv`）に導入します（OmniCast 側には PyTorch や CUDA は不要です）。
- **公開ポート**: LAN 向けに開放するのは原則 **OmniCast の TCP `8080` 番のみ** で構いません（OmniVoice の `8000` 番はローカル通信 `127.0.0.1` で完結します）。

---

## 2. 事前確認（前提環境）

Windows マシン上で PowerShell を開き、以下が揃っていることを確認します。

| 項目 | 要件 | 確認コマンド |
| --- | --- | --- |
| Git | Git for Windows 等 | `git --version` |
| Python | **3.10 以上** | `python --version`（または `py -3 --version`） |
| ffmpeg / ffprobe | PATH に通っていること | `ffmpeg -version` および `ffprobe -version` |
| OmniVoice | 同マシン上で Gradio Web UI が起動できること | 起動後に `http://127.0.0.1:8000` を開けること |

### `ffmpeg` / `ffprobe` が未導入の場合

`winget` で導入できます（`ffmpeg` と `ffprobe` がセットで入ります）。

```powershell
winget install Gyan.FFmpeg
```

> [!IMPORTANT]
> `winget` による導入後は **PowerShell を開き直して** PATH を反映し、`ffmpeg -version` と `ffprobe -version` の両方が通ることを確認してください。

> [!NOTE]
> `python --version` で Microsoft Store が開く場合は、Windows の「アプリ実行エイリアス」で `python.exe` / `python3.exe` をオフにするか、`py -3` コマンドを使用してください。

---

## 3. 初回セットアップ手順

PowerShell で作業用ディレクトリ（日本語やスペースを含まないパスを推奨。例：`C:\work`）へ移動し、以下を実行します。

```powershell
# 1. リポジトリを取得
cd C:\work
git clone https://github.com/Masafuro/OmniCast.git
cd OmniCast

# 2. 専用仮想環境を作成（OmniVoice の環境とは分離する）
python -m venv .venv

# 3. パッケージをインストール（venv の python を直接呼ぶと実行ポリシーの影響を受けません）
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\pip.exe install .

# 4. 設定ファイル (.env) を作成
Copy-Item .env.example .env
```

> [!TIP]
> 仮想環境を有効化（`.\.venv\Scripts\Activate.ps1`）して使いたい場合に PowerShell の実行ポリシーエラーが出る場合は、初回のみ以下を実行します。
> ```powershell
> Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
> ```

### `.env` の設定項目

`.env` をエディタで開き、必要に応じて編集します。OmniVoice が同マシンの既定ポート（`8000`）で動く場合はデフォルトのままで動作します。

| 変数名 | デフォルト値 | 説明 |
| --- | --- | --- |
| `OMNIVOICE_URL` | `http://127.0.0.1:8000` | OmniVoice Gradio サーバーの URL（別ポート例：`http://127.0.0.1:7860`） |
| `OMNICAST_DATA_DIR` | `./data` | プロジェクト・テイク音声・Cast データの保存先 |
| `OMNICAST_HOST` | `0.0.0.0` | 待受アドレス（LAN 内の他マシンから接続するため `0.0.0.0` を維持） |
| `OMNICAST_PORT` | `8080` | Web UI の待受ポート（他アプリと競合する場合のみ変更） |

> [!NOTE]
> **OmniVoice を WSL2 上で起動している場合**でも、通常は Windows 側から `http://127.0.0.1:8000` で接続できます（WSL2 の localhostForwarding）。接続できない場合は WSL 側で `hostname -I` を確認し、その IP を `OMNIVOICE_URL` に指定してください。

---

## 4. LAN 内の他マシンからアクセスするための設定

Windows 側の初回設定として、以下の 3 点を行います。

### 4.1 ネットワークプロファイルを「プライベート」にする

1. Windows の **設定** → **ネットワークとインターネット** → 接続中の Wi-Fi またはイーサネットを開く。
2. ネットワークプロファイルの種類が **プライベート ネットワーク** になっていることを確認する（「パブリック」だと LAN からの着信がブロックされます）。

### 4.2 Windows Defender ファイアウォールで TCP 8080 を許可する

**管理者として実行した PowerShell** で以下を実行し、プライベートネットワーク（自宅・社内 LAN）からの TCP `8080` 番への着信のみを許可します。

```powershell
New-NetFirewallRule `
  -DisplayName "OmniCast Studio (TCP 8080)" `
  -Direction Inbound `
  -Protocol TCP `
  -LocalPort 8080 `
  -Profile Private `
  -Action Allow
```

- `OMNICAST_PORT` を変更した場合は `-LocalPort` の番号を合わせてください。
- このルールを後から削除したい場合は、管理者 PowerShell で次を実行します。
  ```powershell
  Remove-NetFirewallRule -DisplayName "OmniCast Studio (TCP 8080)"
  ```

### 4.3 Windows マシンの LAN IP アドレスを確認する

PowerShell で以下を実行し、LAN 側アダプタの IPv4 アドレス（例：`192.168.1.50`）を控えます。

```powershell
ipconfig
```

> [!TIP]
> ルーター側で GPU マシンの IP アドレスを DHCP 固定割り当てしておくと、毎回 IP を調べ直さずにブックマークから開けるため便利です。

---

## 5. 日常の起動・終了手順（オンデマンド運用）

### 起動手順

1. **OmniVoice を先に起動する**
   - 普段の手順で `k2-fsa/OmniVoice`（Gradio Web UI）を起動し、モデル読み込み完了後 `http://127.0.0.1:8000` が応答する状態にします。
2. **OmniCast を起動する**
   - 別の PowerShell ウィンドウでリポジトリのルートディレクトリへ移動し、起動します。
   ```powershell
   cd C:\work\OmniCast
   $env:PYTHONUTF8 = "1"
   .\.venv\Scripts\omnicast.exe
   ```
   - `Uvicorn running on http://0.0.0.0:8080` と表示されれば起動完了です。

> [!IMPORTANT]
> `.env` とデフォルトの `./data` は **実行時のカレントディレクトリ基準** で読み込まれます。必ず `OmniCast` のルートディレクトリに移動してから起動してください。

### 起動用バッチファイル（任意）

毎回コマンドを打つのが手間な場合は、リポジトリ直下（またはデスクトップ等）にローカル用の起動バッチ（例：`start_omnicast.bat`）を作成するとダブルクリックで起動できます。

```bat
@echo off
cd /d "C:\work\OmniCast"
set PYTHONUTF8=1
".venv\Scripts\omnicast.exe"
pause
```

（※ `start_omnicast.bat` は Git 管理しない場合、リポジトリ外や `Private/` 配下に置くと `git status` が汚れません。）

### 動作確認

1. **GPU マシン自身から確認**: ブラウザで `http://localhost:8080` を開く。
2. **LAN 内の別マシンから確認**: ブラウザで `http://<WindowsマシンのIP>:8080` を開く。
3. **設定確認 API**: `http://<WindowsマシンのIP>:8080/api/health` を開き、`status: "ok"` と `omnivoice.url` が想定通りであることを確認する。
   - ※ `/api/health` は OmniVoice への実通信までは行わないため、初回は **Cast タブの Voice Design 試聴** または **Studio タブで 1 行 Generate** を実行し、OmniVoice 連携と `ffprobe` 計測まで通ることを確認してください。

### 終了手順

使い終わったら、以下の順で終了します。

1. OmniCast のウィンドウで `Ctrl + C`
2. OmniVoice のウィンドウで `Ctrl + C`（GPU メモリ解放）

---

## 6. 既存マシンからのデータ移行（任意）

`data/` ディレクトリは `.gitignore` 対象のため、`git clone` 直後はデフォルトの 5 キャラクター（`Alice`, `Bob`, `Carol`, `Dave`, `Narrator`）のみの状態です。

- **作成した声（Cast）だけ移行したい場合**:
  - 移行元の OmniCast UI → **🎭 Cast** タブで各キャラクターを **Export**（`.omnicast-voice.zip`）し、Windows 側の **🎭 Cast** タブで **Import** します。
- **プロジェクト・テイク音声・Cast を丸ごと移行したい場合**:
  - 双方の OmniCast を停止した状態で、移行元の `OmniCast/data/` フォルダを丸ごと Windows 側の `C:\work\OmniCast\data\` へコピーします。

---

## 7. アップデート手順

コードを更新したいときは OmniCast を停止し、以下を実行します（`.env` と `data/` は上書きされません）。

```powershell
cd C:\work\OmniCast
git pull
.\.venv\Scripts\pip.exe install .
```

---

## 8. トラブルシューティング

| 症状 | 主な原因と対処 |
| --- | --- |
| LAN 内の別マシンから `http://<IP>:8080` に接続できない | ① Windows のネットワークが「プライベート」になっているか確認。<br>② 第 4.2 節のファイアウォール許可ルールが適用されているか確認。<br>③ `ipconfig` で IP が変わっていないか確認。<br>④ `.env` の `OMNICAST_HOST` が `0.0.0.0` か確認。 |
| 生成やエクスポート時に `ffprobe failed` / `ffmpeg` が見つからないエラー | `where.exe ffmpeg` と `where.exe ffprobe` を実行して両方見つかるか確認。導入直後なら PowerShell を再起動する。 |
| Generate 時に `502` / `OmniVoice ... request failed` | ① OmniVoice が起動完了しているか確認（GPU マシン上で `http://127.0.0.1:8000` をブラウザで開けるか）。<br>② `.env` の `OMNIVOICE_URL` のポート番号が一致しているか確認。 |
| 日本語ファイル名やメタデータ付きの音声処理で文字コードエラーが出る | 起動前に `$env:PYTHONUTF8 = "1"`（コマンドプロンプトなら `set PYTHONUTF8=1`）を設定して起動する。 |
| `http://<IP>:8080` でブラウザの PWA インストールが出ない | ブラウザ仕様上、PWA インストール（Service Worker）は `localhost` または HTTPS 環境限定です。通常の Web アプリとしての利用・再生・書き出しは HTTP のまま問題なく動作します。 |
