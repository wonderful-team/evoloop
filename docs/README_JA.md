<p align="center">
  <img src="https://www.evoloop.cn/assets/images/WoodenRobot.png" alt="EvoLoop" width="120" />
</p>
<p align="center"><b>EvoLoop Agent - 自值守エージェント、タスク編成可能、夜勤が得意</b></p>

<p align="center">
  <img src="https://img.shields.io/github/stars/wonderful-team/evoloop" alt="GitHub stars" />
  <img src="https://img.shields.io/github/v/release/wonderful-team/evoloop" alt="GitHub release" />
  <img src="https://img.shields.io/badge/license-MIT-green.svg" alt="License: MIT" />
  <a href="https://github.com/wonderful-team/evoloop/wiki"><img src="https://img.shields.io/badge/Docs-Wiki-blue" alt="Docs" /></a>
</p>

<p align="center">
  <a href="https://github.com/wonderful-team/evoloop/releases">Releases</a> &nbsp;·&nbsp;
  <a href="https://www.evoloop.cn">Website</a> &nbsp;·&nbsp;
  <a href="https://www.evoloop.cn/agent_multi">Try Online</a> &nbsp;·&nbsp;
  <a href="https://github.com/wonderful-team/evoloop/issues">Issues</a>
</p>

<p align="center">
  <a href="README_EN.md">English</a> | <a href="README_CN.md">中文</a> | <a href="README_JA.md">日本語</a> | <a href="README_KO.md">한국어</a>
</p>

---

EvoLoop は **タスク編成可能な自值守エージェント** です。エージェント内部に三権コミュニケーション機構 — **意思決定者、実行者、審査監察者** — を備え、タスクの項目一つひとつを確実にやり遂げさせます。

Agent を使っていてこんな経験はありませんか：長丁場タスクの計画は完璧に見えるのに、SKILL で縛っても実際の実行は**不完全、やり残しがある、甚至方向が逸れる** — 何度もチェックして、何度もやり取りして修正するしかない？

EvoLoop はまさにこの問題を解決するために、新たに **值守式タスクシステム** を設計しました：タスクは時刻になると自動実行、各ステップの進捗をリアルタイムに記録。完了後は **審査監察者** があなたの立場から検証します — 実行者の「できました」は通用しない、不完全なら差し戻し。資金と不可逆な操作は **意思決定者**（あなた）が承認。あなたはタスクを計画し、結果を検収するだけ。

Web・デスクトップ・モバイルの 3 端末をカバーし、ウェイクワード駆動の自然な音声会話に対応。

🌐 公式サイト [evoloop.cn](https://evoloop.cn) · 💻 [GitHub](https://github.com/wonderful-team/evoloop)

---

## 🎬 製品デモ

<table>
  <tr>
    <td valign="top">
      <img src="images/evoloop-ui.png" alt="EvoLoop Desktop" height="500" />
      <p align="center"><em>Desktop</em></p>
    </td>
    <td valign="top">
      <img src="images/evoloop-mobile.jpg" alt="EvoLoop Mobile" height="500" />
      <p align="center"><em>Mobile</em></p>
    </td>
  </tr>
<tr>
<td colspan="2" align="center">
<img src="images/evoloop-duty.png" alt="EvoLoop Duty" height="500" />
<p align="center"><em>Duty</em></p>

<img src="images/evoloop-duty-2.png" alt="EvoLoop Duty" height="500" />
<p align="center"><em>Duty HITL</em></p>
</td>
</tr>
</table>

**EvoLoop 全機能デモ**

https://www.evoloop.cn/assets/video/demo.mp4

**值守タスクシステム デモ 1**

https://www.evoloop.cn/assets/video/duty1.webm

**值守タスクシステム デモ 2**

https://www.evoloop.cn/assets/video/duty2.webm

---

## 🏗 システムアーキテクチャ

<p><img src="images/arch.png" alt="EvoLoop Architecture" /></p>

| 層 | 構成 |
|------|------|
| クライアント | Web（React + Vite）、デスクトップ（Tauri + Rust 音声パイプライン）、モバイル（React Native、リモート承認/検収対応） |
| サービス | FastAPI：REST + SSE + 音声 WebSocket チャネル |
| エンジン | [OpenHands](https://github.com/All-Hands-AI/OpenHands) SDK ベースの Agent エンジン：計画 → ツール実行 → 構造化セルフチェック → 迷ったら差し控えて質問 |
| ルーティング | 指令振り分け：定型コマンドは即実行、不確実なものだけ Agent へ |
| 值守 | タスクキュー + Supervisor スケジューリング：期日実行、クラッシュ収束、サーキットブレーカー |
| 拡張 | MCP ツールサービス、能力パック（SOP）、ランタイムツール作成、マクロエンジン（決定論的リプレイ + 自己修復） |
| データ | デスクトップ内蔵（SQLite + LanceDB、データは端末外に出ない）/ SaaS サーバ（PostgreSQL + Redis） |

---

## ⏱ 值守タスクシステム (Autonomous Duty)

### どんな問題を解決するか

LLM は要件を **不完全に実施したり、部分的に逸れたり** します — 長丁場タスクの途中でコンテキストがノイズに溺れて腐敗し、モデルが疲弊して早期離脱、完了を偽報、正面回答の回避、成果物が目標から逸脱。あなたは **何度もチェックし、何度もやり取りして** 修正するしかなく、実行の詳細に駆り込まされる。

値守タスクシステムは、まさにこの修正コストを消すために設計されました：タスク作成時にシナリオ・目標・検収基準を先に明確化。実行状態はすべて永続化、中断後は続きから再開。完了後は結果を **あなたの名義で、元の依頼会話に差し戻し**、当初あなたの要件を理解した Agent があなたの立場で検証します — 実行者の口から出る「完了」は通用しない、2 回の差し戻しで不承認なら人工仲裁へエスカレーション。

### 目標

Agent にビジネスを長期的に安定して回させる：要件は一度伝えるだけで、修正は仕組みに任せる。人が登場するのは承認・検収・仲裁の 3 瞬間だけ。

### タスク実行フロー

<p><img src="images/duty-workflow.png" alt="Duty Workflow" height="500" /></p>

### 適したシナリオ

- **EC / 小売運用托管**：選品リサーチ → 価格設定 → 出品 → 日次巡回（欠品・悪評価・異常注文）— 最初の試験シナリオは「商城の接管」
- **コンテンツ & グロースパイプライン**：企画 → 執筆 → 素材制作 → マルチプラットフォーム投稿 → 投下振り返り、各ステップが痕跡化・検収対象
- **データ & 巡回ボット**：経営日報、在庫 / 資金 / 指標の定期巡回、異常は即アラート・即提案
- **サードパーティイベントの継続応答**：注文・チケット・審査メッセージを自動キューイング、全工程監査可能
- **企業バックオフィス SOP**：承認補助、消し込み、棚卸しなど、繰り返し可能で検収可能なフロー
- **R&D プロジェクト管家**：コードベース巡回、依存セキュリティチェック、バックアップ検証、バックログ整理
- **カスタマーサービス受付**：企業微信 / 微信カスタマーサービス巡回自動応答、資金関連は人工へエスカレーション
- **人不盯盤**：7×24 值守ループ、人が登場するのは承認・検収・仲裁の 3 瞬間だけ

接管対象を変更（商城 → CRM → サプライチェーン → コンテンツサイト）する場合は、能力パックとタスクデータを入れ替えるだけで、スケジューリング・実行層はゼロ変更。

### ワークベンチ

無限キャンバスをメインビューに：異種成果物カード + 依存ライン、視覚フォーカスが Agent の現在ノードを自動追従。承認 / 検収 / 審査カードはノード内に埋め込み。いつでも 3 つの問いに答えられます — **Agent は今何をしているか、これまで何をしたか、次に何をするか**。

---

## 🌟 主な機能

| 機能 | 説明 |
|---|---|
| **長時間実行** | 単一タスク 300 ステップ以上の連続実行、数時間の安定稼働、自動エラー復旧 |
| **クロスデバイス A2A 協調** | デバイス間でエージェントが発見・委任・結果返却を非同期に実行 |
| **値守実行** | タスクは期日になると自動キューイング・実行。各ステップの進捗をリアルタイム記録、完了時には検証可能な証跡を添付。実行者の「できた」は通用しない — 結果はあなたの名義で依頼元の会話に戻され、審査監察者が「本当に正しくやったか」を検証。資金と不可逆操作は必ず人の承認を待つ |
| **模倣学習** | あなたが 1 回デモすれば 1 セット習得 — マウス操作の軌跡を記録し、画面録画はフレームごとに理解して、再利用可能なスキルや「マクロ」に蒸留。以後同じ作業は機械的にリプレイし計算資源を消費しない。環境変化時は自動で AI にフォールバック。AI 自作のフローは実測テスト合格後のみ稼働許可 |
| **随時呼び出し** | 音声・Web・企業微信 / 微信カスタマーサービス・モバイル — どの入口も平等に扱う。定型コマンドは LLM を起こさず秒で処理、曖昧・複雑なものだけ AI がじっくり思考 |
| **音声対話** | 「你好Evo」と呼べば会話開始、話しかけの割り込みや音声入力の代筆も可能。音声は端末外に出ない |
| **あなたの代わりに手を動かす** | 既に持っているデバイスで作業 — ブラウザの Web ページ、デスクトップアプリ、Android / iOS / HarmonyOS スマホ。PC の前にいなくてもスマホで承認・検収 |
| **助けを求められる（A2A）** | このマシンの Agent は、別デバイスの Agent に仕事を委託できる — 派遣中はメインフローが自動待機し、結果が戻れば即座に再開。委託の全過程が UI 上でリアルタイム可視化 |
| **安全装置** | 迷ったら止まって人に聞く、決して答えを捏造しない。危険操作は権限ゲートで封鎖、機密は出力に現れない、空回りループは即座に遮断 |
| **エコシステム接続** | 外部ツールは MCP プロトコルでいつでも接続 / 切離。業務知識は能力パックとして必要に応じ組み込み — 今日は商城を接管、明日は別のシステムへ、コアコードは無変更 |

---

## 🚀 インストールとデプロイ

EvoLoop には 3 つのデプロイ形態があります。用途に合わせて選択してください。

| モード | シナリオ | スタック | 設定ファイル |
|---|---|---|---|
| **デスクトップ内蔵** | 個人 PC・ローカル利用 | SQLite + LanceDB + Huey | `.env.prod.desktop` |
| **Web 単一ユーザー** | 個人サーバー | SQLite + LanceDB + Huey | `.env.prod.web.single` |
| **Web マルチユーザー** | チーム / 企業本番 | PostgreSQL + Redis + Meilisearch + Neo4j + Celery | `.env.prod.web.multi` |

### デスクトップ内蔵モード（個人 PC、外部依存ゼロ）

バックエンドに SQLite + LanceDB + Huey を内蔵。デスクトップアプリと共に単機で起動し、データは端末外に出ません：

```bash
# リポジトリをクローン
git clone https://github.com/wonderful-team/evoloop.git
cd evoloop

# バックエンド：依存インストール + ワンコマンド起動
cd backend
./bin/evo install
cp .env.prod.desktop .env      # LLM API Key を記入
./bin/evo start                # API + Worker を同時起動（evo stop で停止）

# デスクトップ（Tauri、音声ウェイク内蔵。バックエンドは sidecar として同梱起動）
cd frontend
npm install
npm run tauri dev
```

### Web 単一ユーザーモード（個人サーバー）

```bash
cd backend
cp .env.prod.web.single .env
./bin/evo start
```

### Web マルチユーザーモード（チーム / 企業本番）

```bash
cd backend
cp .env.prod.web.multi .env
# PostgreSQL / Redis / Meilisearch / Neo4j を設定、または ./bin/evo install full
./bin/evo start
```

`evo` コマンド早見表：`evo start / stop / status / logs` でサービス管理、`evo test` でテスト、`evo check` でコード検査 — 一覧は `./bin/evo help`。

---

## 📦 ビルドとリリース

```bash
# デスクトップ パッケージング
./deploy/build.sh macos-arm64 --env-file=.env.prod.desktop
./deploy/build.sh macos-x86_64 --env-file=.env.prod.desktop

# モバイル パッケージング（Android APK / AAB、iOS、HarmonyOS HAP）
./deploy/build.sh android --env-file=.env.prod.desktop   # APK。Google Play には --aab
./deploy/build.sh ios --env-file=.env.prod.desktop
./deploy/build.sh harmony --env-file=.env.prod.desktop
./deploy/build.sh mobile --env-file=.env.prod.desktop    # 3 プラットフォーム一括ビルド

# Web 静的アセットビルド
./deploy/build.sh web --env-file=.env.prod.web.multi

# モデルダウンロード
./deploy/download_models.sh --models nomic-embed,paraformer-zh
```

---

## 🤝 連携と共創

あらゆる **Agent カスタマイズ案件** をお引き受けします — EvoLoop であなたのビジネス向けの值守 Agent（EC 運用托管、カスタマーサービス受付、巡回ボットなど）をカスタム構築し、試験から納品までフルサポート。お気軽にご連絡ください：

**同時に、本プロジェクトへの参加と共に建设を楽しむ仲間も大歓迎です** — 要件提起、バグ報告、コード貢献、活用シェア、どれもこのエコシステムの建設者です。

- **公式サイト**：[evoloop.cn](https://evoloop.cn)
- **GitHub**：[wonderful-team/evoloop](https://github.com/wonderful-team/evoloop)
- **Issues**：[GitHub Issues](https://github.com/wonderful-team/evoloop/issues)
- **メール**：[preterchan@gmail.com](mailto:preterchan@gmail.com)
- **微信**：QR コードでご連絡を

<p align="center">
  <img src="images/wechat.png" alt="EvoLoop WeChat" width="200" />
</p>

---

<p align="center">
  <b>Built with ❤️ by EvoLoop Team</b>
</p>
