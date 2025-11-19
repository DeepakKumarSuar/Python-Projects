import js
from pyodide.ffi import create_proxy #type: ignore
import random
import asyncio

# --- Global Game State Variables ---
board = [""] * 9
current_player = "X"
game_active = False
mode = None  # 'single', 'local', or 'online'
ws = None # WebSocket connection
room_code = None
is_my_turn = False
my_player_symbol = "X"

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
x_label = document.getElementById("xLabel")
o_label = document.getElementById("oLabel")
game_title = document.getElementById("gameTitle")
status_text = document.getElementById("statusText")
turn_indicator = document.getElementById("turnIndicator")
thinking_animation = document.getElementById("thinkingAnimation")
celebration_div = document.getElementById("celebration")
wait_timer_display = document.getElementById("waitTimer") # Retained for matchmaking display

# Winning combinations
WINNING_CONDITIONS = [
    [0, 1, 2], [3, 4, 5], [6, 7, 8],
    [0, 3, 6], [1, 4, 7], [2, 5, 8],
    [0, 4, 8], [2, 4, 6]
]

# --- WebSocket Client Logic ---

async def connect_websocket():
    global ws
    if ws and ws.readyState == 1: # 1 means OPEN
        return
    
    # Constructing the WebSocket URL for the current host
    url ="wss://web-production-08d84.up.railway.app/play"
    
    ws = js.WebSocket.new(url)
    
    # Wait for the connection to open
    while ws.readyState == 0:  # CONNECTING
        await asyncio.sleep(0.1)
    
    if ws.readyState != 1: # OPEN
        js.console.error("WebSocket failed to connect.")
        return None
        
    ws.onmessage = create_proxy(handle_server_message)
    ws.onclose = create_proxy(lambda e: js.console.log("WebSocket Closed:", e))
    ws.onerror = create_proxy(lambda e: js.console.error("WebSocket Error:", e))
    
    return ws

async def send_to_server(type, data={}):
    if ws and ws.readyState == 1:
        message = js.JSON.stringify({'type': type, 'data': data})
        ws.send(message)

def handle_server_message(event):
    global room_code, my_player_symbol, is_my_turn, current_player, game_active
    
    try:
        msg = js.JSON.parse(event.data)
        msg_type = msg.type
        data = msg.data
    except Exception as e:
        js.console.error("Error parsing message:", e)
        return

    if msg_type == 'room_created':
        room_code = data.code
        my_player_symbol = 'X'
        matchmaking_status.textContent = f"Room created. Code: {room_code}. Waiting for Player O..."
        
    elif msg_type == 'opponent_joined':
        matchmaking_status.textContent = "Opponent joined! Starting Game..."
        game_active = True
        is_my_turn = True
        switch_screen('game')
        start_new_game()
        
    elif msg_type == 'room_joined':
        room_code = data.code
        my_player_symbol = 'O'
        matchmaking_status.textContent = "Joined game! Starting Game..."
        game_active = True
        is_my_turn = False
        switch_screen('game')
        start_new_game()
        
    elif msg_type == 'game_move':
        index = data.index
        player = data.player
        make_opponent_move(index, player)
        
    elif msg_type == 'turn_switch':
        current_player = data.player
        is_my_turn = (current_player == my_player_symbol)
        set_turn_display()
        if is_my_turn:
            start_move_timer()

    elif msg_type == 'game_win' or msg_type == 'game_tie':
        # Apply the final move if needed
        final_index = data.get('index')
        final_player = data.get('player')
        if final_index is not None and final_player:
            make_opponent_move(final_index, final_player)
            
        game_active = False
        cancel_timers()
        winner = data.get('winner')
        
        if winner:
            scores[winner] += 1
            update_scores()
            
            if msg_type == 'game_win':
                for index in data.condition:
                    cells[index].className += " winning"
                winner_name = x_label.textContent.split('(')[0].strip() if winner == 'X' else o_label.textContent.split('(')[0].strip()
                js.setTimeout(create_proxy(lambda: show_celebration(f"{winner_name} Wins!")), 500)
            else:
                js.setTimeout(create_proxy(lambda: show_celebration("It's a Tie!")), 500)
        
    elif msg_type == 'opponent_disconnected':
        handle_opponent_disconnect(data.disconnected)

    elif msg_type == 'error':
        js.alert(f"Error: {data.message}")
        matchmaking_status.textContent = "Error during connection. Try again."
        document.getElementById("connectBtn").disabled = False
        game_code_input.disabled = False

# --- Timer Logic ---
def cancel_timers():
    global move_timer_handle
    if move_timer_handle:
        js.clearTimeout(move_timer_handle)
        move_timer_handle = None
    wait_timer_display.textContent = ""

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
    global game_active
    game_active = False
    cancel_timers()
    
    if mode == 'online':
        # Send one last disconnect message just in case
        asyncio.ensure_future(send_to_server('disconnect_room', {'code': room_code}))
        
        if disconnected_player != my_player_symbol:
            scores[my_player_symbol] += 1
            update_scores()
            show_celebration(f"Opponent ({disconnected_player}) disconnected. You win by forfeit!")
        else:
            show_celebration(f"You disconnected.")


# --- UI Helper Functions ---
def set_player_labels():
    if mode == 'online':
        x_label.textContent = "You (X)" if my_player_symbol == 'X' else "Friend (X)"
        o_label.textContent = "You (O)" if my_player_symbol == 'O' else "Friend (O)"
        game_title.textContent = "Online vs Friend"
    elif mode == 'single':
        x_label.textContent = "You (X)"
        o_label.textContent = "Computer (O)"
        game_title.textContent = "You vs Computer"
    else:
        x_label.textContent = "Player 1 (X)"
        o_label.textContent = "Player 2 (O)"
        game_title.textContent = "Two Players (Local)"

def switch_screen(target):
    mode_selection_screen.className = "screen"
    matchmaking_screen.className = "screen"
    game_screen.className = "screen"
    
    cancel_timers()
    
    if target == 'mode_selection':
        mode_selection_screen.className = "screen active"
        # Cleanup online connection
        if ws and ws.readyState == 1:
            asyncio.ensure_future(send_to_server('disconnect_room', {'code': room_code}))
        
    elif target == 'matchmaking':
        matchmaking_screen.className = "screen active"
        matchmaking_status.textContent = "Ready to connect..."
        game_code_input.disabled = False
        document.getElementById("connectBtn").disabled = False
    elif target == 'game':
        game_screen.className = "screen active"

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

def show_celebration(message):
    celebration_div.innerHTML = f"""
        <div class="celebration-content">
            <i class="fas fa-trophy celebration-icon"></i>
            <h2>{message}</h2>
            <div class="action-buttons" style="margin-top: 20px;">
                <button id="nextRoundBtn" class="action-btn new-game" style="margin: 0;">Next Round</button>
            </div>
            <div class="confetti">
                <div class="confetti-piece"></div>
                <div class="confetti-piece"></div>
                <div class="confetti-piece"></div>
                <div class="confetti-piece"></div>
                <div class="confetti-piece"></div>
            </div>
        </div>
    """
    
    document.getElementById("nextRoundBtn").addEventListener("click", create_proxy(start_new_game))
    celebration_div.className = "celebration"

def hide_celebration():
    celebration_div.className = "celebration hidden"

def reset_board_ui():
    for i in range(9):
        cells[i].textContent = ""
        cells[i].className = "cell"
        cells[i].disabled = False

def start_new_game(event=None):
    global board, current_player, game_active, is_my_turn
    
    hide_celebration()
    reset_board_ui()
    
    board = [""] * 9
    current_player = "X"
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
            js.setTimeout(create_proxy(lambda: show_celebration(f"{winner_name} Wins!")), 500)
            return True
    
    if "" not in board:
        game_active = False
        scores["TIE"] += 1
        update_scores()
        js.setTimeout(create_proxy(lambda: show_celebration("It's a Tie!")), 500)
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
async def start_matchmaking_async():
    global room_code
    
    code_str = game_code_input.value
    if not code_str:
        matchmaking_status.textContent = "Error: Please enter a code."
        return
    
    try:
        code = int(code_str)
    except ValueError:
        matchmaking_status.textContent = "Error: Code must be a number."
        return
    
    if code < 0 or code > 100:
        # Using the game code as a request type (join/create) is clearer with WebSockets
        js.alert("Please use a code between 0 and 100.")
        return
    
    document.getElementById("connectBtn").disabled = True
    game_code_input.disabled = True
    
    matchmaking_status.textContent = "Connecting to server..."
    
    if not await connect_websocket():
        matchmaking_status.textContent = "Connection failed. Try refreshing."
        document.getElementById("connectBtn").disabled = False
        game_code_input.disabled = False
        return
        
    room_code = code # Temporarily store to decide join/create
    
    if room_code == 0:
        # Create a new room (Player X)
        matchmaking_status.textContent = "Requesting new room..."
        await send_to_server('create_room', {})
    else:
        # Join existing room (Player O)
        matchmaking_status.textContent = f"Attempting to join room {room_code}..."
        await send_to_server('join_room', {'code': room_code})

def start_matchmaking(event):
    asyncio.ensure_future(start_matchmaking_async())

# --- Event Listeners Setup ---
def setup_event_listeners():
    document.getElementById("singlePlayerBtn").addEventListener("click", create_proxy(lambda e: select_mode('single')))
    document.getElementById("onlineFriendBtn").addEventListener("click", create_proxy(lambda e: switch_screen('matchmaking')))
    document.getElementById("localTwoPlayerBtn").addEventListener("click", create_proxy(lambda e: select_mode('local')))
    
    document.getElementById("connectBtn").addEventListener("click", create_proxy(start_matchmaking))
    document.getElementById("matchmakingBackBtn").addEventListener("click", create_proxy(lambda e: switch_screen('mode_selection')))
    
    document.getElementById("backBtn").addEventListener("click", create_proxy(lambda e: switch_screen('mode_selection')))
    document.getElementById("newGameBtn").addEventListener("click", create_proxy(start_new_game))
    document.getElementById("resetScoresBtn").addEventListener("click", create_proxy(reset_all_scores))
    
    for cell in cells:
        cell.addEventListener("click", create_proxy(handle_cell_click))

# --- Initialize Game ---
setup_event_listeners()
update_scores()
print("Tic-Tac-Toe loaded successfully!")








