import asyncio
import json
import logging
import os
import secrets
import string
from dataclasses import dataclass, field

import websockets
from websockets.exceptions import ConnectionClosed

from games.tic_tac_toe import check_result

HOST = "0.0.0.0"
PORT = int(os.getenv("PORT", "8080"))

ROOM_CODE_LENGTH = 6
TURN_TIMEOUT_SECONDS = 30

logger = logging.getLogger("ttt-server")
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s | %(levelname)s | %(message)s",
)


@dataclass
class Room:
    code: str
    player_x: object | None = None
    player_o: object | None = None
    board: list[str] = field(default_factory=lambda: [""] * 9)
    turn: str = "X"
    # The player who starts the current round. It alternates after every rematch.
    starting_player: str = "X"
    round_active: bool = True
    turn_task: asyncio.Task | None = None
    rematch_votes: set = field(default_factory=set)

    def symbol_for(self, websocket):
        if self.player_x is websocket:
            return "X"
        if self.player_o is websocket:
            return "O"
        return None

    @property
    def full(self):
        return self.player_x is not None and self.player_o is not None


ROOMS: dict[str, Room] = {}


def generate_room_code() -> str:
    # Avoid visually ambiguous characters.
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    while True:
        code = "".join(secrets.choice(alphabet) for _ in range(ROOM_CODE_LENGTH))
        if code not in ROOMS:
            return code


async def send(ws, message_type: str, data: dict | None = None):
    if ws is None:
        return

    try:
        await ws.send(json.dumps({
            "type": message_type,
            "data": data or {},
        }))
    except ConnectionClosed:
        pass


async def broadcast(room: Room, message_type: str, data: dict | None = None):
    await asyncio.gather(
        send(room.player_x, message_type, data),
        send(room.player_o, message_type, data),
    )


def find_room(ws):
    for code, room in ROOMS.items():
        if room.player_x is ws or room.player_o is ws:
            return code, room
    return None, None


def cancel_turn_timer(room: Room):
    task = room.turn_task
    room.turn_task = None

    if task and not task.done():
        task.cancel()


async def turn_timeout(room_code: str, expected_turn: str):
    try:
        await asyncio.sleep(TURN_TIMEOUT_SECONDS)
    except asyncio.CancelledError:
        return

    room = ROOMS.get(room_code)

    if room is None or not room.round_active or room.turn != expected_turn:
        return

    winner = "O" if expected_turn == "X" else "X"

    room.round_active = False
    cancel_turn_timer(room)

    logger.info(
        "Room %s: player %s timed out; %s wins",
        room_code,
        expected_turn,
        winner,
    )

    # Compatible with the current frontend.
    await broadcast(
        room,
        "game_win",
        {
            "winner": winner,
            "condition": [],
            "index": None,
            "player": expected_turn,
            "reason": "timeout",
        },
    )


def start_turn_timer(room: Room):
    cancel_turn_timer(room)

    if room.full and room.round_active:
        room.turn_task = asyncio.create_task(
            turn_timeout(room.code, room.turn)
        )


async def create_room(ws):
    existing_code, _ = find_room(ws)
    if existing_code:
        await send(ws, "error", {"message": "You are already in a room."})
        return

    code = generate_room_code()
    room = Room(code=code, player_x=ws)
    ROOMS[code] = room

    logger.info("Room %s created", code)
    await send(ws, "room_created", {
        "code": code,
        "player": "X",
    })


async def join_room(ws, code):
    existing_code, _ = find_room(ws)
    if existing_code:
        await send(ws, "error", {"message": "You are already in a room."})
        return

    if not isinstance(code, str):
        await send(ws, "error", {"message": "Invalid room code."})
        return

    code = code.strip().upper()
    room = ROOMS.get(code)

    if room is None:
        await send(ws, "error", {"message": "Room not found."})
        return

    if room.full:
        await send(ws, "error", {"message": "Room is full."})
        return

    room.player_o = ws

    logger.info("Player O joined room %s", code)

    await send(ws, "room_joined", {
        "code": code,
        "player": "O",
    })
    await send(room.player_x, "opponent_joined", {
        "code": code,
        "player": "O",
    })

    start_turn_timer(room)


async def handle_rematch(ws, data):
    code = data.get("code")
    room = ROOMS.get(str(code).strip().upper()) if isinstance(code, str) else None
    if room is None:
        await send(ws, "error", {"message": "Room not found."})
        return
    symbol = room.symbol_for(ws)
    if symbol is None or not room.full:
        await send(ws, "error", {"message": "You are not in this room."})
        return

    room.rematch_votes.add(symbol)

    # Only the player who requested the rematch should see the waiting state.
    # The opponent receives an actionable invitation instead.
    opponent = room.player_o if symbol == "X" else room.player_x
    await send(ws, "rematch_waiting", {
        "player": symbol,
        "waiting_for": "O" if symbol == "X" else "X",
    })
    await send(opponent, "rematch_requested", {
        "player": symbol,
    })

    if room.rematch_votes == {"X", "O"}:
        room.board = [""] * 9
        room.starting_player = "O" if room.starting_player == "X" else "X"
        room.turn = room.starting_player
        room.round_active = True
        room.rematch_votes.clear()
        start_turn_timer(room)
        await broadcast(room, "rematch_started", {
            "board": room.board,
            "turn": room.turn,
            "starting_player": room.starting_player,
        })


async def handle_chat(ws, data):
    code = data.get("code")
    text = data.get("message")
    if not isinstance(code, str) or not isinstance(text, str):
        await send(ws, "error", {"message": "Invalid chat message."})
        return
    room = ROOMS.get(code.strip().upper())
    if room is None:
        await send(ws, "error", {"message": "Room not found."})
        return
    symbol = room.symbol_for(ws)
    if symbol is None:
        await send(ws, "error", {"message": "You are not in this room."})
        return
    text = text.strip()[:300]
    if text:
        await broadcast(room, "chat_message", {"player": symbol, "message": text})


async def handle_move(ws, data):
    code = data.get("code")
    index = data.get("index")

    if not isinstance(code, str):
        await send(ws, "error", {"message": "Invalid room code."})
        return

    room = ROOMS.get(code.strip().upper())

    if room is None:
        await send(ws, "error", {"message": "Room not found."})
        return

    if not room.full:
        await send(ws, "error", {"message": "Waiting for opponent."})
        return

    player = room.symbol_for(ws)

    if player is None:
        await send(ws, "error", {
            "message": "You are not a player in this room.",
        })
        return

    if not room.round_active:
        await send(ws, "error", {"message": "Round is over."})
        return

    if player != room.turn:
        await send(ws, "error", {"message": "Not your turn."})
        return

    if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < 9:
        await send(ws, "error", {"message": "Invalid board position."})
        return

    if room.board[index]:
        await send(ws, "error", {
            "message": "That position is already occupied.",
        })
        return

    room.board[index] = player
    cancel_turn_timer(room)

    winner, condition = check_result(room.board)

    # The current frontend optimistically draws its own move, so receiving
    # the same move back is harmless: its cell is already occupied.
    await broadcast(
        room,
        "game_move",
        {
            "index": index,
            "player": player,
        },
    )

    if winner == "TIE":
        room.round_active = False
        await broadcast(
            room,
            "game_tie",
            {
                "winner": "TIE",
                "condition": [],
                "index": index,
                "player": player,
            },
        )
        return

    if winner in ("X", "O"):
        room.round_active = False
        await broadcast(
            room,
            "game_win",
            {
                "winner": winner,
                "condition": condition,
                "index": index,
                "player": player,
            },
        )
        return

    room.turn = "O" if player == "X" else "X"

    await broadcast(
        room,
        "turn_switch",
        {"player": room.turn},
    )

    start_turn_timer(room)


async def remove_player(ws, code, room):
    symbol = room.symbol_for(ws)

    if symbol is None:
        return

    was_active = room.round_active

    # A room is single-use: once either player leaves, invalidate the room.
    # This prevents a later player from joining an abandoned room code.
    cancel_turn_timer(room)
    ROOMS.pop(code, None)

    remaining = room.player_o if symbol == "X" else room.player_x

    if symbol == "X":
        room.player_x = None
    else:
        room.player_o = None

    logger.info("Player %s disconnected from room %s", symbol, code)

    if remaining is not None:
        await send(
            remaining,
            "opponent_disconnected" if was_active else "opponent_left",
            {"disconnected": symbol},
        )


async def disconnect_room(ws, code=None):
    found_code, room = find_room(ws)

    if found_code is None:
        return

    if code is not None and str(code).strip().upper() != found_code:
        return

    await remove_player(ws, found_code, room)


async def process_message(ws, raw_message):
    try:
        message = json.loads(raw_message)
    except (json.JSONDecodeError, TypeError):
        await send(ws, "error", {"message": "Invalid JSON."})
        return

    if not isinstance(message, dict):
        await send(ws, "error", {"message": "Invalid message."})
        return

    message_type = message.get("type")
    data = message.get("data") or {}
    print(f"RECEIVED MESSAGE: type={message_type!r}, data={data!r}", flush=True)

    if not isinstance(data, dict):
        await send(ws, "error", {"message": "Invalid message data."})
        return

    if message_type == "create_room":
        await create_room(ws)
    elif message_type == "join_room":
        await join_room(ws, data.get("code"))
    elif message_type == "game_move":
        await handle_move(ws, data)
    elif message_type == "chat_message":
        await handle_chat(ws, data)
    elif message_type == "rematch_request":
        await handle_rematch(ws, data)
    elif message_type == "disconnect_room":
        await disconnect_room(ws, data.get("code"))
    else:
        await send(ws, "error", {"message": "Unknown message type."})


# websockets 11.x passes (websocket, path). Keeping path optional also
# makes this easy to adapt when we upgrade the networking dependency.
async def handler(ws, path=None):
    logger.info("Client connected: %s", ws.remote_address)

    try:
        async for raw_message in ws:
            await process_message(ws, raw_message)
    except ConnectionClosed:
        pass
    except Exception:
        logger.exception("Unhandled client error")
    finally:
        code, room = find_room(ws)

        if code and room:
            await remove_player(ws, code, room)

        logger.info("Client disconnected: %s", ws.remote_address)


async def main():
    logger.info("Starting Tic-Tac-Toe WebSocket server on port %s", PORT)

    async with websockets.serve(
        handler,
        HOST,
        PORT,
        ping_interval=20,
        ping_timeout=20,
    ):
        logger.info(
            "WebSocket server listening on %s:%s",
            HOST,
            PORT,
        )
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())


