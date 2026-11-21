# クアッドロータ研究モデル — 箱庭・Gazeboシミュレータ

**箱庭 + Unity + PX4**、または **Gazebo + PX4** で、研究の同定モデルを使って操縦するための配布用コードです。USBプロポ／コントローラーはQGroundControlで入力します。

## 導入する

**[箱庭・Gazebo版の導入手順](docs/desktop-install.md)**

このブランチを **Code → Download ZIP** で取得して展開するか、GitHubのClone URLと表示中のブランチ名を使って取得してください。以下は `desktop.py` のあるフォルダで行います。

| 使いたいもの | 導入後の起動コマンド | 実行環境 |
|---|---|---|
| 箱庭 + Unity + PX4 | `python3 desktop.py launch hakoniwa` | x86_64 Ubuntu |
| 箱庭・速度推定アシスト | `python3 desktop.py launch hakoniwa --assist aero` | 同上 |
| Gazebo + PX4 | `python3 desktop.py launch gazebo` | Ubuntu + Gazebo Harmonic |
| 補助ブラウザデモ | `python3 run.py interactive` | Mac / Windows / Linux |

**最初の3つはPythonだけでは動きません。** 上の導入手順に沿って、PX4・箱庭・UnityまたはGazeboを導入します。Mac/Windowsから使う場合のUbuntu PCでの実行方法も記載しています。ブラウザデモへ自動で切り替わることはありません。

## 含まれるもの

- 稼働済みの箱庭研究モデル、モーター応答、PX4接続、公式Avatar連携。
- 速度推定アシスト、操縦者の合図による水平速度の零点補正。
- ネイティブGazeboの機体生成と研究荷重補正プラグイン。
- ソースの固定コミット、箱庭ランタイムのチェックサム、導入・起動スクリプト。
- [補助デモと比較図の作り方](docs/browser-demo.md)。

箱庭とGazeboの力学・モーター実装の違いは [導入手順](docs/desktop-install.md) に明記しています。シミュレーションで生成したRPMを使い、実飛行ログの再生や係数の再同定は行いません。

[研究モデルの計算](desktop/hakoniwa/launcher/RESEARCH-MODEL.md) / [速度推定アシスト](desktop/hakoniwa/launcher/VELOCITY-ASSIST.md)

解析・同定・実験収録のソースは [FFTGYRO研究コード](https://github.com/onionitsuka/fftgyro-quadrotor-identification) を参照してください。
