# SID Synth Desktop 初期実装の確認

2026-11-08開始、2026-11-09 JST最終確認。Desktop **0.0.1**。

## 含めたもの

- 採用SID icon、他Synthと揃えたMenu／Pin、native file保存、Web Audio／Native device出力。
- Web版の6581／8580 Preview、複合波形、CH別編集／Round robin、Retrigger／Legato、SID import／Live／Pause／Resume、voice／channel setup保存。
- JS／CSSのmodule構造と可読性を維持した`dist/`、元browser source ZIP、全4 native source kit・5 WASMと対応receipt／license。
- 改造した`dist/`を記録するlocal-changes機能、Windows checkoutのbyte保持、macOS／Windows／Linux CI、ローカル署名用deploy script。

取込Web snapshotは`20261108-desktop.1`。ZIP 2,973,476 bytes、SHA-256
`cd35b6ae6e5447a26cef174bc63101066e00c6454cf97a5aa5940c66b3687dee`。
全265ファイルをZIPのbytesのまま取り込み、36可読module／198原入力、native kitの13／14／29／99 compiled inputs、license／toolchain noticesを検証した。
2つのmacOS app build後も`python3 scripts/import_release.py --check`が成功した。

## 音声の接続

SIDの鍵盤と曲previewは別のAudioContextを使う。親Web版に、localなTauri top-level windowでだけ公開する音声bridgeを追加した。
Native adapterは新しい鍵盤のNote On／曲preview開始より前に最終Master busの接続を完了する。明示的な出力変更は鍵盤とpreviewを停止してPitchを戻し、音色・選択fileを保持する。
通常のpreview終了ではNativeの選択を維持して次のcontextへ接続し、実際のdevice障害ではWeb Audioへ戻す。
音源処理は元のWASM／AudioWorkletであり、RustへSID DSPを移植したものではない。

親側変更は`docs/synth-sid/synth.js`、入口のcache revision、controller testとTODO。childの`dist/`へ直接patchは加えていない。

## 自動検証

- Python **25件**成功。4source kit／receipt／license、ZIP安全性、改造記録とrollback、Windows checkoutを含む。
- Node **47件**成功（全suite45件と、後から追加したbridge guardの2件）。Native transport、source切り替え、stale session、cancel／failure、Refresh中の接続、binary save、Pinを含む。
- Rust **30件**成功。実device用2件は通常ignore。format check成功。
- parent Synth **183件**成功。route完了前に発音しないこと、Stopで遅延routeを無効化すること、preview graph選択と通常Webでbridgeを公開しないことを含む。
- desktopのChromium／WebKitが各9検証群成功。実SID WASM／AudioWorklet、6581／8580、Legato／個別CH、設定保存、Native PCM、別contextの曲、Pause／Resume、遅延接続中Stop、device障害復帰を確認。390pxの横方向overflowは両方0。
- parentの通常Web版もChromium／WebKit各20項目成功。通常の発音、複合波形、filter、modulation、保存、Legato、起動取消と失敗復帰を維持した。
- transport stress **21 scenario**成功。9packet credits／開始4packets、異なるclock、遅延、drift、停止後の古いPCMを扱う。IPCとdevice消費を模した測定であり、実deviceの長時間試験ではない。

実装レビューでRefreshが進行中のNative接続を無効化する競合を見つけ、読み取り専用Refreshではrouteを無効化しないよう修正し、回帰testを追加した。
最初のbrowser実行には、Worklet生成前のstate readと、古いWeb Audioエラー表示を出力変更完了と誤判定する待機不足があった。起動・出力変更・file loadの完了待ちを修正し、両engineを再実行した。
ブラウザーのphysical outputはmuteし、新規作成SID fixtureを使った。ゲーム曲／ROM／PCMを追加していない。

記録:

- [desktop browser](desktop_browser_20261108.json)
- [transport stress](audio_transport_20261108.json)
- [desktop入力hash](desktop_inputs_20261108.json)
- [build／実アプリ確認](build_20261108.json)
- 詳細ログ: ignoredの`artifacts/`、parentの`build/validation/sid-desktop-bridge-*`。

## macOS app

次の両方でapp buildが成功した。今回のbuildは`--no-sign`でDeveloper ID署名／公証を行っていない。

```sh
npm run build -- --target aarch64-apple-darwin --bundles app --no-sign -- --locked
npm run build -- --target x86_64-apple-darwin --bundles app --no-sign -- --locked
```

出力は`src-tauri/target/TARGET/release/bundle/macos/Tetorica SID Synth.app`。
Apple Silicon appを起動し、実`tauri://localhost`のSID UI、MenuのImport／Export、Pin On→Offを確認した。
音を弾かずにNative出力を実deviceの44,100 Hzへ接続し、Web Audioへ戻した。appはWeb Audio・Pin Off・保持鍵なしで残した。
Intel appはarchitectureを検査し、起動はしていない。

## 残す確認と次の手順

- [ ] 実アプリで自分のSID・preset／setupを読み込み、両model・Legato・filterを実聴する。
- [ ] 実native file dialogの保存・取消、実device選択を操作する。
- [ ] Pin／background／長時間、device変更／高負荷での音切れやmemoryを確認する。
- [ ] commit／push後にGitHub Actionsの全OS buildとinstallerを確認する。
- [ ] ローカル`deploy_mac.sh`で署名／公証し、配布installerからの起動を確認する。

CIはmacOS ARM／Intel、Windows x64、Linux x64／ARM64を設定した。mainでartifact、v tagでdraft releaseを作る。ホストされたCIは未実行。
commit／push／tag／Release公開は実行していない。parentとchild両方に未commitの変更がある。
