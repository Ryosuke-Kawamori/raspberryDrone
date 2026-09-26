# BMP581 / VL53L4CD 高度維持（実験段階）

Meteor85 + Raspberry Pi Zero W / Raspberry Pi OS CPython 3.11以上を対象とします。
FCは姿勢を安定化し、PiはRC Throttleだけを補正します。自動離着陸・水平位置保持・画像認識はありません。
**ゲイン・ホバー値・センサー範囲・故障時動作は実機未検証です。同梱設定ではliveを起動できません。**
1.5m維持は対象外です。

## 構成と互換性

既存Pi ZeroのUDP→UART/CRSF 50Hz基盤を拡張しました。Picoファームウェアと共有RC形式は変更していません。
既定起動はUARTを開かないdry-runへ変更しました。従来のUART手動ブリッジは`--mode manual`です。

|層|ファイル|責務|
|---|---|---|
|取得|sensors.py / alt_runtime.py|センサーごとの子プロセス、data-ready、bounded queue|
|推定|estimation.py|ToF品質・相対高度・速度、DISARM時の気圧基準|
|制御|alt_control.py|PD/PID、ON/OFF受渡し、状態管理|
|通信|udp_receiver.py|旧RC互換、timeout、再ARM制約、live用token/seq|
|送信|main.py / serial_transport.py|50Hz CRSF、最終出力|
|保存|alt_runtime.py|bounded queue＋ログスレッド、欠落数と保存エラー|
|非駆動検証|experiments.py|再生とノイズ・遅延・飽和付き模擬機体|

I2Cの初期化も読取も送信ループで実行しません。I2Cが固着しても送信側は鮮度とUDP timeoutを確認します。
ログqueue満杯では保存を落とし、制御を待たせません。Python/Linuxはハードリアルタイムではありません。
UART書込timeoutは20ms。遅れたフレームを一斉送信せず、loop遅延を記録します。

## 採用ドライバーと配線確認

2026-09-25に公式API・ソースと配布バージョンを確認しました。Pi実機での動作は未確認です。

- [SparkFun Qwiic BMP581 2.0.0](https://github.com/sparkfun/qwiic_bmp581_py/blob/master/qwiic_bmp581.py)：
  `begin`, `set_odr_frequency`, `int_source_select`, `get_interrupt_status`, `get_sensor_data`を使用。
  DRDYの読取・クリアを経た新規変換だけを公開します。気圧はPa。
  Qwiic Linux backendの自動bus選択を避け、明示busのSMBus adapterを渡します。
  2.0.0のunsigned温度デコードへ24bit signed Q16補正を施しています。
  [Boschデータシート](https://cdn.sparkfun.com/assets/9/a/4/4/f/BMP581-Datasheet.pdf)も参照してください。
- [Adafruit VL53L4CD 1.3.6](https://github.com/adafruit/Adafruit_CircuitPython_VL53L4CD/blob/main/adafruit_vl53l4cd.py)：
  `data_ready`, `range_status == 0`, `distance`（cm→m）, `clear_interrupt`を使用。
  [ExtendedI2C](https://docs.circuitpython.org/projects/extended_bus/en/latest/api.html)でbus番号を指定します。
  通常0x29。別アドレス指定は既に設定済みの機器向けです。XSHUTや電源投入時の再割当ては実装していません。

購入基板メーカーは不明です。裸のIC定格とブレークアウトのVIN定格は別です。
**電源電圧、レベル変換、プルアップの存在を断定しないでください。** 回路図・基板資料で次を確認します。

1. VIN/VDD/VDDIOの許容電圧、レギュレーター、端子順序。
2. SDA/SCLのレベル変換、プルアップ抵抗・接続先電圧・合成抵抗。Pi GPIOは3.3V系で5V耐性を前提にしません。
3. BMPの0x46/0x47選択、ToFの0x29/XSHUT、GND共通、短い配線と機体電源ノイズ・供給能力。
4. 通常bus 1はPi pin 3(GPIO2 SDA)、pin 5(GPIO3 SCL)、GND。電源端子は資料で確定してから接続します。
5. 下向きToFの視野、脚・配線・プロペラの遮蔽、保護フィルム/カバーのクロストーク。
   黒い床・光沢・照明・斜面での有効範囲。BMPはプロペラ風を避け、通気を確保します。
6. UARTとFC接続は既存Pi READMEに従い、FC Receiver画面で確認します。

## 実行コマンド

リポジトリ直下から実行します。OSでI2C・UARTを有効にしてください。

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r pi_zero/requirements-sensors.txt pytest
cp pi_zero/altitude.example.json altitude.local.json

# 既定：UARTなしのUDP動作確認
.venv/bin/python -m pi_zero.main --duration 10

# 1: センサー取得・推定・保存だけ。UDP/UARTを開かない
.venv/bin/python -m pi_zero.main --mode sensor-monitor --alt-config altitude.local.json --log sensors.jsonl --duration 30

# 2: センサーもUARTも開かない
.venv/bin/python -m pi_zero.main --mode simulation --log simulation.jsonl
.venv/bin/python -m pi_zero.main --mode replay --replay sensors.jsonl --log replay.jsonl --alt-config altitude.local.json
.venv/bin/python -m pytest pi_zero/tests -q

# 3: 手動RCをそのままFCへ送る。高度計算は保存だけ
.venv/bin/python -m pi_zero.main --mode shadow --alt-config altitude.local.json --log shadow.jsonl
# UARTなしでshadow通信確認するなら --dry-run も追加

# 4: 検証後のみ。同梱設定のままでは拒否される
.venv/bin/python -m pi_zero.main --mode live --enable-live --alt-config altitude.local.json --log live.jsonl

# PC：既存キーはそのまま。H=hold切替、[ / ]=目標 -/+2cm
python3 pc_keyboard_ui.py --ip 192.168.4.1 --altitude
# ゲームパッド：probeで未使用番号を確認して指定する（番号は機種依存）
python3 pc_gamepad_ui.py --ip 192.168.4.1 --altitude --alt-hold-button 0 --alt-up-button 2 --alt-down-button 3
```

ゲームパッドの既存ARM=7、ANGLE=6、panic=1、Throttle上下=5/4との重複は拒否します。
`--altitude`なしの旧UIはmanual/shadowで従来どおり手動操縦します。高度制御は発動しません。
liveは新通信形式だけを受理します。Pico向けは従来どおり`--altitude`なしを使ってください。
auto表示は計算値、out表示はPiがUARTへ出すRC値です。FCからの受理確認値ではありません。

## 座標・基準・品質

内部はm、m/s、Pa、s。生温度は`temperature_c`、気圧式ではKです。
ToFはセンサーから床までの距離で、離陸時に実測した`ground_sensor_height_m`を引き、
離陸位置に対する機体の鉛直移動量へ変換します。既定0.04mは仮値です。
機体中心の床からの絶対高さとは区別してください。同じ高さの平坦な床が継続する前提で、段差越えは対象外です。

既存基盤にはFC姿勢テレメトリの受信デコーダーがありません。未計測角度を0として生成しません。
推定器の時刻付き`Attitude`注入口へ将来実測値を渡す場合のみ、
`distance*cos(roll)*cos(pitch)`で補正します。古い姿勢・20度超は無効です。
現在は水平に近い状態に限定し、その未検証事項をlive設定でも明示します。
水平姿勢をソフトウェアが保証するわけではありません。

ToF公称約1.2mを運用上限にしません。既定床距離は0.02以上0.90m未満、
目標相対高度は0.10〜0.70mです。これらも実測済みではなく、結果に応じて狭める必要があります。
範囲外を上限値にclampして正常扱いしません。status、新規変換、鮮度、
急変（`jump_m + max_speed_m_s*dt`）を検査します。
ARM中に完全に同じ距離が`freeze_s`（2秒）続く場合も疑わしい凍結として無効にします。
これは保守的で、静止・量子化による誤検出があります。data-readyが更新され続ける故障を完全には識別できません。

変換の機器時刻がないため、`at_s`はmonotonic読取開始時刻から設定周期を引いた保守的な値です。
真のハードウェア時刻ではありません。ポーリング/取得遅延、data-ready timeout、I2C例外はinvalidです。
重複seq/timeは鮮度を更新しません。

BMP基準は地上静止・DISARM中の2秒以上で一度だけ取得します。
ToFが取付高付近で連続安定し、気圧spanも制限内であることを要求します。
飛行中・着陸後の自動再ゼロ化はありません。場所を変えた再校正はDISARM・地上でプロセス再起動します。
式は `h = R*T0/g * ln(p0/p)`、R=287.05 J/(kg K)、g=9.80665 m/s²。
静水圧平衡・乾燥空気・基準付近の等温層を仮定します。T0は基準時センサー温度で、
周囲平均気温とは限りません。気圧変動、自己発熱、プロペラ風、風防遅延を誤差として考慮します。
標準`estimator_mode=tof`ではBMPは記録・比較専用で、ToF喪失時に使いません。

`comparison-blend`はmonitor/replay/shadow用の交換可能な実験モードです。
両方が有効な最初の時点で固定biasを取り、`(1-w)*ToF+w*(baro+bias)`（既定w=0.1）を計算します。
両方の品質・鮮度と差0.3m以内を要求します。biasを飛行中に追従更新せず、床変化や気圧ドリフトは補償できません。
片方の喪失時の継続やlive利用は禁止しています。

## 制御・設定単位

`u = hover + Kp*(target-height) + Ki*integral(error) - Kd*velocity`

uは既存RC Throttleスケール（µs相当）で推力[N]ではありません。
KpはRC単位/m、KiはRC単位/(m·s)、KdはRC単位·s/m。
ゲインは全て0が既定です。最初はKi=0を維持し、質量だけからゲインを決めないでください。
hoverはON時の手動Throttleです。`verified_hover_throttle`は実測設定の検証ゲートであり、そこへ瞬間移動しません。

センサー周期（各50ms）、制御周期（20ms）、CRSF送信（20ms）は独立しています。
実monotonic dtと`alpha=dt/(tau+dt)`で高度LPF、平滑高度差分の速度LPFを計算します。
高度tau=0.08s、速度tau=0.15s。低周波での遅延目安は高度0.08s、速度0.23sに取得・配送時間を加えます。
正確な遅延は周波数/周期に依存します。ログに時刻・取得時間・LPF遅延目安・loop遅延を残します。
予測による遅延補償はなく、遅延込みの調整が必要です。

|設定|単位/意味|
|---|---|
|bmp_period_s|0.025/0.05/0.1/0.2秒からODR選択|
|tof_period_s / tof_budget_ms|測距周期s / budget ms|
|stale_s / qualify_s / max_dt_s|鮮度0.20s / 品質継続1s / 制御dt上限0.10s|
|throttle_min / throttle_max|RC下限1000 / 上限1200|
|correction_limit / slew_per_s|ON時手動値から±40 / 通常時80 RC単位/s|
|integral_limit_m_s|積分状態の絶対上限m·s|
|target_min_m / target_max_m|目標相対高度m。床距離限界への余裕が必要|
|max_enable_velocity_m_s|ON時推定速度の絶対上限0.15m/s|

ONはARM済み、品質継続、範囲内、低速度、OFFを経た新しい操作が条件です。
現在高度をcaptureし最初の出力を現在手動Throttleと一致させます。ARM自体は手動です。
目標変更はcaptureに対するoffset差で、同一パケット再送で重複加算しません。
通常OFFではMANUALへ移り、直前自動値から最新の手動Throttleへslewで近づきます。
`releasing=true`の間は新しいONを拒否します。手動値も自動値に近づけておいてください。
緊急DISARM/通信failsafeには平滑化・slewを掛けません。
絶対出力、補正幅、slewで飽和する方向への積分を止めるanti-windupと積分上限があります。
DISARM・解除・FAULTで積分をリセットします。Dは速度に掛け、目標差分には掛けません。

既存上限1200ではMeteor85がホバーできない可能性があります。上限を自動変更しません。
安全な手動試験で必要値を確かめ、明示設定でのみ変更します。
liveには`manual_hover_verified`, `verified_hover_throttle`（上下限内側）、`sensor_range_verified`,
`gains_verified`, `loss_policy_tested`, `fc_failsafe_tested`, `near_level_operation_accepted`と
条件・日付を記した`verification_notes`が必須です。フラグ変更だけで検証が成立するものではありません。

## 状態と故障時動作

優先順位は緊急DISARM/通信failsafe ＞ 明示OFF ＞ 高度制御です。

|状態|動作|
|---|---|
|DISARMED|起動状態。ARM OFFかつThrottle=1000後に新しいARMだけを許可|
|MANUAL|手動出力。通常解除直後のliveはslew受渡しを含む|
|ALT_HOLD|ToF正常時に補正。shadowは計算のみ|
|FAULT|高度制御停止、積分リセット、理由保持。復帰だけで再開しない|

既存UDP timeout（500ms）、不正パケット、受信滞留過多はDISARM/1000を優先します。
不正・期限切れ・重複パケットはtimeoutを延長しません。
liveはPi発行の短命ランダムtoken（最大0.4s）と増加seqを要求します。
起動/timeout/faultでtokenを無効化し、新statusとの往復とARM OFF→ONが必要です。
受信batch内で滞留OFF→ONを実行しません。OFFが同batchのARMより優先します。
暗号認証ではないため信頼できる専用ネットワークで使用します。
旧形式では個別到着する遅延パケットを完全に識別できないためliveでは拒否します。
fault解除はARM OFF、手動再ARM、hold OFF→ONで行います。

センサー喪失時の`loss_policy`は明示設定・試験が必要です。

- `bench-disarm`（既定）：liveでは即時DISARM/1000。プロペラなしベンチ用です。
  **空中DISARMは墜落につながります。安全に着陸する機能ではありません。**
- `manual-recover`：高度制御を即停止し現在手動Throttleへ返します。最後の自動値を保持しません。
  通常OFFと異なり即時返却なので差があれば急変します。操縦者の即応・Throttle位置合わせ・回復試験が必須です。
  高度制御はFAULTのままです。通信も失えば既存DISARM failsafeが優先します。

shadowのセンサーFAULTは手動RCを変更しません。通信failsafe・緊急DISARMは有効です。
自動着陸や気圧への自動切替はありません。
Pi停止・電源断・UART断・SIGKILLではfinallyによる安全フレームは送れません。
プロペラを外し、FC Receiver画面・failsafe状態で通常DISARM、UDP停止、
Pi通常/強制停止、Pi電源断、UART信号断を個別確認します。
FCでの受信途絶時間とThrottle/ARM動作を記録し、復帰だけで再ARMしないことを確認してください。
FCファームウェアとfailsafe設定は機体に適したものを別途検証します。

## ログと検証順

JSONL settings行に設定、壁時計とmonotonic対応を保存します。
tick行は測定生値（単位付きキー）、seq/時刻/valid/error/status/取得時間、推定高度/速度、
target、P/I/D、制限上下限とlimited、manual/auto/output、RC、状態/遷移、fault、dt、loop遅延です。
不正なNaN/Infinityはnullで保存しinvalidを維持します。保存欠落数/エラーはstatusにも載ります。
欠落区間の完全再現はできません。replayはUARTを開かずshadow計算します。
既定ではログのsettingsを使い、`--alt-config`指定時だけ設定を上書きして比較します。
simulationのゲイン・1400ホバー・一次元推力モデルは架空です。固定seed、距離ノイズ、60ms配送遅延、
推力応答遅れ/飽和、外乱を含みます。**シミュレーション成功は実機の安定性保証ではありません。**

1. プロペラを外し、配線・I2Cアドレス・センサー・FC Receiver全chとDISARMを確認。
2. 地上静止で取付高/BMP基準を確認。手で高さを変え距離・相対高度・上昇速度正を確認。
   目標より低いと補正正、上昇速度正ならD補正負、範囲外/欠測でFAULTを確認。
3. ログ再生・simulation・自動テスト。切断、data-ready停止、UDP途絶、stale token、保存遅延、緊急DISARMを試験。
4. 安全を確保した手動ホバーでshadow記録。実ホバーThrottle、床/光条件別有効範囲、ノイズ・遅延・風影響を調べる。
5. Ki=0、補正幅を小さくし、小さいKpから検討。Kdで上下速度を減衰させる。
   遅延・飽和・振動を確認し一度に一変数ずつ変更。IはPD安定と定常偏差を確認した後だけ追加する。
6. 設定・通常解除の受渡し・故障時回復・FC failsafeを検証後、実測範囲内で限定的な高度維持試験。

実機でしか検証できないもの：基板定格、取付高、床/照明/姿勢、I2C耐ノイズ、PiのOS遅延・UART実baud、
FC設定、Meteor85推力/ホバー、プロペラ風、バッテリー低下、空中回復。いずれも未確認です。
