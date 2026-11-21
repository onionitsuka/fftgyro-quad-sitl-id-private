# 補助ブラウザ版のコード構成と検証

箱庭・Gazebo版は [デスクトップ導入手順](desktop-install.md) を参照してください。以下は補助ブラウザ版の説明です。

| 場所 | 役割 |
|---|---|
| `run.py` | OS共通の環境作成・依存導入・実行入口（標準ライブラリのみ） |
| `start.command` / `start.bat` / `start.sh` | 各OSから `run.py` を起動 |
| `sim/appendix/simulate.py` | バッチ計算・力学・制御・保存・描画 |
| `sim/appendix/aerodynamics.py` | 採用項と荷重の評価 |
| `sim/appendix/model.json` | 同定係数・機体諸元・モーター・制御設定 |
| `sim/appendix/interactive.py` | 操縦用制御・状態・ローカルHTTP API |
| `sim/appendix/interactive.html` | 画面の構造 |
| `sim/appendix/assets/` | 画面スタイルとJavaScript |
| `sim/appendix/tests/` | 力学・操縦制御の回帰テスト |
| `tests/` | 起動入口・実HTTP通信の統合テスト |

今回の整理では `simulate.py`、`aerodynamics.py`、`model.json` の内容は変更していません。式・係数と制御器の変更は、導入や画面の変更と別に検証してください。

## 自動確認

```sh
python3 run.py setup --dev
python3 run.py test -q
```

## 再現性

ブランチは最新版への入口です。計算結果には係数・設定とコードのハッシュを保存します。同じコードへ戻りたい場合は、利用時の `git rev-parse HEAD` も実験記録に残してください。生の実験データや実行結果をGitへ追加しないでください。
