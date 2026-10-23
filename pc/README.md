# PC側の操作と入力デバイス確認

コマンドはリポジトリ直下で実行します。PCとPico WまたはPi Zero Wを同じネットワークに接続し、
`<IP>` を送信先のIPに置き換えてください。

|ファイル|役割|起動方法|
|---|---|---|
|`keyboard_ui.py`|キーボード操作|`python -m pc.keyboard_ui --ip <IP>`|
|`gamepad_ui.py`|ゲームパッド操作とACK表示|`python -m pc.gamepad_ui --ip <IP> --receiver-test`|
|`gamepad_probe.py`|ゲームパッドの軸・ボタン番号確認|`python -m pc.gamepad_probe`|
|`hid_probe.py`|Raw HID機器の確認|`python -m pc.hid_probe --list`|
|`altitude.py`|Pi用高度制御プロトコルのクライアント|UIから使用|

ゲームパッドUIとprobeには `python -m pip install pygame`、Raw HID probeには
`python -m pip install hidapi` が必要です。WindowsのキーボードUIには
`python -m pip install windows-curses` を実行してください。

従来の `python pc_keyboard_ui.py ...`、`python pc_gamepad_ui.py ...`、
`python pc_gamepad_probe.py`、`python pc_hid_probe.py ...` も利用できます。
ルートの `pc_*.py` は互換用で、実装の編集はこのディレクトリで行います。
`python pc/gamepad_ui.py` のような直接起動ではなく、上記の `-m` または互換ランチャーを使用してください。

Pi Zero Wのセットアップは[Pi Zeroガイド](../pi_zero/README.md)、
高度表示・操作は[高度維持ガイド](../pi_zero/ALTITUDE.md)を参照してください。

送信指令を詳しく確認するには`--details`を付けます。従来の1行表示は引き続き既定です。

```bash
python -m pc.gamepad_ui --ip <IP> --details
# プロペラを外してReceiver表示と比較する場合
python -m pc.gamepad_ui --ip <IP> --receiver-test --details
```

詳細表示は200msごとに、CH1〜6、ARM/ANGLE、操作中と実送信のThrottle、
全軸の生値、押下ボタン番号、送信JSON、ACKの経過時間と受信側RCを追記します。
送信自体は従来の30Hzです。DISARM時などのThrottle補正も送信後の値で確認できます。
`--altitude`と併用すると高度維持要求・目標offset・高度状態も表示します。
ACKが1秒以上届かない場合は受信側の値を現在値として表示しません。
Pi側のThrottle制限や高度補正で送信値と受信側出力が異なる場合があります。
ACKはブリッジの報告であり、FCが受理したことを保証するものではありません。
