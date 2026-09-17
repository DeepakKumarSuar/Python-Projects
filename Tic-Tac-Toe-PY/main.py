import js
from pyodide.ffi import create_proxy #type: ignore
import random
import asyncio
import json

# --- Global Game State Variables ---
board = [""] * 9
current_player = "X"
game_active = False
mode = None  # 'single', 'local', or 'online'
ws = None # WebSocket connection
room_code = None
is_my_turn = False
my_player_symbol = "X"
rematch_waiting = False

# Timer handles
move_timer_handle = None

# Score tracking
scores = {"X": 0, "O": 0, "TIE": 0}

# HTML Elements
document = js.document
cells = [document.querySelector(f'[data-index="{i}"]') for i in range(9)]
mode_selection_screen = document.getElementById("modeSelection")
matchmaking_screen = document.getElementById("matchmakingScreen")
game_screen = document.getElementById("gameScreen")
game_code_input = document.getElementById("gameCodeInput")
matchmaking_status = document.getElementById("matchmakingStatus")
room_choice = document.getElementById("roomChoice")
create_room_panel = document.getElementById("createRoomPanel")
join_room_panel = document.getElementById("joinRoomPanel")
create_room_btn = document.getElementById("createRoomBtn")
join_room_btn = document.getElementById("joinRoomBtn")
copy_link_btn = document.getElementById("copyLinkBtn")
room_code_display = document.getElementById("roomCodeDisplay")
invite_link_display = document.getElementById("inviteLinkDisplay")
join_status = document.getElementById("joinStatus")
x_label = document.getElementById("xLabel")
o_label = document.getElementById("oLabel")
game_title = document.getElementById("gameTitle")
status_text = document.getElementById("statusText")
turn_indicator = document.getElementById("turnIndicator")
thinking_animation = document.getElementById("thinkingAnimation")
celebration_div = document.getElementById("celebration")
chat_panel = document.getElementById("onlineChat")
chat_toggle = document.getElementById("chatToggle")
chat_badge = document.getElementById("chatBadge")
chat_messages = document.getElementById("chatMessages")
chat_input = document.getElementById("chatInput")
send_chat_btn = document.getElementById("sendChatBtn")
local_actions = document.getElementById("localActions")

# Winning combinations
WINNING_CONDITIONS = [
    [0, 1, 2], [3, 4, 5], [6, 7, 8],
    [0, 3, 6], [1, 4, 7], [2, 5, 8],
    [0, 4, 8], [2, 4, 6]
]

# --- WebSocket Client Logic ---

async def connect_websocket():
    global ws

    if ws and ws.readyState == 1:
        return ws

    url = "ws://127.0.0.1:8080"

    ws = js.WebSocket.new(url)

    # wait until open
    while ws.readyState == 0:
        await asyncio.sleep(0.1)

    if ws.readyState != 1:
        js.console.error("WebSocket failed to connect.")
        return None

    ws.onmessage = create_proxy(handle_server_message)
    ws.onclose = create_proxy(lambda e: js.console.log("WS Closed"))
    ws.onerror = create_proxy(lambda e: js.console.error("WS Error"))

    return ws

async def send_to_server(message_type, data=None):
    """Send a properly formatted JSON message to the WebSocket server."""
    if data is None:
        data = {}

    if ws and ws.readyState == 1:
        message = {
            "type": str(message_type),
            "data": data
        }

        json_message = json.dumps(message)
        js.console.log(f"Sending WebSocket message: {json_message}")
        ws.send(json_message)
    else:
        js.console.error("WebSocket is not connected.")

def show_created_room(code):
    room_code_display.textContent = code

    current_url = str(js.window.location.href)
    base_url = current_url.split("?")[0].split("#")[0]
    invite_link = f"{base_url}?room={code}"

    invite_link_display.textContent = invite_link
    room_choice.className = "hidden"
    create_room_panel.className = ""
    join_room_panel.className = "hidden"
    matchmaking_status.textContent = "Waiting for your friend to join..."


def show_room_choice():
    room_choice.className = ""
    create_room_panel.className = "hidden"
    join_room_panel.className = "hidden"
    matchmaking_status.textContent = ""


async def copy_invite_link(event=None):
    link = str(invite_link_display.textContent).strip()

    if not link:
        return

    try:
        await js.navigator.clipboard.writeText(link)
        copy_link_btn.innerHTML = '<i class="fas fa-check"></i> Link Copied!'

        def reset_copy_button():
            copy_link_btn.innerHTML = '<i class="fas fa-copy"></i> Copy Link'

        js.setTimeout(create_proxy(reset_copy_button), 2000)

    except Exception:
        js.alert("Unable to copy the invite link. Please copy it manually.")


def handle_server_message(event):
    global room_code, my_player_symbol, is_my_turn, current_player, game_active

    try:
        # Convert the JavaScript WebSocket payload into normal Python data.
        # This avoids JsProxy/.get() issues that can silently stop result handling.
        msg = json.loads(str(event.data))
        msg_type = msg.get("type")
        data = msg.get("data") or {}
    except Exception as e:
        js.console.error("Error parsing message:", e)
        return

    if msg_type == 'room_created':
        room_code = data.get('code')
        my_player_symbol = 'X'
        show_created_room(room_code)

    elif msg_type == 'opponent_joined':
        matchmaking_status.textContent = "Opponent joined! Starting Game..."
        game_active = True
        is_my_turn = True
        switch_screen('game')
        start_new_game()

    elif msg_type == 'room_joined':
        room_code = data.get('code')
        my_player_symbol = 'O'
        matchmaking_status.textContent = "Joined game! Starting Game..."
        game_active = True
        is_my_turn = False
        switch_screen('game')
        start_new_game()

    elif msg_type == 'game_move':
        index = int(data.get('index'))
        player = data.get('player')
        make_opponent_move(index, player)

    elif msg_type == 'turn_switch':
        current_player = data.get('player')
        is_my_turn = (current_player == my_player_symbol)
        set_turn_display()
        if is_my_turn:
            start_move_timer()

    elif msg_type == 'game_win' or msg_type == 'game_tie':
        final_index = data.get('index')
        final_player = data.get('player')
        if final_index is not None and final_player:
            make_opponent_move(int(final_index), final_player)

        game_active = False
        cancel_timers()
        winner = data.get('winner')

        if winner == 'TIE' or msg_type == 'game_tie':
            scores['TIE'] += 1
            update_scores()
            show_celebration("It's a Tie!", online_result=True)
        elif winner in ('X', 'O'):
            scores[winner] += 1
            update_scores()
            for index in data.get('condition') or []:
                cells[int(index)].className += " winning"
            winner_name = "You" if winner == my_player_symbol else "Friend"
            show_celebration(f"{winner_name} won!", online_result=True)

    elif msg_type == 'rematch_waiting':
        global rematch_waiting
        rematch_waiting = True
        show_celebration("Waiting for opponent to accept rematch...", waiting=True)

    elif msg_type == 'rematch_requested':
        rematch_waiting = False
        show_celebration("Opponent wants a rematch!", online_result=True)

    elif msg_type == 'rematch_started':
        rematch_waiting = False
        start_new_game(starting_player=data.get('turn', 'X'))

    elif msg_type == 'opponent_disconnected':
        handle_opponent_disconnect(data.get('disconnected'))

    elif msg_type == 'opponent_left':
        if mode != 'online' or not room_code:
            return
        game_active = False
        cancel_timers()
        rematch_waiting = False
        show_celebration("Opponent left the room.", action_label="Back to Home", action_callback=go_home, online_result=False)

    elif msg_type == 'chat_message':
        add_chat_message(data.get("player"), data.get("message"))

    elif msg_type == 'error':
        error_message = data.get('message', 'Unknown error')
        if mode == 'online' and room_code and error_message == 'Room not found.':
            game_active = False
            rematch_waiting = False
            cancel_timers()
            show_celebration("Opponent left the room.", action_label="Back to Home", action_callback=go_home, online_result=False)
            return
        js.alert(f"Error: {error_message}")
        if join_room_panel.className != "hidden":
            join_status.textContent = f"Error: {data.get('message', 'Unknown error')}"
        else:
            matchmaking_status.textContent = f"Error: {data.get('message', 'Unknown error')}"
        reset_matchmaking_controls()
        game_code_input.disabled = False

# --- Timer Logic ---
def cancel_timers():
    global move_timer_handle
    if move_timer_handle:
        js.clearTimeout(move_timer_handle)
        move_timer_handle = None

def update_move_timer(remaining_seconds):
    global move_timer_handle
    if move_timer_handle: js.clearTimeout(move_timer_handle)

    if remaining_seconds > 0 and game_active:
        display_text = ""
        if mode == 'online':
            display_text = f"Your turn ({my_player_symbol}) - {remaining_seconds}s left" if is_my_turn else "Opponent's turn"
        else:
            display_text = f"{current_player}'s turn - {remaining_seconds}s left"

        status_text.textContent = display_text

        move_timer_handle = js.setTimeout(
            create_proxy(lambda: update_move_timer(remaining_seconds - 1)),
            1000
        )
    else:
        handle_move_timeout()

def start_move_timer():
    if game_active and (mode != 'online' or is_my_turn):
        update_move_timer(30)

def handle_move_timeout():
    global game_active

    if mode == 'online' and is_my_turn:
        js.alert("Time's up! You lose this round.")
        asyncio.ensure_future(send_to_server('disconnect_room', {'code': room_code}))
        game_active = False
        switch_screen('mode_selection')
    elif mode == 'local':
        js.alert(f"{current_player}'s time ran out! Game over.")
        # Optionally end game or choose random move for local timeout
        game_active = False

def handle_opponent_disconnect(disconnected_player):
    global game_active, room_code
    # Ignore stale disconnect notifications after this client has already
    # returned to the homepage or left the room.
    if mode != 'online' or not room_code:
        return
    game_active = False
    cancel_timers()

    if mode == 'online':
        if disconnected_player != my_player_symbol:
            if room_code:
                scores[my_player_symbol] += 1
                update_scores()
            show_celebration(
                f"Opponent ({disconnected_player}) disconnected.<br>You win by forfeit!",
                action_label="Back to Home",
                action_callback=go_home,
                online_result=False,
            )
        else:
            show_celebration(
                "You left the room.",
                action_label="Back to Home",
                action_callback=go_home,
                online_result=False,
            )


def go_home(event=None):
    global room_code, rematch_waiting, mode, game_active, is_my_turn
    hide_celebration()
    rematch_waiting = False
    game_active = False
    is_my_turn = False
    room_code = None
    mode = None
    switch_screen('mode_selection')


def exit_online_game(event=None):
    global room_code, game_active, mode
    code = room_code
    if mode == 'online' and code:
        asyncio.ensure_future(send_to_server('disconnect_room', {'code': code}))
    game_active = False
    # Clear local room state immediately so later/stale server messages cannot
    # display a result popup on the homepage.
    go_home()


def request_rematch(event=None):
    global rematch_waiting
    if mode != 'online' or not room_code or rematch_waiting:
        return
    rematch_waiting = True
    show_celebration("Waiting for opponent to accept rematch...", waiting=True)
    asyncio.ensure_future(send_to_server('rematch_request', {'code': room_code}))


def add_chat_message(player, message):
    if not message:
        return

    # Keep only the six newest messages.
    while chat_messages.children.length >= 6:
        chat_messages.removeChild(chat_messages.firstElementChild)

    item = document.createElement("div")
    item.className = "chat-message own" if player == my_player_symbol else "chat-message opponent"

    body = document.createElement("div")
    body.className = "chat-message-body"
    body.textContent = str(message)

    time_label = document.createElement("span")
    time_label.className = "chat-time"
    time_label.textContent = js.Date.new().toLocaleTimeString([], {"hour": "2-digit", "minute": "2-digit"})

    item.appendChild(body)
    item.appendChild(time_label)
    chat_messages.appendChild(item)
    chat_messages.scrollTop = chat_messages.scrollHeight

    # A new incoming message briefly highlights the floating chat button.
    if player != my_player_symbol and chat_panel.className == "online-chat hidden":
        chat_toggle.classList.add("has-new-message")
        chat_badge.textContent = "1"
        js.setTimeout(create_proxy(lambda: chat_toggle.classList.remove("has-new-message")), 10000)


async def toggle_chat(event=None):
    if mode != "online":
        return
    if chat_panel.className == "online-chat hidden":
        chat_panel.className = "online-chat"
        chat_badge.textContent = ""
        chat_toggle.classList.remove("has-new-message")
    else:
        chat_panel.className = "online-chat hidden"


async def send_chat(event=None):
    text = str(chat_input.value).strip()
    if not text or mode != 'online' or not room_code:
        return
    await send_to_server('chat_message', {'code': room_code, 'message': text})
    chat_input.value = ""


# --- UI Helper Functions ---
def set_player_labels():
    if mode == 'online':
        x_label.textContent = "You (X)" if my_player_symbol == 'X' else "Friend (X)"
        o_label.textContent = "You (O)" if my_player_symbol == 'O' else "Friend (O)"
        game_title.textContent = "Private Match"
    elif mode == 'single':
        x_label.textContent = "You (X)"
        o_label.textContent = "Computer (O)"
        game_title.textContent = "You vs Computer"
    else:
        x_label.textContent = "Player 1 (X)"
        o_label.textContent = "Player 2 (O)"
        game_title.textContent = "Two Players (Local)"

def switch_screen(target):
    global room_code
    mode_selection_screen.className = "screen"
    matchmaking_screen.className = "screen"
    game_screen.className = "screen"

    cancel_timers()

    if target == 'mode_selection':
        mode_selection_screen.className = "screen active"
        # Explicitly close the online room when leaving it.
        if mode == 'online' and ws and ws.readyState == 1 and room_code:
            asyncio.ensure_future(send_to_server('disconnect_room', {'code': room_code}))
        room_code = None

    elif target == 'matchmaking':
        matchmaking_screen.className = "screen active"
        show_room_choice()
        reset_matchmaking_controls()
    elif target == 'game':
        game_screen.className = "screen active"
        online = (mode == 'online')
        chat_panel.className = "online-chat hidden" if online else "online-chat hidden"
        chat_toggle.className = "chat-toggle" if online else "chat-toggle hidden"
        chat_badge.textContent = ""
        local_actions.className = "action-buttons hidden" if online else "action-buttons"

def update_scores():
    document.getElementById("xScore").textContent = str(scores["X"])
    document.getElementById("oScore").textContent = str(scores["O"])
    document.getElementById("tieScore").textContent = str(scores["TIE"])

def set_turn_display():
    if not game_active: return

    if mode == 'single' and current_player == 'O':
        status_text.textContent = "Computer's turn (O)"
        turn_indicator.className = "turn-indicator o-turn"
    elif mode == 'online':
        if is_my_turn:
            status_text.textContent = f"Your turn ({my_player_symbol})"
            turn_indicator.className = f"turn-indicator {my_player_symbol.lower()}-turn"
        else:
            status_text.textContent = "Opponent's turn"
            indicator_symbol = 'X' if my_player_symbol == 'O' else 'O'
            turn_indicator.className = f"turn-indicator {indicator_symbol.lower()}-turn"
    elif current_player == 'X':
        status_text.textContent = "Player 1's turn (X)"
        turn_indicator.className = "turn-indicator x-turn"
    else:
        status_text.textContent = "Player 2's turn (O)"
        turn_indicator.className = "turn-indicator o-turn"

def show_thinking(show):
    thinking_animation.className = "thinking-animation" if show else "thinking-animation hidden"

def show_celebration(message, action_label=None, action_callback=None, online_result=False, waiting=False):
    if waiting and mode == 'online':
        celebration_div.innerHTML = f"""
            <div class="celebration-content">
                <i class="fas fa-hourglass-half celebration-icon"></i>
                <h2>{message}</h2>
                <div class="action-buttons" style="margin-top: 20px;">
                    <button id="celebrationWaitingExitBtn" class="action-btn reset-scores" style="margin: 0;">Exit Room</button>
                </div>
            </div>
        """
        document.getElementById("celebrationWaitingExitBtn").addEventListener("click", create_proxy(exit_online_game))
    elif online_result and mode == 'online':
        action_label = "Back to Home" if waiting else None
        action_callback = go_home if waiting else None

    if mode == 'online' and online_result and not waiting:
        safe_message = message
        celebration_div.innerHTML = f"""
            <div class="celebration-content">
                <i class="fas fa-trophy celebration-icon"></i>
                <h2>{safe_message}</h2>
                <div class="action-buttons" style="margin-top: 20px; display:flex; gap:12px; justify-content:center;">
                    <button id="celebrationRematchBtn" class="action-btn new-game" style="margin:0;">Rematch</button>
                    <button id="celebrationExitBtn" class="action-btn reset-scores" style="margin:0;">Exit</button>
                </div>
            </div>
        """
        document.getElementById("celebrationRematchBtn").addEventListener("click", create_proxy(request_rematch))
        document.getElementById("celebrationExitBtn").addEventListener("click", create_proxy(exit_online_game))
    else:
        if action_label is None:
            action_label = "Back to Home" if mode == 'online' else "Next Round"
            action_callback = go_home if mode == 'online' else start_new_game
        celebration_div.innerHTML = f"""
            <div class="celebration-content">
                <i class="fas fa-trophy celebration-icon"></i>
                <h2>{message}</h2>
                <div class="action-buttons" style="margin-top: 20px;">
                    <button id="celebrationActionBtn" class="action-btn new-game" style="margin: 0;">{action_label}</button>
                </div>
            </div>
        """
        document.getElementById("celebrationActionBtn").addEventListener("click", create_proxy(action_callback))

    celebration_div.className = "celebration"


def hide_celebration():
    celebration_div.className = "celebration hidden"

def reset_board_ui():
    for i in range(9):
        cells[i].textContent = ""
        cells[i].className = "cell"
        cells[i].disabled = False

def start_new_game(event=None, starting_player=None):
    global board, current_player, game_active, is_my_turn

    hide_celebration()
    reset_board_ui()
    chat_messages.innerHTML = ""

    board = [""] * 9
    current_player = starting_player if starting_player in ("X", "O") else "X"
    game_active = True

    set_player_labels()
    cancel_timers()

    if mode == 'online':
        is_my_turn = (current_player == my_player_symbol)
        if is_my_turn:
            start_move_timer()
        else:
            pass # Opponent's turn, wait for message
    elif mode == 'local':
        start_move_timer()

    set_turn_display()

    if mode == 'single' and current_player == 'O':
        js.setTimeout(create_proxy(computer_move), 1000)

def reset_all_scores(event=None):
    global scores
    scores = {"X": 0, "O": 0, "TIE": 0}
    update_scores()
    start_new_game()

def select_mode(selected_mode):
    global mode, game_active
    mode = selected_mode
    game_active = True
    set_player_labels()
    switch_screen('game')
    reset_all_scores()


def enter_online_mode(event=None):
    global mode, game_active, room_code
    mode = 'online'
    game_active = False
    room_code = None
    switch_screen('matchmaking')

# --- Core Game Logic ---
def check_win_local():
    global game_active

    for condition in WINNING_CONDITIONS:
        a, b, c = condition
        if board[a] and board[a] == board[b] and board[a] == board[c]:
            game_active = False
            winner = board[a]
            scores[winner] += 1
            update_scores()

            for index in condition: cells[index].className += " winning"

            winner_name = x_label.textContent.split('(')[0].strip() if winner == 'X' else o_label.textContent.split('(')[0].strip()
            show_celebration(f"{winner_name} Wins!")
            return True

    if "" not in board:
        game_active = False
        scores["TIE"] += 1
        update_scores()
        show_celebration("It's a Tie!")
        return True

    return False

def next_turn():
    global current_player
    if not game_active: return

    current_player = "O" if current_player == "X" else "X"
    set_turn_display()

    if mode == 'single' and current_player == 'O':
        js.setTimeout(create_proxy(computer_move), 1000)
    elif mode == 'local':
        start_move_timer()

def handle_cell_click(event):
    global board, game_active, current_player

    if not game_active: return

    target = event.currentTarget
    clicked_index = int(target.getAttribute('data-index'))

    if board[clicked_index] != "": return

    player_to_move = current_player

    if mode == 'online':
        if not is_my_turn or player_to_move != my_player_symbol: return

        # Online move
        board[clicked_index] = player_to_move
        target.textContent = player_to_move
        target.className += f" {player_to_move.lower()}"
        target.disabled = True

        cancel_timers()
        asyncio.ensure_future(send_to_server('game_move', {'code': room_code, 'index': clicked_index, 'player': player_to_move}))

    else:
        # Single or Local move
        board[clicked_index] = player_to_move
        target.textContent = player_to_move
        target.className += f" {player_to_move.lower()}"
        target.disabled = True

        if not check_win_local():
            next_turn()

def make_opponent_move(index, player):
    global board, current_player

    if board[index] != "": return

    board[index] = player
    cell = cells[index]
    cell.textContent = player
    cell.className += f" {player.lower()}"
    cell.disabled = True

    # Do NOT call check_win_local() or next_turn() here, the server will send win/tie/turn_switch messages.

# --- Computer AI Logic ---
def get_empty_cells():
    return [i for i, val in enumerate(board) if val == ""]

def computer_move():
    show_thinking(True)
    js.setTimeout(create_proxy(lambda: execute_ai_move()), 500)

def execute_ai_move():
    empty_cells = get_empty_cells()

    # AI logic (O)
    def find_best_move(player):
        for i in empty_cells:
            board[i] = player
            for condition in WINNING_CONDITIONS:
                a, b, c = condition
                if board[a] == board[b] == board[c] == player:
                    board[i] = ''
                    return i
            board[i] = ''
        return None

    # 1. Try to win (O)
    move = find_best_move('O')
    if move is not None:
        make_move(move, 'O')
        show_thinking(False)
        return

    # 2. Try to block (X)
    move = find_best_move('X')
    if move is not None:
        make_move(move, 'O')
        show_thinking(False)
        return

    # 3. Center
    if 4 in empty_cells:
        make_move(4, 'O')
        show_thinking(False)
        return

    # 4. Corners
    corners = [0, 2, 6, 8]
    available_corners = [c for c in corners if c in empty_cells]
    if available_corners:
        move_index = random.choice(available_corners)
        make_move(move_index, 'O')
        show_thinking(False)
        return

    # 5. Edges
    if empty_cells:
        move_index = random.choice(empty_cells)
        make_move(move_index, 'O')

    show_thinking(False)

def make_move(index, player):
    global board

    board[index] = player
    cell = cells[index]
    cell.textContent = player
    cell.className += f" {player.lower()}"
    cell.disabled = True

    if not check_win_local():
        next_turn()

# --- Online Matchmaking ---
async def create_room(event=None):
    global room_code

    create_room_btn.disabled = True
    join_room_btn.disabled = True
    matchmaking_status.textContent = "Connecting to server..."

    if not await connect_websocket():
        matchmaking_status.textContent = "Connection failed. Try refreshing."
        create_room_btn.disabled = False
        join_room_btn.disabled = False
        return

    room_code = None
    matchmaking_status.textContent = "Creating room..."
    await send_to_server('create_room', {})


def show_join_room_panel(event=None):
    room_choice.className = "hidden"
    create_room_panel.className = "hidden"
    join_room_panel.className = ""

    game_code_input.value = ""
    game_code_input.disabled = False
    join_room_btn.disabled = False
    join_status.textContent = "Enter your friend's room code."


async def join_room(event=None):
    global room_code

    code = str(game_code_input.value).strip().upper()

    if not code:
        join_status.textContent = "Please enter a room code."
        return

    if len(code) != 6 or not code.isalnum():
        join_status.textContent = "Please enter a valid 6-character room code."
        return

    join_room_btn.disabled = True
    game_code_input.disabled = True
    create_room_btn.disabled = True
    join_status.textContent = "Connecting to server..."

    if not await connect_websocket():
        join_status.textContent = "Connection failed. Try refreshing."
        join_room_btn.disabled = False
        game_code_input.disabled = False
        create_room_btn.disabled = False
        return

    room_code = code
    join_status.textContent = "Joining room..."
    await send_to_server('join_room', {'code': code})


def reset_matchmaking_controls():
    create_room_btn.disabled = False
    join_room_btn.disabled = False
    game_code_input.disabled = False


# --- Event Listeners Setup ---
def setup_event_listeners():
    document.getElementById("singlePlayerBtn").addEventListener(
        "click",
        create_proxy(lambda e: select_mode('single'))
    )

    document.getElementById("onlineFriendBtn").addEventListener(
        "click",
        create_proxy(enter_online_mode)
    )

    document.getElementById("localTwoPlayerBtn").addEventListener(
        "click",
        create_proxy(lambda e: select_mode('local'))
    )

    create_room_btn.addEventListener(
        "click",
        create_proxy(lambda e: asyncio.ensure_future(create_room(e)))
    )

    join_room_btn.addEventListener(
        "click",
        create_proxy(show_join_room_panel)
    )

    copy_link_btn.addEventListener(
        "click",
        create_proxy(copy_invite_link)
    )

    document.getElementById("connectBtn").addEventListener(
        "click",
        create_proxy(lambda e: asyncio.ensure_future(join_room(e)))
    )

    document.getElementById("matchmakingBackBtn").addEventListener(
        "click",
        create_proxy(lambda e: switch_screen('mode_selection'))
    )

    document.getElementById("backBtn").addEventListener(
        "click",
        create_proxy(exit_online_game)
    )

    document.getElementById("newGameBtn").addEventListener(
        "click",
        create_proxy(start_new_game)
    )

    document.getElementById("resetScoresBtn").addEventListener(
        "click",
        create_proxy(reset_all_scores)
    )

    send_chat_btn.addEventListener("click", create_proxy(send_chat))
    chat_toggle.addEventListener("click", create_proxy(toggle_chat))
    document.getElementById("closeChatBtn").addEventListener("click", create_proxy(toggle_chat))
    chat_input.addEventListener("keydown", create_proxy(lambda e: asyncio.ensure_future(send_chat()) if e.key == "Enter" else None))

    for cell in cells:
        cell.addEventListener(
            "click",
            create_proxy(handle_cell_click)
        )


# --- Invite-link auto join ---
async def auto_join_from_url():
    try:
        params = js.URLSearchParams.new(str(js.window.location.search))
        invite_code = params.get('room')
        if invite_code:
            enter_online_mode()
            show_join_room_panel()
            game_code_input.value = str(invite_code).strip().upper()
            await asyncio.sleep(0.2)
            await join_room()
    except Exception as e:
        js.console.error('Invite-link join failed:', e)


# --- Initialize Game ---
setup_event_listeners()
update_scores()
asyncio.ensure_future(auto_join_from_url())
print("Tic-Tac-Toe loaded successfully!")
