# 卒論付録Cのクアッドロータシミュレータ

卒論「三軸姿勢試験台を用いたクアッドロータの推進・姿勢応答モデルの同定」で得た荷重モデルを試せます。保存済みの係数を同梱しているので、実験ログを用意する必要はありません。

## やりたいことから選ぶ

| やりたいこと | 必要な環境 | 手順 |
| --- | --- | --- |
| **まず飛ばして試す** | Mac・Windows・Linux、Python 3.11以上、キーボード | [ブラウザで操縦する](docs/browser-demo.md) |
| **既存モデルと同定モデルを比較する** | Mac・Windows・Linux、Python 3.11以上 | [付録Cの比較図を作る](docs/browser-demo.md#付録cの比較図を作る) |
| **付録のPX4閉ループで操縦する** | x86_64 Ubuntu、QGroundControl、箱庭＋UnityまたはGazebo | [箱庭・Gazebo版を導入する](docs/desktop-install.md) |

## まず試す

1. [ZIPをダウンロード](https://github.com/onionitsuka/fftgyro-quad-sitl-id-private/archive/refs/heads/thesis-appendix-simulator.zip)して展開します。GitHubへのログインは不要です。
2. [Python 3.11以上](https://www.python.org/downloads/)を用意し、展開した `run.py` のあるフォルダでターミナルを開きます。
3. 下のコマンドを実行し、ブラウザで **開始** を押します。初回は依存パッケージの取得にネット接続が必要です。

| OS | 起動コマンド |
| --- | --- |
| macOS / Linux | `python3 run.py interactive` |
| Windows（PowerShell） | `py -3 run.py interactive` |

**W/S** で前後、**A/D** で左右、**Q/E** で方位、**↑/↓** で昇降します。地面に達したり計算が止まったりしたら、画面の **ホバーからやり直す** を押してください。終了するにはターミナルで **Ctrl+C** を押します。

ブラウザ操縦と比較図は、付録C「補助的な比較計算」に対応します。共通の簡易制御器で同定モデルと回転数二乗モデルを比較できます。

## 論文と照らし合わせる

- **箱庭・Gazebo版**は実際のPX4制御器を含みます。箱庭はモーター応答と研究荷重を箱庭の力学で積分し、Unityで表示します。Gazeboはネイティブのモーター・センサ・力学を使い、研究荷重を外力・モーメントとして加えます。[両方式の構成と操作手順](docs/desktop-install.md)
- **回転数**はシミュレーションの中で生成します。`measured` は実測RPMで学習した係数を選ぶ設定です。[係数・計算・出力の説明](sim/appendix/README.md)
- **解析・同定のソース**から手法を確認する場合は、別の研究コードリポジトリを参照してください。[FFTGYRO研究コード](https://github.com/onionitsuka/fftgyro-quadrotor-identification)

起動できないときは、Pythonの導入、ブラウザの接続、コントローラーの認識を順に確認できます。[困ったとき](docs/troubleshooting.md)
