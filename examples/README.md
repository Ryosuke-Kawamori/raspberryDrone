# 手動の実機確認スクリプト

ここには元々ルートにあった独立した確認スクリプトを移しています。
通常運用の起動ファイルやpytestの自動テストではありません。内容と対象機器を確認してから実行してください。

|旧ファイル名|現在のパス|実行先・動作|
|---|---|---|
|`testPicomotor.py`|`pico_w/motor_test.py`|Pico W。自動ARMとモーター出力を含む|
|`testPicoFcReceive.py`|`pico_w/receiver_test.py`|Pico W。RCチャンネルを順番に変化させる|
|`testPicoFcConnection.py`|`pico_w/connection_test.py`|Pico W。Pitchチャンネルを周期的に変化させる|
|`testCommand.py`|`udp/send_rc.py`|PC。指定IPへ固定のDisarm RC値をUDP送信する|

`pico_w/` のスクリプトはMicroPythonの `machine` を使います。
Pico Wへ必要な1本をコピーし、通常の `main.py` と同時に動かさず実行してください。
プロペラを外し、特に `motor_test.py` は自動でARMする内容を確認してから使用します。
初回Receiver確認には[通常UIのreceiver-test手順](../pi_zero/README.md#配線とreceiver確認)を使えます。

UDPの簡易確認は `udp/send_rc.py` 内の `PICO_IP` を実際の対象IPへ変更し、
リポジトリ直下で `python examples/udp/send_rc.py` を実行します。終了はCtrl+Cです。

`pytest.ini` は自動テストの探索先を `pi_zero/tests/` と `tests/` に限定し、
これらの実機操作スクリプトを自動収集しません。
