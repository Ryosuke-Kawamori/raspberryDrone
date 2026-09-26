# Raspberry Pi Zero W UDP → CRSF

BMP581 / VL53L4CDの高度維持を追加しました。
**既定起動はUARTを開かないdry-runです。** UART手動ブリッジは`--mode manual`を明示してください。
センサー配線、実行モード、設定単位、校正、調整、FC failsafe検証は
[高度維持ガイド](ALTITUDE.md)を参照してください。未検証設定ではliveを起動できません。

既存PC UI → Wi-Fi / UDP → Pi Zero W → GPIO UART / CRSF → Meteor85 FC。
Pico W用ファイルは維持し、PC UIはオプションで高度表示・操作に対応します。CPython 3.11以降を使います。
リポジトリ直下の `crsf.py` と `rc_protocol.py` はMicroPython依存がないため、そのまま共有します。

## 初めてセットアップする場合

対象は **Raspberry Pi Zero W（Pi Zero W）** です。microSDへRaspberry Pi OSを入れ、
通常のPythonで起動します。Pico W用のUF2、MicroPython、Thonny、`wifi_config.py` は使用しません。

次の順番で進めてください。初回のdry-runまではFCやセンサーの接続は不要です。

1. [OS・Wi-Fi・SSHとPython環境を準備](#osとpythonの準備sta方式)する。
2. dry-runで起動し、PC UIからのUDPとACKを確認する。
3. [UARTとPL011](#uartとpl011)を設定する。
4. [FCへ配線し、Receiverタブで確認](#配線とreceiver確認)する。
5. 手動動作と安全停止の確認後に[自動起動](#systemd)を設定する。

準備するもの：Pi Zero W、microSDカードとカードリーダー、安定した5V USB電源とケーブル、
Wi-Fi接続できるPC。FC接続時には配線材と、必要に応じてはんだ付け用品を用意します。
最初は既存Wi-FiへのSTA接続で進めます。AP化と高度センサーの設定は後から追加できます。

## 動作と安全状態

|項目|設定|
|---|---|
|UDP|`0.0.0.0:5005`、既存JSON|
|UART|`/dev/serial0`、420000 baud、8N1、フロー制御なし|
|RC送信|50Hz / 20ms、`time.monotonic()` 基準|
|通信断|最後の正常パケットから500ms以上でDisarm|
|Throttle|Pi側で1000～1200に制限|
|安全値|Roll/Pitch/Yaw=1500、Throttle=1000、ARM=False、Angle=True|
|終了|SIGINT/SIGTERMまたは例外時、20ms間隔で安全フレーム50回を試行|

CH1=Roll、CH2=Pitch、CH3=Throttle、CH4=Yaw、CH5=AUX1 ARM、CH6=AUX2 Angle。
ARM/Angleは1000=OFF、2000=ON、CH7～16は1500です。

起動直後に安全フレームを送ります。起動・通信断・不正JSON・受信過多の後はARMロック状態です。
通常モードの **`arm:false, throttle:1000` を明示したパケット**を受けてから、
Throttle=1000のARM要求だけを受け付けます。ARM中にThrottleを上げることは可能です。
通信復旧時にARM=Trueを送り続けても再ARMしません。PCで一度ARM OFF・Throttle最小に戻してください。
ARM切り替え時にThrottleが高ければロックへ戻ります。

`receiver_test:true` はARMを常にOFFにし、Throttleだけ1000～1200の範囲で動かせます。
このモードはARMロックを解除しません。通常のDisarmはThrottleも1000へ戻します。
JSONの数値フィールドは数値、真偽値フィールドはJSON booleanを使います。
不正JSON・非オブジェクト・不正な型・NaN/InfinityのRC値は安全状態に戻します。
既存の `rc_protocol.py` のThrottle上限が変更されていても、Pi側の既定上限1200は維持します。
高度設定ファイルによる明示的な変更だけを許可します。手動ホバー実測がない設定ではliveを拒否します。

ACKは200msごとに最後の正常送信元へ返します。
`{"type":"pico_status","packets":1,"link_age_ms":0,"rc":{...},"arm_ready":true}`
という既存互換形式です。ゲームパッドUIの `ACK packets=... age=...ms` 表示で確認できます。
キーボードUIには元々ACK表示機能がなく、送信互換性を維持しています。
ゲームパッドUIのRC表示は送信値です。Pi側で拒否したARMや制限後の値はACKの `rc` またはFCで確認してください。

Linux/CPythonはハードリアルタイムではなく、負荷による周期の揺れがあります。
遅れたフレームはまとめて送らず、次周期へ進めます。タイムアウト判定後の安全値は次の送信機会で出力します。
UARTを開けなければ異常終了します。UART切断時は安全送信を試行して異常終了します。
電源断・SIGKILL・OS停止・物理断線では安全フレームは届けられないため、FC自体のRX loss failsafeも設定・確認してください。
UDPは認証・シーケンス番号を持たない既存形式です。信頼できるLANで単一のPC送信元を使ってください。

## OSとPythonの準備（STA方式）

### OSの書き込みとSSH接続

PCのRaspberry Pi Imagerで機種をPi Zero Wに設定し、**Zero W対応のRaspberry Pi OS Lite (32-bit)**
をmicroSDへ書き込みます。書き込み前のカスタマイズで以下を設定します。

|項目|設定例|
|---|---|
|ホスト名|`raspberrydrone`|
|ユーザー名・パスワード|自分で設定（以下の `<USER>` に使用）|
|SSH|有効（パスワード認証または自分の公開鍵を設定）|
|Wi-Fi|既存の2.4GHz Wi-FiのSSID・パスワード|
|Wi-Fiの国|実際の使用国（日本ならJP）|

microSDをPiへ挿入して給電し、起動を待ちます。PCも同じLANへ接続します。
**PCのPowerShellまたはターミナル**から接続してください。

```powershell
ssh <USER>@raspberrydrone.local
```

`<USER>` は設定したユーザー名へ置き換えます。初回接続時は接続先を確認してホスト鍵を登録します。
名前で接続できない場合は、ルーターのDHCPリース一覧でPiのIPを確認し、
`ssh <USER>@<PI_ZERO_IP>` を使います。詳しくは[IPの確認方法](#pcからipを確認)を参照してください。

### Pythonとコードの配置

以下は **SSH接続したPi上**で実行します。Pythonが3.11以上であることを確認してください。

```bash
sudo apt update
sudo apt install -y git python3 python3-venv
python3 --version
```

GitHubへ必要なコードがpush済みなら、Pi上で取得します。

```bash
git clone https://github.com/Ryosuke-Kawamori/raspberryDrone.git
cd raspberryDrone
```

別ブランチで作業している場合は、そのブランチをチェックアウトしてください。
**PC上の未commit・未pushの変更や追加ファイルは、cloneだけではPiへ入りません。**
その場合はPCのリポジトリ直下から、必要なコードをSSH経由で転送できます。
以下は新しい配置先 `~/raspberryDrone` を作る例です。既に同名ファイルがある場合は上書きされるので、
Pi側で編集している場合は別の配置先を使ってください。

```powershell
ssh <USER>@raspberrydrone.local "mkdir -p ~/raspberryDrone"
scp -r pi_zero crsf.py rc_protocol.py <USER>@raspberrydrone.local:~/raspberryDrone/
```

`pi_zero/` は現在の高度関連モジュールも含めてディレクトリごと転送します。
PC UIはPC上で実行するため、この転送例には含めません。Windows用の `.venv` は転送せず、
**Pi上**で新しいvenvを作ります。

PC UIの実装は [`pc/`](../pc/README.md) にあります。PCへコードをコピーして配置する場合は、
ルートの `pc_*.py` だけでなく `pc/` と `rc_protocol.py` も含めてください。
ルートの `pc_*.py` は従来コマンド用の互換ランチャーです。

```bash
cd ~/raspberryDrone
ls pi_zero/main.py crsf.py rc_protocol.py
python3 -m venv .venv
.venv/bin/python -m pip install -r pi_zero/requirements.txt
.venv/bin/python -m pi_zero.main --dry-run
```

すべての起動コマンドはリポジトリ直下で実行します。`python pi_zero/main.py` ではなく
`python -m pi_zero.main` を使います。dry-runではpyserialのインポートもUART openもせず、
RC値とCRSFフレームの16進表現を1秒に1回ログ出力します。Ctrl+Cで終了できます。

### FCなしでUDP通信を確認

Piでdry-runを起動したまま、別のSSH端末で `hostname -I` を実行してWi-Fi側のIPを確認します。
**PC側のリポジトリ直下**で、ゲームパッドを接続して以下を実行します。

```powershell
python -m pip install pygame
python pc_gamepad_ui.py --ip <PI_ZERO_IP> --receiver-test
```

PCに `ACK packets=...` が表示され、Piのログに操作値が反映されればUDP通信の確認は完了です。
dry-runではFCへ何も送信しません。この確認にはゲームパッドを使います。
ゲームパッドがない場合は、後述のキーボードUIで送信し、Pi側のログで受信値を確認できます。

## UARTとPL011

Pi Zero Wでは420000 baudを安定して出すため、GPIO14/15側にPL011を割り当てる設定を推奨します。
Bluetoothを無効化してPL011をprimary UARTへ戻します。
[Raspberry Pi公式UART資料](https://www.raspberrypi.com/documentation/computers/configuration.html#configure-uarts)
も参照してください。

```bash
sudo raspi-config
```

Interface Options → Serial Portで、serial login shellは **No**、serial hardwareは **Yes** にします。
OS世代によって起動設定は `/boot/firmware/config.txt` または `/boot/config.txt` です。
実際のファイルをバックアップして編集し、有効な `[all]` セクションへ以下を設定します。
重複するUART/Bluetooth overlayは整理してください。

通常の編集コマンドは `sudo nano /boot/firmware/config.txt` です。
旧OSでは `sudo nano /boot/config.txt` を使い、実際に起動に使用されるファイルを編集します。

```ini
enable_uart=1
dtoverlay=disable-bt
```

古いイメージでは `dtoverlay=pi3-disable-bt` を `disable-bt` の代わりに使えます。
両方を同時に追加せず、インストール済みの `/boot/firmware/overlays/README`
（旧OSでは `/boot/overlays/README`）で利用可能な名前を確認してください。
[公式overlay一覧](https://github.com/raspberrypi/firmware/blob/master/boot/overlays/README)
では `disable-bt` と旧名の互換対応を確認できます。

同じbootディレクトリの `cmdline.txt` から `console=serial0,115200`、
`console=ttyAMA0,...` などGPIO UARTを使うconsole指定を取り除きます。
他の設定は保持し、ファイルは1行のままにします。

```bash
sudo systemctl disable --now hciuart.service
sudo systemctl disable --now bluetooth.service
sudo systemctl disable --now serial-getty@serial0.service serial-getty@ttyAMA0.service
sudo reboot
```

存在しないサービスについての「not found」は、そのサービスが未導入なら問題ありません。
再起動後に確認します。

```bash
readlink -f /dev/serial0
ls -l /dev/serial0 /dev/ttyAMA0
cat /proc/cmdline
```

Zero Wのこの設定では `/dev/serial0` がPL011の `/dev/ttyAMA0` を指すことを確認します。
`/dev/ttyS0` のままなら設定を見直してください。
シリアル端末や他のサービスから同じUARTを同時使用しないでください。

Raspberry Pi OSでは通常UARTデバイスの所属グループは `dialout` です。
`ls -l` で確認し、実際のserialアクセス用グループへ実行ユーザーを追加します。
OSによって `serial` などの場合は以下とserviceの `SupplementaryGroups` を読み替えてください。

```bash
sudo usermod -aG dialout "$(id -un)"
```

ログアウト・再ログインして `id` で反映を確認します。通常の起動にsudoは不要です。

## 配線とReceiver確認

プロペラを外し、電源を切って配線します。

|Pi Zero W|Meteor85 FC|
|---|---|
|GPIO14 / physical pin 8 / TX|使用するUARTのRX|
|GPIO15 / physical pin 10 / RX|同じUARTのTX（optional）|
|GND（例 physical pin 6）|GND|

UARTは **3.3Vロジック**です。5VをTX/RX端子に接続しないでください。
Pi用電源とFC用電源を適切に用意し、GNDを共通化します。RX接続は不要で、今回はテレメトリ受信は実装していません。
FC側のRX/TXパッドはMeteor85に搭載された基板の型番・配線図で確認してください。
Pico W用のGP0/GP1配線とは異なります。

1. Betaflightで使用UARTのSerial RXを有効にし、受信方式をSerial、プロトコルをCRSF、
   チャンネルマップをAETR1234に設定します。既存内蔵受信機との競合を避けてください。
2. ModesでAUX1の高側をARM、AUX2の高側をAngleに割り当てます。
3. Piで実UART出力を開始します。

```bash
.venv/bin/python -m pi_zero.main --mode manual --uart /dev/serial0 --baud 420000 --port 5005 --link-timeout-ms 500
```

420000 baud、8N1、50Hz、UDP 5005、timeout 500msは既定値です。
短く起動する場合は `.venv/bin/python -m pi_zero.main --mode manual` でも同じ設定になります。
**`--uart` だけでは実UART出力に切り替わりません。`--mode manual` を明示してください。**

4. PCでゲームパッド用依存を用意し、receiver-testで起動します。

```bash
python -m pip install pygame
python pc_gamepad_ui.py --ip <PI_ZERO_IP> --receiver-test
```

5. ReceiverタブでCH1～4の方向と中立、Throttle=1000～1200、AUX1=1000固定、
   AUX2の切り替えを確認します。ARM操作をしてもAUX1が上がらないことを確認してください。
6. PC UIを止める、またはWi-Fiを切り、Throttle=1000・AUX1=1000に戻ることを確認します。
   通信復帰後も自動ARMしないこと、PiのCtrl+C停止でも安全値を送ることを確認してください。

通常のキーボードUI実行例（receiver-testオプションはありません）：

```bash
python pc_keyboard_ui.py --ip <PI_ZERO_IP>
```

通常操作の初期状態はARM OFF・Throttle最小です。ARM操作前にその状態をPiへ送信してください。
キーボードUIをWindowsで使う場合は、PCで `python -m pip install windows-curses` を実行します。

## PCからIPを確認

Imagerで設定したホスト名を使って `ping raspberrydrone.local` を実行します。
Windowsでは `Resolve-DnsName raspberrydrone.local`、Linux/macOSでは
`ssh <USER>@raspberrydrone.local 'hostname -I'` でも確認できます。
mDNSが使えなければルーターのDHCPリース一覧でPiのホスト名を探してください。
`arp -a` は既に通信したLAN機器の確認に使えますが、必ず全機器を列挙するものではありません。
Pi側では `hostname -I` または `ip -4 addr show wlan0` を使います。
ACKが来ない場合はIP、UDP 5005、PC側の戻りUDP、LAN内クライアント隔離設定を確認します。

## systemd

手動でUARTと安全停止を確認した後、テンプレートをコピーします。

```bash
sudo cp pi_zero/raspberry-drone.service /etc/systemd/system/raspberry-drone.service
sudoedit /etc/systemd/system/raspberry-drone.service
```

`REPLACE_WITH_USER` を実行ユーザー名に、`/REPLACE_WITH_ABSOLUTE_REPO_PATH` の2箇所を
実際のリポジトリ絶対パス（`pwd` で確認）に置き換えます。
`ExecStart` のvenvもそのパスの `.venv/bin/python` を指すようにします。
空白のない配置先を推奨します。テンプレートは既定のdry-runで起動します。
手動UARTブリッジとして自動起動する場合は、動作確認後に `ExecStart` の末尾へ
`--mode manual` を追加してください。明示的に非駆動で確認する場合は `--dry-run` を付けます。

```bash
sudo systemd-analyze verify /etc/systemd/system/raspberry-drone.service
sudo systemctl daemon-reload
sudo systemctl enable --now raspberry-drone.service
systemctl status raspberry-drone.service
journalctl -u raspberry-drone.service -f
```

異常終了時は3秒後に再起動します（60秒間に5回の起動制限あり）。再起動してもARMロックから開始します。
`sudo systemctl stop raspberry-drone.service` はSIGTERMを送り、安全フレーム50回送信後に終了します。
UARTエラーを含めた送信試行のため `TimeoutStopSec=10` を確保しています。
手動起動とserviceを同時実行しないでください。

## 任意: hostapd / dnsmasqでAP化

以下は **STA接続を置き換える手動設定例**です。実装にはネットワーク変更スクリプトを含めません。
SSH接続は切れるため、ローカル端末または別の管理経路を用意し、対象ファイルをバックアップしてください。
単一 `wlan0` をAP専用にし、インターネット転送/NATは設定しません。

```bash
sudo apt install hostapd dnsmasq
sudo systemctl stop hostapd dnsmasq
```

NetworkManagerを使用するOSでは `/etc/NetworkManager/conf.d/90-drone-ap.conf` を作ります。
他に `unmanaged-devices` 設定がある場合は既存内容と統合してください。

```ini
[keyfile]
unmanaged-devices=interface-name:wlan0
```

古いdhcpcd構成では、代わりに `/etc/dhcpcd.conf` へ `denyinterfaces wlan0` を追加します。
どちらも他のインターフェース設定は保持します。wlan0用のwpa_supplicantなどが別サービスとして
稼働していれば、そのwlan0サービスも停止して競合を除いてください。

`/etc/systemd/network/90-drone-ap.network` を作り、APのアドレスを設定します。

```ini
[Match]
Name=wlan0
[Network]
Address=192.168.4.1/24
DHCP=no
ConfigureWithoutCarrier=yes
```

既存のsystemd-networkd設定がwlan0に先にマッチしないことを確認します。
`/etc/hostapd/hostapd.conf` を作ります。`country_code` は実際の国、パスワードは固有の8～63文字へ置換します。

```ini
interface=wlan0
driver=nl80211
country_code=JP
ssid=raspberry-drone
hw_mode=g
channel=6
ieee80211d=1
wmm_enabled=1
auth_algs=1
wpa=2
wpa_passphrase=REPLACE_WITH_UNIQUE_PASSWORD
wpa_key_mgmt=WPA-PSK
rsn_pairwise=CCMP
```

パッケージの `systemctl cat hostapd` で上記設定ファイルを読むことを確認してください。
古いパッケージで必要なら `/etc/default/hostapd` に
`DAEMON_CONF="/etc/hostapd/hostapd.conf"` を設定します。
`/etc/dnsmasq.d/drone-ap.conf` を作ります（既存のDHCP設定と競合させないでください）。

```ini
interface=wlan0
bind-dynamic
port=0
dhcp-range=192.168.4.10,192.168.4.50,255.255.255.0,12h
dhcp-option=3
dhcp-option=6
```

```bash
sudo dnsmasq --test
sudo systemctl unmask hostapd
sudo systemctl enable systemd-networkd hostapd dnsmasq
sudo reboot
```

PCを `raspberry-drone` に接続し、UIには `--ip 192.168.4.1` を指定します。
このネットワークにはインターネット接続がありません。
復旧時はhostapd/dnsmasqを停止し、追加したAP用設定を外して、バックアップしたSTA設定を戻して再起動します。
NetworkManager方式のOSで提供される別のAP設定方法は
[公式ホットスポット資料](https://www.raspberrypi.com/documentation/computers/configuration.html#enable-hotspot)
を参照してください。上記hostapd方式と同時に有効にしないでください。

## テストと拡張点

```bash
.venv/bin/python -m pip install pytest
.venv/bin/python -m pytest pi_zero/tests -q
```

実UDPのlocalhost通信、既存ゲームパッドUIのpayload/ACK処理、CRSF固定ベクトルとチャンネル、
不正JSON、タイムアウト境界、ARMロック、FakeSerialと仮想時計による20ms周期、
SIGINT/SIGTERM、例外時の安全送信を検証します。実機の電気特性やLinuxの周期精度は別途測定してください。

`UdpRcReceiver` が入力、`RcState` が安全状態、`SerialTransport` がCRSF出力を担当します。
高度推定・制御は独立した層とし、最終出力前に同じ通信・DISARM制約を通しています。
BMP581、VL53L4CD、高度維持PD/PIDは[高度維持ガイド](ALTITUDE.md)を参照してください。
カメラ、映像認識、自動離着陸、水平位置保持は実装していません。
