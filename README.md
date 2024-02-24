# genesa

Utility acting as a Netplay feature for multiplayer console emulator games

Set it up as a game host or a player connecting and your keypresses will be captured and sent
to the game host via UDP socket. Host program receives the keys for each player individually and
simulates them as if host had triggered them themselves.

Currently does not support any security measures so use it only when clients and host are on the
same network (e.g. using Hamachi) but the feature is planned in the future.

Keypress capturing is based on boppreh's `keyboard` library and its copy can be found in the root dir.
- https://github.com/boppreh/keyboard

## Special keybinds
The program features a few useful keybinds as well as configurable selection of keys that should
be tracked.

| Shortcut | Description |
| :------: | ----------- |
| F7       | Enables or disables capturing keypresses |
| Esc      | Quickly exits the program |

