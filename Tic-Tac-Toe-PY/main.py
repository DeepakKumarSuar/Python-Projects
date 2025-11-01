import js
from pyodide.ffi import create_proxy #type:ignore
import random
import asyncio

# --- Global Game State Variables ---
board = [""] * 9
current_player = "X"
game_active = False
mode = None  # 'single', 'local', or 'online'

# Online mode state
is_connected = False
is_my_turn = False
my_player_symbol = "X"
game_code = None
waiting_for_opponent = False

# Timer handles
move_timer_handle = None
wait_timer_handle = None

# Score tracking
scores = {"X": 0, "O": 0, "TIE": 0}

# HTML Elements (Accessed via js)
document = js.document
cells = [document.querySelector(f'[data-index="{i}"]') for i in range(9)]
mode_selection_screen = document.getElementById("modeSelection")
matchmaking_screen = document.getElementById("matchmakingScreen")
game_screen = document.getElementById("gameScreen")
game_code_input = document.getElementById("gameCodeInput")
matchmaking_status = document.getElementById("matchmakingStatus")
wait_timer_display = document.getElementById("waitTimer")
x_label = document.getElementById("xLabel")
o_label = document.getElementById("oLabel")
game_title = document.getElementById("gameTitle")
status_text = document.getElementById("statusText")
turn_indicator = document.getElementById("turnIndicator")
thinking_animation = document.getElementById("thinkingAnimation")
celebration_div = document.getElementById("celebration")

# Winning combinations
WINNING_CONDITIONS = [
    [0, 1, 2], [3, 4, 5], [6, 7, 8],
    [0, 3, 6], [1, 4, 7], [2, 5, 8],
    [0, 4, 8], [2, 4, 6]
]

# --- Storage-based Online Play ---
async def save_game_state(code, state):
    """Save game state to persistent storage"""
    try:
        result = await js.window.storage.set(f"game:{code}", js.JSON.stringify(state), True)
        return result is not None
    except Exception as e:
        js.console.log(f"Storage error: {e}")
        return False

async def get_game_state(code):
    """Get game state from persistent storage"""
    try:
        result = await js.window.storage.get(f"game:{code}", True)
        if result and result.value:
            return js.JSON.parse(result.value)
        return None
    except Exception as e:
        js.console.log(f"Storage error: {e}")
        return None

async def delete_game_state(code):
    """Delete game state from storage"""
    try:
        await js.window.storage.delete(f"game:{code}", True)
    except Exception as e:
        js.console.log(f"Storage delete error: {e}")

async def poll_for_opponent():
    """Poll storage to check for opponent moves or disconnects"""
    global game_active, waiting_for_opponent, is_my_turn, current_player
    
    if not waiting_for_opponent or not game_active or mode != 'online':
        return
    
    try:
        state = await get_game_state(game_code)
        if state:
            # Check if opponent made a move
            if state.last_move and state.last_move.player != my_player_symbol:
                # Apply opponent's move
                move_index = state.last_move.index
                opponent_player = state.last_move.player
                
                board[move_index] = opponent_player
                cell = cells[move_index]
                cell.textContent = opponent_player
                cell.className = f"cell {opponent_player.lower()}"
                cell.disabled = True
                
                current_player = opponent_player
                check_result()
                
                waiting_for_opponent = False
                return
            
            # Check if opponent disconnected
            if state.disconnected and state.disconnected != my_player_symbol:
                handle_opponent_disconnect()
                return
        
        # Continue polling
        js.setTimeout(create_proxy(lambda: asyncio.ensure_future(poll_for_opponent())), 1000)
    except Exception as e:
        js.console.log(f"Poll error: {e}")

async def handle_online_move(index):
    """Send move to storage for online play"""
    global waiting_for_opponent, is_my_turn
    
    try:
        state = {
            'last_move': {
                'player': my_player_symbol,
                'index': index,
                'timestamp': js.Date.now()
            },
            'board': board,
            'disconnected': None
        }
        await save_game_state(game_code, state)
        
        is_my_turn = False
        waiting_for_opponent = True
        cancel_timers()
        
        # Start polling for opponent's move
        asyncio.ensure_future(poll_for_opponent())
    except Exception as e:
        js.console.log(f"Error sending move: {e}")

def handle_opponent_disconnect():
    """Handle when opponent quits"""
    global game_active
    
    game_active = False
    cancel_timers()
    
    opponent_symbol = 'X' if my_player_symbol == 'O' else 'O'
    scores[my_player_symbol] += 1
    update_scores()
    show_celebration(f"Opponent ({opponent_symbol}) quit. You win by forfeit!")

# --- Timer Logic ---
def cancel_timers():
    """Cancels all active timers"""
    global move_timer_handle, wait_timer_handle
    
    if move_timer_handle:
        js.clearTimeout(move_timer_handle)
        move_timer_handle = None
    if wait_timer_handle:
        js.clearTimeout(wait_timer_handle)
        wait_timer_handle = None
    
    wait_timer_display.textContent = ""

def update_move_timer(remaining_seconds):
    """Updates the move timer display"""
    global move_timer_handle
    
    if move_timer_handle:
        js.clearTimeout(move_timer_handle)
        move_timer_handle = None
    
    if remaining_seconds > 0 and game_active:
        if mode == 'online':
            status_text.textContent = f"Your turn ({my_player_symbol}) - {remaining_seconds}s left"
        else:
            status_text.textContent = f"{current_player}'s turn - {remaining_seconds}s left"
        
        move_timer_handle = js.setTimeout(
            create_proxy(lambda: update_move_timer(remaining_seconds - 1)), 
            1000
        )
    else:
        handle_move_timeout()

def start_move_timer():
    """Starts the 30-second timer for the current player's move"""
    if game_active:
        if mode == 'online' and is_my_turn:
            update_move_timer(30)
        elif mode == 'local':
            update_move_timer(30)

def handle_move_timeout():
    """Executed when a player runs out of time"""
    global board, is_my_turn
    
    empty_cells = get_empty_cells()
    if not empty_cells or not game_active:
        return
    
    # Randomly choose a move for the timed-out player
    move_index = random.choice(empty_cells)
    
    if mode == 'online':
        js.alert(f"Time's up! A random move was chosen for you.")
        # Make the random move
        board[move_index] = my_player_symbol
        cells[move_index].textContent = my_player_symbol
        cells[move_index].className = f"cell {my_player_symbol.lower()}"
        cells[move_index].disabled = True
        
        # Send to storage
        asyncio.ensure_future(handle_online_move(move_index))
        check_result()
    else:
        js.alert(f"{current_player}'s time ran out! A random move was chosen.")
        make_move(move_index, current_player)

# --- UI Helper Functions ---
def set_player_labels():
    """Sets player labels based on current mode"""
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
    """Handles switching between screens"""
    mode_selection_screen.className = "screen"
    matchmaking_screen.className = "screen"
    game_screen.className = "screen"
    
    cancel_timers()
    
    if target == 'mode_selection':
        mode_selection_screen.className = "screen active"
        # Clean up online game if exiting
        if mode == 'online' and game_code:
            asyncio.ensure_future(mark_disconnected())
    elif target == 'matchmaking':
        matchmaking_screen.className = "screen active"
        matchmaking_status.textContent = "Ready to connect..."
        game_code_input.disabled = False
        document.getElementById("connectBtn").disabled = False
    elif target == 'game':
        game_screen.className = "screen active"

async def mark_disconnected():
    """Mark player as disconnected in storage"""
    global game_code
    if game_code:
        try:
            state = await get_game_state(game_code)
            if state:
                state['disconnected'] = my_player_symbol
                await save_game_state(game_code, state)
        except Exception as e:
            js.console.log(f"Disconnect error: {e}")

def update_scores():
    """Updates score display"""
    document.getElementById("xScore").textContent = str(scores["X"])
    document.getElementById("oScore").textContent = str(scores["O"])
    document.getElementById("tieScore").textContent = str(scores["TIE"])

def set_turn_display():
    """Updates the status text and turn indicator"""
    if not game_active:
        return
    
    if mode == 'single' and current_player == 'O':
        status_text.textContent = "Computer's turn (O)"
        turn_indicator.className = "turn-indicator o-turn"
    elif mode == 'online':
        if is_my_turn:
            status_text.textContent = f"Your turn ({my_player_symbol})"
            turn_indicator.className = "turn-indicator x-turn" if my_player_symbol == 'X' else "turn-indicator o-turn"
        else:
            status_text.textContent = "Opponent's turn"
            # Show the symbol of the player whose turn it *is* according to current_player
            turn_indicator.className = "turn-indicator x-turn" if current_player == 'X' else "turn-indicator o-turn"
    elif current_player == 'X':
        status_text.textContent = "Player 1's turn (X)"
        turn_indicator.className = "turn-indicator x-turn"
    else:
        status_text.textContent = "Player 2's turn (O)"
        turn_indicator.className = "turn-indicator o-turn"

def show_thinking(show):
    """Toggle thinking animation"""
    if show:
        thinking_animation.className = "thinking-animation"
    else:
        thinking_animation.className = "thinking-animation hidden"

def show_celebration(message):
    """Display celebration screen with message"""
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
    
    document.getElementById("nextRoundBtn").addEventListener(
        "click", 
        create_proxy(start_new_game)
    )
    celebration_div.className = "celebration"

def hide_celebration():
    """Hide celebration screen"""
    celebration_div.className = "celebration hidden"

def reset_board_ui():
    """Reset all cells to empty state"""
    for i in range(9):
        cells[i].textContent = ""
        cells[i].className = "cell"
        cells[i].disabled = False

def start_new_game(event=None):
    """Start a new game round"""
    global board, current_player, game_active, is_my_turn, waiting_for_opponent
    
    hide_celebration()
    reset_board_ui()
    
    board = [""] * 9
    current_player = "X"
    game_active = True
    waiting_for_opponent = False
    
    set_player_labels()
    cancel_timers()
    
    if mode == 'single':
        set_turn_display()
    elif mode == 'online':
        is_my_turn = (current_player == my_player_symbol)
        if is_my_turn:
            start_move_timer()
        else:
            waiting_for_opponent = True
            asyncio.ensure_future(poll_for_opponent())
        set_turn_display()
    elif mode == 'local':
        start_move_timer()
        set_turn_display()

def reset_all_scores(event=None):
    """Reset all scores and start new game"""
    global scores
    scores = {"X": 0, "O": 0, "TIE": 0}
    update_scores()
    start_new_game()

def select_mode(selected_mode):
    """Sets the game mode and starts game"""
    global mode, game_active
    
    mode = selected_mode
    game_active = True
    
    set_player_labels()
    switch_screen('game')
    reset_all_scores()

# --- Core Game Logic ---
def check_result():
    """Check for win or tie"""
    global game_active
    
    # Check for win
    for condition in WINNING_CONDITIONS:
        a, b, c = condition
        if board[a] and board[a] == board[b] and board[a] == board[c]:
            game_active = False
            winner = board[a]
            scores[winner] += 1
            update_scores()
            
            for index in condition:
                cells[index].className += " winning"
            
            winner_name = x_label.textContent.split('(')[0].strip() if winner == 'X' else o_label.textContent.split('(')[0].strip()
            
            js.setTimeout(
                create_proxy(lambda: show_celebration(f"{winner_name} Wins!")), 
                500
            )
            return
    
    # Check for tie
    if "" not in board:
        game_active = False
        scores["TIE"] += 1
        update_scores()
        js.setTimeout(
            create_proxy(lambda: show_celebration("It's a Tie!")), 
            500
        )
        return
    
    # Switch turn
    next_turn()

def next_turn():
    """Switch to next player"""
    global current_player, is_my_turn
    
    current_player = "O" if current_player == "X" else "X"
    set_turn_display()
    
    if mode == 'single' and current_player == 'O' and game_active:
        js.setTimeout(create_proxy(computer_move), 1000)
    elif mode == 'online':
        is_my_turn = (current_player == my_player_symbol)
        if is_my_turn:
            start_move_timer()
        else:
            cancel_timers()
            waiting_for_opponent = True
            asyncio.ensure_future(poll_for_opponent())
    elif mode == 'local':
        start_move_timer()

def handle_cell_click(event):
    """Handle cell click event"""
    global board, game_active
    
    if not game_active:
        return
    
    target = event.currentTarget
    clicked_index = int(target.getAttribute('data-index'))
    
    # Check if move is allowed
    if mode == 'online' and not is_my_turn:
        return
    if mode == 'single' and current_player == 'O':
        return
    if board[clicked_index] != "":
        return
    
    # Make the move
    board[clicked_index] = current_player
    target.textContent = current_player
    target.className += f" {current_player.lower()}"
    target.disabled = True
    
    # Handle online mode
    if mode == 'online':
        asyncio.ensure_future(handle_online_move(clicked_index))
    
    # Check result
    check_result()

# --- Computer AI Logic ---
def get_empty_cells():
    """Return list of empty cell indices"""
    return [i for i, val in enumerate(board) if val == ""]

def computer_move():
    """AI makes a move"""
    show_thinking(True)
    js.setTimeout(create_proxy(lambda: execute_ai_move()), 500)

def execute_ai_move():
    """Execute the AI's chosen move"""
    empty_cells = get_empty_cells()
    
    # Try to win (O)
    for i in empty_cells:
        board[i] = 'O'
        for condition in WINNING_CONDITIONS:
            a, b, c = condition
            if board[a] == board[b] == board[c] == 'O':
                board[i] = ''
                make_move(i, 'O')
                show_thinking(False)
                return
        board[i] = ''
    
    # Try to block (X)
    for i in empty_cells:
        board[i] = 'X'
        for condition in WINNING_CONDITIONS:
            a, b, c = condition
            if board[a] == board[b] == board[c] == 'X':
                board[i] = ''
                make_move(i, 'O')
                show_thinking(False)
                return
        board[i] = ''
    
    # Random move
    if empty_cells:
        move_index = random.choice(empty_cells)
        make_move(move_index, 'O')
    
    show_thinking(False)

def make_move(index, player):
    """Execute a move on the board"""
    global board
    
    board[index] = player
    cell = cells[index]
    cell.textContent = player
    cell.className += f" {player.lower()}"
    cell.disabled = True
    
    check_result()

# --- Online Matchmaking ---
async def start_matchmaking_async():
    """Handle matchmaking connection"""
    global mode, game_code, my_player_symbol, is_my_turn, game_active, waiting_for_opponent
    
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
        matchmaking_status.textContent = "Error: Code must be 0-100."
        return
    
    game_code = code
    mode = 'online'
    game_code_input.disabled = True
    document.getElementById("connectBtn").disabled = True
    
    matchmaking_status.textContent = f"Connecting to game {code}..."
    
    # Check if game exists
    state = await get_game_state(game_code)
    
    if state and state.get('player1') and not state.get('player2'):
        # Join existing game as player 2 (O)
        my_player_symbol = 'O'
        state['player2'] = 'O'
        await save_game_state(game_code, state)
        
        matchmaking_status.textContent = "Match Found! Starting Game..."
        game_active = True
        is_my_turn = False
        waiting_for_opponent = True
        
        set_player_labels()
        switch_screen('game')
        start_new_game()
        
    elif not state or not state.get('player1'):
        # Create new game as player 1 (X)
        my_player_symbol = 'X'
        state = {
            'player1': 'X',
            'player2': None,
            'board': [""] * 9,
            'last_move': None,
            'disconnected': None
        }
        await save_game_state(game_code, state)
        
        matchmaking_status.textContent = f"Waiting for opponent with code {code}..."
        
        # Wait for opponent (simulate with timeout)
        await wait_for_opponent()
    else:
        matchmaking_status.textContent = "Error: Game is full or invalid."
        game_code_input.disabled = False
        document.getElementById("connectBtn").disabled = False

async def wait_for_opponent():
    """Wait for second player to join (FIXED LOGIC)"""
    global game_active, is_my_turn, waiting_for_opponent, current_player, my_player_symbol
    
    # 30-second timeout loop
    for i in range(30):
        await asyncio.sleep(1)
        wait_timer_display.textContent = f"Time remaining: {30 - i} seconds."
        
        state = await get_game_state(game_code)
        
        # Check for opponent join (player2)
        if state and state.get('player2'):
            # Opponent joined!
            matchmaking_status.textContent = "Match Found! Starting Game..."
            wait_timer_display.textContent = ""
            
            # Initialize Player 1 state correctly
            game_active = True
            my_player_symbol = 'X'
            current_player = 'X'
            is_my_turn = True
            waiting_for_opponent = False
            
            set_player_labels()
            switch_screen('game')
            start_new_game()
            return
            
    # Timeout logic
    matchmaking_status.textContent = "Matchmaking timed out. No opponent found."
    wait_timer_display.textContent = ""
    game_code_input.disabled = False
    document.getElementById("connectBtn").disabled = False
    await delete_game_state(game_code)

def start_matchmaking(event):
    """Wrapper for matchmaking"""
    asyncio.ensure_future(start_matchmaking_async())

# --- Event Listeners Setup ---
def setup_event_listeners():
    """Attach all event handlers"""
    
    # Mode selection buttons
    document.getElementById("singlePlayerBtn").addEventListener(
        "click", 
        create_proxy(lambda e: select_mode('single'))
    )
    
    document.getElementById("onlineFriendBtn").addEventListener(
        "click", 
        create_proxy(lambda e: switch_screen('matchmaking'))
    )
    
    document.getElementById("localTwoPlayerBtn").addEventListener(
        "click", 
        create_proxy(lambda e: select_mode('local'))
    )
    
    # Matchmaking buttons
    document.getElementById("connectBtn").addEventListener(
        "click", 
        create_proxy(start_matchmaking)
    )
    
    document.getElementById("matchmakingBackBtn").addEventListener(
        "click", 
        create_proxy(lambda e: switch_screen('mode_selection'))
    )
    
    # Game control buttons
    document.getElementById("backBtn").addEventListener(
        "click", 
        create_proxy(lambda e: switch_screen('mode_selection'))
    )
    
    document.getElementById("newGameBtn").addEventListener(
        "click", 
        create_proxy(start_new_game)
    )
    
    document.getElementById("resetScoresBtn").addEventListener(
        "click", 
        create_proxy(reset_all_scores)
    )
    
    # Cell click handlers
    for cell in cells:
        cell.addEventListener("click", create_proxy(handle_cell_click))

# --- Initialize Game ---
setup_event_listeners()
update_scores()
print("Tic-Tac-Toe loaded successfully!")
