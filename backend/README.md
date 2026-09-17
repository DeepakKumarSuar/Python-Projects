# Tic-Tac-Toe Multiplayer Backend — v1

This replaces the expired Railway WebSocket server.

## Structure

- `server.py` — WebSocket server, rooms, validation, timers, disconnects.
- `games/tic_tac_toe.py` — Tic-Tac-Toe rules.
- `requirements.txt` — server dependency.
- `Procfile` — process command for hosts that support it.

## Local run

From this `backend` directory:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python server.py
```

The server listens on:

```text
ws://127.0.0.1:8080
```

## Protocol

Client messages:

- `create_room`
- `join_room`
- `game_move`
- `disconnect_room`

Server messages:

- `room_created`
- `opponent_joined`
- `room_joined`
- `game_move`
- `turn_switch`
- `game_win`
- `game_tie`
- `opponent_disconnected`
- `error`

## Security/state improvements over the old server

- Random 6-character room codes instead of 0–100.
- Server determines X/O from the WebSocket connection.
- Client-supplied `player` is ignored.
- Board positions are validated.
- Turn ownership is validated.
- Occupied cells are rejected.
- Server enforces a 30-second turn timeout.
- Disconnects are handled centrally.
- WebSocket ping/pong is enabled.
- Game rules are separated from room/networking code.

## Important

The current frontend still points to the expired Railway URL and still uses the old numeric room-code UI.

**Do not expect online multiplayer to work yet.**

The next step is to update `Tic-Tac-Toe-PY/main.py` to use this backend while preserving the existing UI exactly.


- Each rematch alternates the starting player: X starts the first round, then O, then X, and so on.
