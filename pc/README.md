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
