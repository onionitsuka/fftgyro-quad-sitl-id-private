# Quadrotor Lab — 卒論付録Cシミュレータ

風洞試験から同定した機体モデルを、自分で操縦し、回転数二乗モデルと比較するためのローカルシミュレータです。
**Mac・Windows・Linux用。Python 3.11以上が必要です。Unity・PX4・実験ログは不要です。**

## 1. 取得する

[ZIPをダウンロード](https://github.com/onionitsuka/fftgyro-quad-sitl-id-private/archive/refs/heads/thesis-appendix-simulator.zip)して展開します。
以下のコマンドは、展開した `run.py` のあるフォルダで実行してください。

## 2. 補助デモを起動する

[Python公式サイト](https://www.python.org/downloads/)からPythonを導入してください。初回起動は依存パッケージの取得にネット接続が必要です。以後はローカルで動きます。

`python3 run.py interactive`（Windowsは `py -3 run.py interactive`）で起動します。OS用startファイルは箱庭版の入口です。

初回はプロジェクト内に `.venv` を作り、必要なパッケージを導入します。システムのPython環境は変更しません。ブラウザが開かなければ **http://127.0.0.1:8765** を開いてください。起動したターミナルは開いたままにします。終了はターミナルで **Ctrl+C** です。

## 3. 飛ばす・保存する

最初は「速度・高度保持」で **開始** を押します。2 mのホバーから始まります。

- **W/S**：前後、**A/D**：左右、**Q/E**：方位、**↑/↓**：上昇・下降。
- **P**：一時停止・再開、**R**：ホバーからやり直す。
- キーを離すと減速し、高度と方位を保持します。別のタブへ移ると一時停止します。
- **CSV保存**で飛行の時系列、**計算条件**で係数・設定・コードのハッシュを保存します。
- モデルを変更すると新しいホバーから始まります。残したい飛行は変更前に保存してください。
- 通信が切れたらターミナルを確認して **再接続**。地面到達・計算限界で停止したら **ホバーからやり直す**。

PSコントローラー／USBプロポは接続後にボタンを押し、「コントローラーで操縦する」を選びます。軸割り当て・反転は画面で設定します。
**Mode 2の推力中央はホバー相当です。下端はモーター停止ではなく、位置・高度保持も入りません。** 実機のアーミング・離着陸手順は再現していません。

## 付録Cの比較図を作る

論文の補助計算と同じく、共通の簡易制御器で荷重モデルを切り替え、速度・高度・Pitch・前方距離を比較します。

```sh
python3 run.py batch --output results/example
python3 run.py batch --output results/example --plot-only
```

Windows（PowerShell）では次の2行を実行します。

```powershell
py -3 run.py batch --output results/example
py -3 run.py batch --output results/example --plot-only
```

`results/example/comparison.png`（PDFも生成）で速度・高度・Pitch・前方距離を比較できます。`summary.json` の両モデルが `COMPLETED`、終了時刻が14.5秒なら既定例は完了です。途中終了した場合は同ファイルの理由を確認してください。`existing.csv` と `identified.csv` に時系列、`config.json` に使用した係数と設定を保存します。
再計算は `results/example2` など別の出力先を指定してください。既存結果は上書きしません。`python3 run.py batch` だけなら日時付きフォルダを自動作成します。

```sh
python3 run.py batch --target 5 --output results/forward5
python3 run.py batch --route measured --output results/measured
```

`--route measured` は**実測RPMで学習した係数**を選びます。シミュレーション内のRPMは、どちらの経路でも指令から生成します。

## 困ったとき・開発

- [導入と起動のトラブル対応](troubleshooting.md)
- [力学・制御・係数・出力の説明](../sim/appendix/README.md)
- [コードの構成と検証](development.md)

```sh
python3 run.py doctor
python3 run.py setup --dev
python3 run.py test -q
```

このプログラムは論文モデルの動作例です。簡易制御器を用いており、PX4・箱庭のシミュレータや実飛行による性能検証とは異なります。
