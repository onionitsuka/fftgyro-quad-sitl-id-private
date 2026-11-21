# 荷重モデルの式を読む・編集する

[式と係数を読む](equations.md) · [編集用CSVを見る](model-terms.csv)

式の表は、配布版の `sim/appendix/model.json` から生成しています。行ごとに「係数 × 表の右列」を計算し、各成分で足し合わせると、推進による基準荷重に加える補正になります。

## 保存して編集する

配布ZIPを展開し、`run.py` のあるフォルダで実行します。Windowsでは以下の `python3` を `py -3` に置き換えてください。書き出しにはPython 3.11以上があれば十分です。

```sh
python3 run.py equations --output my-model
```

`my-model/equations.md` は式と係数の読み物、`my-model/terms.csv` はシミュレーターに渡す編集用の表です。CSVをテキストエディタや表計算ソフトで開き、次の4列を保ってUTF-8 CSVとして保存します。

| 列 | 意味 |
| --- | --- |
| `route` | `command_route` は指令と電圧から推算したRPMで学習、`measured` は実測RPMで学習 |
| `output` | 力 `Fx, Fy, Fz` またはモーメント `Mx, My, Mz` |
| `term` | 係数を掛ける項。積は `*`、整数乗は `^`、例は `mu_x*mu_z^2` |
| `coefficient` | 係数。小数点は `.` を使う |

最初は `command_route` の `Fx` にある `rotor_inplane_linear` の係数を少し変えて試せます。行の追加・削除もでき、追加できるのは `aerodynamics.py` の評価器が扱う項です。同じ経路・成分内での項名の重複や、未対応の項はエラーになります。各経路の6成分に少なくとも1行を残してください。補正をゼロにする場合は `intercept` の係数を `0` にします。

```sh
python3 run.py batch --terms my-model/terms.csv --output results/edited
python3 run.py batch --output results/edited --plot-only
python3 run.py interactive --terms my-model/terms.csv
```

編集した式を確認するには `python3 run.py equations --terms my-model/terms.csv --output my-model-edited` を使います。比較計算の `config.json` とブラウザの「計算条件」には読み込んだ係数が記録されます。CSVの編集結果は配布時の同定結果とは区別してください。

CSVで編集するのは空力補正です。推進定数やモーター係数を変えるときは `sim/appendix/model.json` のコピーを作り、`--config コピー先.json` を指定します。`--config` と `--terms` は併用できます。これらの指定はPythonの比較計算とブラウザ版で使えます。箱庭・Gazebo用ランチャーはそれぞれの配布設定を使います。

## 式の定義

座標は機体FRD（前・右・下）です。対気速度 `air = (u,v,w)` は m/s、機体角速度 `rate = (p,q,r)` とローター角速度 `Omega[i]` は rad/s、ローター角加速度は rad/s² です。ローター番号は1〜4、`w[i]` は以下で定義する重みです。

```text
Omega_rms = sqrt(mean_i(Omega[i]^2))
mu = air / (Omega_rms * R)
(pbar,qbar,rbar) = rate * L / (Omega_rms * R)
w[i] = Omega[i]^2 / Omega_rms^2
up = sum_i(roll[i]  * w[i])
uq = sum_i(pitch[i] * w[i])
ur = sum_i(s[i]     * w[i])
roll  = (-1,  1,  1, -1)
pitch = ( 1, -1,  1, -1)
s     = ( 1,  1, -1, -1)
S_F = rho * 4*pi*R^2 * (Omega_rms * R)^2
S_M = S_F * L
mu_h2 = mu_x^2 + mu_y^2
mu_total2 = mu_h2 + mu_z^2
delta_s = Omega_rms / (4000 * 2*pi/60) - 1
ur_absur = ur * abs(ur)
```

`R` はローター半径、`L` はローター腕の水平成分です。`abs_mu_x` などは絶対値。`intercept` は無次元の定数1で、項名 `1` は荷重スケール `S_F` または `S_M` を意味します。

### 基準推進荷重

```text
F_base = (0, 0, -kf * sum_i(Omega[i]^2))
h = (0, 0, -J_rotor * sum_i(s[i] * Omega[i]))
M_base = (kf*L * sum_i(roll[i]  * Omega[i]^2),
          kf*L * sum_i(pitch[i] * Omega[i]^2),
          kq    * sum_i(s[i]     * Omega[i]^2))
         - shift × F_base - d(h)/dt - rate × h
```

`shift` は推進基準重心からモデルの重心への差分をFRDに直したものです。各モーターのRPM式と時定数は[式の表](equations.md)に記載しています。RPM指令を `2*pi/60` 倍して角速度指令に変換します。指令の遅れを適用した後、ローターごとに `d(Omega)/dt = (Omega_goal - Omega)/tau` を使います。目標値が現在値以上なら上昇時定数、それ以外なら下降時定数です。

### 局所流・方向補正

- **局所流**は `mu[i] = (air + rate × r[i]) / (abs(Omega[i])*R)`。ローター位置 `r[i]` は `L * (1,1,0), L * (-1,-1,0), L * (1,-1,0), L * (-1,1,0)` から、それぞれ `shift` を引いた値です。`mu_h[i]` は `mu[i]` の水平成分の大きさです。
- **誘導流**は `C_T = kf/(rho*pi*R^4)` として、`2*nu*sqrt(mu_h2+(nu-mu_z)^2) = C_T` を満たす正の根を求めます。`inflow_delta = nu - mu_z - sqrt(C_T/2)` です。
- **Yawの方向補正**は `alpha = atan2(mu_y, mu_x)` と `beta = atan2(mu_y, abs(mu_x))` を使います。`B[j]` は `sin(beta)^2` 上の自然三次スプラインの基底で、節点は `sin([0°,30°,60°,90°])^2` です。`1 - sun_low` は低対気速度域を外すための重みで、配布モデルでは `norm(mu)=0.05` の周囲を5次式で滑らかにつなぎます。幅は `settings.sun_mu_halfwidth` です。
- **Rollへの転用**が有効なとき、実際のMx補正は±90°変換したMy補正の差の半分です。この状態でRoll補正を変えるには元になるMyの項を編集します。保存済みのMxの項を直接使うには、JSONのコピーで `roll_transfer` を `false` にします。

```text
T_plus:  (u,v,w) -> (-v,u,w), (p,q,r) -> (-q,p,r), rotor order -> (3,4,2,1)
T_minus: (u,v,w) -> (v,-u,w), (p,q,r) -> (q,-p,r), rotor order -> (4,3,1,2)
Mx_correction = (My_correction(T_plus) - My_correction(T_minus)) / 2
```

ローターの並べ替えは角速度・角加速度の両方に適用します。

式を評価するコードは [aerodynamics.py](../sim/appendix/aerodynamics.py)、基準推進荷重とRollへの転用は [simulate.py](../sim/appendix/simulate.py) にあります。
