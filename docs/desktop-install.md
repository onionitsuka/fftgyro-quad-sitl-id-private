# 箱庭・Gazebo版の導入

卒論の付録Cで説明したPX4閉ループを、箱庭またはGazeboで試す手順です。両方式ともQGroundControlでUSBプロポを使えます。

| 使う方式 | Ubuntuで用意するもの | 向いている用途 |
| --- | --- | --- |
| 箱庭 + Unity + PX4 | Unity Editor、QGroundControl | Unityでの操縦、水平速度推定アシスト |
| Gazebo + PX4 | Gazebo Harmonic、QGroundControl | ネイティブGazeboでのモデル比較 |

**実行環境は x86_64 Ubuntu 24.04 です。** Mac・WindowsのPCから使う場合は、Ubuntu PCで実行し、必要に応じてリモートデスクトップで表示します。プロポは実行先のUbuntu PCに接続します。手元のMac・Windowsで手早く試す場合は、[Pythonのブラウザ版](browser-demo.md)を使えます。

[ZIPをダウンロード](https://github.com/onionitsuka/fftgyro-quad-sitl-id-private/archive/refs/heads/thesis-appendix-simulator.zip)して展開し、`desktop.py` のあるフォルダで以下のコマンドを実行します。

## 1. 共通の準備

- Python 3.12（Ubuntu 24.04の標準版）、venv/pip、Git、C/C++コンパイラ、CMake、Ninja。
- QGroundControlを[公式手順](https://docs.qgroundcontrol.com/master/en/qgc-user-guide/getting_started/download_and_install.html)で導入する。
- PX4は `desktop/sources.json` のバックエンド別コミットを使う。外部ソースは自分のPCへ取得し、このリポジトリには同梱しない。

Ubuntuの基本パッケージ例：

```sh
sudo apt update
sudo apt install git build-essential cmake ninja-build python3-venv python3-pip unzip curl libglfw3
```

PX4の[Ubuntu開発環境](https://docs.px4.io/main/en/dev_setup/dev_env_linux_ubuntu.html)に従ってOS依存を導入してください。`desktop.py setup` はsudoやライセンス同意を代行しません。PX4のビルド依存が既にそろっている場合は、以下のsetupが固定コミットの取得・ビルドも行います。既存のビルド済みPX4を使う場合は `--px4-root /path/to/PX4-Autopilot` を付けます。コミットが異なるものは受け付けません。

## 2. 箱庭 + Unity + PX4

### 初回導入

Unity Hubから **Unity Editor 6000.3.10f1（Linux Build Supportを含む）** を導入し、利用者のアカウントでライセンス認証を完了します。規約同意も利用者が行います。

```sh
python3 desktop.py setup hakoniwa --unity-editor "$HOME/Unity/Hub/Editor/6000.3.10f1/Editor/Unity"
python3 desktop.py doctor hakoniwa
python3 desktop.py launch hakoniwa
```

setupは箱庭core・drone-core・公式Unity Avatarを固定コミットから取得し、v5.0.0ランタイムのSHA256を照合して導入します。箱庭の共有ライブラリ・研究モデル用の力学ブリッジ・Unity Avatarをビルドします。保存先は `.desktop-runtime/hakoniwa/` です。数GB以上のダウンロードとUnityビルドが必要です。

UnityのPackage Manager認証やEditorエラーが出た場合は、同フォルダの `hakoniwa-unity-drone/simulation` をEditorで開いて問題を確認し、setupを再実行します。ビルドログは `avatar-build.log` です。

### 操縦

QGroundControlを開き、USBプロポを選んで校正し、ジョイスティック入力を有効にします。接続・Ready表示を確認して、利用者がArmし、Positionモードで操縦します。自動Armはしません。

```sh
# 同じ機体・モーター・PX4設定の回転数二乗モデル
python3 desktop.py launch hakoniwa --model existing

# 研究モデルによる水平速度推定アシスト
python3 desktop.py launch hakoniwa --assist aero

# IMU積分のみの比較用アシスト
python3 desktop.py launch hakoniwa --assist imu
```

終了は起動端末でCtrl+C。Disconnectedのままなら終了後に同じlaunchを再実行します。QGCの校正は保持され、飛行状態は初期状態に戻ります。セッション記録は `.desktop-runtime/hakoniwa/sessions/` に残ります。

アシストではPosition要求をOffboardへ切り替えます。操縦者が静止を確認して押す速度零点ボタンなど、詳細は [速度推定アシスト](../desktop/hakoniwa/launcher/VELOCITY-ASSIST.md) と [研究モデルの計算](../desktop/hakoniwa/launcher/RESEARCH-MODEL.md) を参照してください。機種依存の軸・ボタン割当は利用者の機器で確認します。

## 3. Gazebo + PX4

[Gazebo Harmonicの公式Ubuntu導入手順](https://gazebosim.org/docs/harmonic/install_ubuntu/)に従い、Gazebo 8とPythonバインディングを導入します。UbuntuのGazebo配布元を設定した環境では、Python側に `python3-gz-sim8`、`python3-gz-math7` が必要です。PX4側は[公式Gazebo手順](https://docs.px4.io/main/en/sim_gazebo_gz/)も参照します。

```sh
python3 desktop.py setup gazebo
python3 desktop.py doctor gazebo
python3 desktop.py launch gazebo
```

Gazeboの機体表示とPX4を起動します。QGCでプロポを校正し、接続後に利用者がArmして操縦します。比較用には `--model existing` を付けます。終了はCtrl+Cです。他のPX4/Gazeboセッションとは同時起動せず、順番に比較してください。

ネイティブGazeboのX500を基に、質量・慣性・推力係数と水平腕を研究設定に合わせます。同定時の保存係数から求めた6軸補正を外力・モーメントとして加えます。二重計上を避けるため、ネイティブの水平抗力・ローリングモーメントを差し引きます。既存モデル側も水平抗力を差し引き、回転数二乗の推進を比較基準にします。

**箱庭版とモーターモデルは同一ではありません。** Gazebo版はネイティブの回転ジョイント、モーター応答、センサ、接触・剛体積分を残します。箱庭版の指令・電圧→RPMモデルをGazeboへ適用したものとは扱いません。また、同梱Gazeboシーンは無風です。Gazebo版の結果は卒論の既存図表を再計算した結果ではありません。

ログ、使用係数のハッシュ、実際に適用した空力補正は `.desktop-runtime/gazebo/sessions/` に保存します。`plugin_ready.json` がない場合や `plugin_failure.json` がある場合は正常な研究モデル計算と扱いません。

## 4. 構成と確認範囲

- 箱庭：`プロポ → QGC → PX4 → モーター応答・研究荷重 → 箱庭剛体力学 → 模擬センサ → PX4`。UnityはAvatar表示。
- Gazebo：`プロポ → QGC → PX4 → Gazeboモーター・研究荷重補正 → Gazebo剛体力学・センサ → PX4`。
- 学習係数は同梱JSONを使い、導入時に再fitしません。
- OS用の起動ファイルは箱庭版の入口です。補助ブラウザ版は明示的に `python3 run.py interactive` で起動します。
