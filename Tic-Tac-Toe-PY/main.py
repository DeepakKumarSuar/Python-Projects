# --- 1. Pyodide/DOM Imports ---
# Importing the js module to access JavaScript/DOM functions and global objects
import js
from pyodide.ffi import create_proxy # type: ignore
import random
import time

# --- 2. Global Game State Variables ---
# The board state, represented by a list of 9 elements (0-8)
board = [""] * 9
current_player = "X"
game_active = True
mode = None  # 'single' or 'two'

# Score tracking
scores = {"X": 0, "O": 0, "TIE": 0}

# HTML Elements (Cached for efficient use)
document = js.document
cells = [document.querySelector(f'[data-index="{i}"]') for i in range(9)]
mode_selection_screen = document.getElementById("modeSelection")
game_screen = document.getElementById("gameScreen")
x_label = document.getElementById("xLabel")
o_label = document.getElementById("oLabel")
game_title = document.getElementById("gameTitle")
status_text = document.getElementById("statusText")
turn_indicator = document.getElementById("turnIndicator")
thinking_animation = document.getElementById("thinkingAnimation")
celebration_div = document.getElementById("celebration")
celebration_content = document.querySelector("#celebration") # Using the existing celebration div for content
# Note: The original index.html has a placeholder for celebration content. We'll use the main div.

# Winning combinations (indices of the board)
WINNING_CONDITIONS = [
    [0, 1, 2], [3, 4, 5], [6, 7, 8],  # Rows
    [0, 3, 6], [1, 4, 7], [2, 5, 8],  # Columns
    [0, 4, 8], [2, 4, 6]             # Diagonals
]

# --- 3. DOM Interaction Helpers ---

def update_scores():
    """Updates the score display in the HTML."""
    document.getElementById("xScore").textContent = str(scores["X"])
    document.getElementById("oScore").textContent = str(scores["O"])
    document.getElementById("tieScore").textContent = str(scores["TIE"])

def set_turn_display():
    """Updates the status text and turn indicator color."""
    if mode == 'single' and current_player == 'O':
        status_text.textContent = "Computer's turn (O)"
        turn_indicator.className = "turn-indicator o-turn"
    elif current_player == 'X':
        status_text.textContent = f"{x_label.textContent.split('(')[0].strip()}'s turn (X)"
        turn_indicator.className = "turn-indicator x-turn"
    else: # Two-player O's turn
        status_text.textContent = f"{o_label.textContent.split('(')[0].strip()}'s turn (O)"
        turn_indicator.className = "turn-indicator o-turn"

def show_thinking(show):
    """Toggles the 'Computer is thinking...' animation."""
    if show:
        thinking_animation.className = "thinking-animation"
    else:
        thinking_animation.className = "thinking-animation hidden"

def show_celebration(message):
    """Shows the winner celebration screen with a message."""
    
    # Simple celebration content injection
    celebration_div.innerHTML = f"""
        <div class="celebration-content">
            <i class="fas fa-trophy celebration-icon"></i>
            <h2>{message}</h2>
            <div class="action-buttons" style="margin-top: 20px;">
                <button id="nextRoundBtn" class="action-btn new-game" style="margin: 0;">Next Round</button>
            </div>
            <div class="confetti">
                <div class="confetti-piece"></div><div class="confetti-piece"></div>
                <div class="confetti-piece"></div><div class="confetti-piece"></div>
                <div class="confetti-piece"></div>
            </div>
        </div>
    """
    
    # Must re-attach the event listener to the new button
    document.getElementById("nextRoundBtn").addEventListener("click", create_proxy(start_new_game))

    # Show the celebration screen
    celebration_div.className = "celebration"

def hide_celebration():
    """Hides the celebration screen."""
    celebration_div.className = "celebration hidden"


# --- 4. Game Logic Core Functions ---

def check_result():
    """Checks for a win or a tie."""
    global game_active

    # 1. Check for Win
    for condition in WINNING_CONDITIONS:
        a, b, c = condition
        if board[a] and board[a] == board[b] and board[a] == board[c]:
            game_active = False
            winner = board[a]
            scores[winner] += 1
            update_scores()
            
            # Highlight winning cells and show celebration
            for index in condition:
                cells[index].className += " winning"
                
            winner_name = x_label.textContent.split('(')[0].strip() if winner == 'X' else o_label.textContent.split('(')[0].strip()
            
            # Use js.setTimeout to slightly delay the celebration to allow CSS animations
            js.setTimeout(create_proxy(lambda: show_celebration(f"{winner_name} Wins!")), 500)
            return

    # 2. Check for Tie
    if "" not in board:
        game_active = False
        scores["TIE"] += 1
        update_scores()
        js.setTimeout(create_proxy(lambda: show_celebration("It's a Tie!")), 500)
        return

    # 3. If no result, switch turn and check for Computer move
    next_turn()

def next_turn():
    """Switches the current player and triggers the Computer's move if in single-player mode."""
    global current_player
    
    current_player = "O" if current_player == "X" else "X"
    set_turn_display()
    
    if mode == 'single' and current_player == 'O' and game_active:
        # Schedule the Computer's move after a slight delay for realism
        js.setTimeout(create_proxy(computer_move), 1000)

def handle_cell_click(event):
    """Handles a cell click event from the HTML."""
    global board, game_active

    if not game_active:
        return

    target = event.currentTarget
    clicked_index = int(target.getAttribute('data-index'))

    # Check if the cell is already played or if it's the computer's turn
    if board[clicked_index] != "" or (mode == 'single' and current_player == 'O'):
        return

    # Mark the board
    board[clicked_index] = current_player
    target.textContent = current_player
    target.className += f" {current_player.lower()}"
    target.disabled = True # Disable the button

    # Check for game end
    check_result()


# --- 5. Computer AI Logic (Simple Random Move) ---

def get_empty_cells():
    """Returns a list of indices of empty cells."""
    return [i for i, val in enumerate(board) if val == ""]

def computer_move():
    """
    Implements a simple AI strategy:
    1. Check for a winning move.
    2. Check for a move to block the player (X).
    3. Choose a random empty cell.
    """
    empty_cells = get_empty_cells()
    if not empty_cells:
        return # Should not happen if game_active is True

    # Simple Random Move (Placeholder for a more complex minimax AI)
    # The Computer is player 'O'
    
    # 1. Look for a winning move for 'O'
    for i in empty_cells:
        board[i] = 'O'
        for condition in WINNING_CONDITIONS:
            a, b, c = condition
            if board[a] == board[b] == board[c] == 'O':
                # Found a winning move
                make_move(i, 'O')
                return
        board[i] = '' # Undo the test move

    # 2. Look for a blocking move for 'X'
    for i in empty_cells:
        board[i] = 'X'
        for condition in WINNING_CONDITIONS:
            a, b, c = condition
            if board[a] == board[b] == board[c] == 'X':
                # Found a blocking move
                board[i] = '' # Undo the test move
                make_move(i, 'O') # Block the player
                return
        board[i] = '' # Undo the test move

    # 3. Choose a random empty cell
    move_index = random.choice(empty_cells)
    make_move(move_index, 'O')


def make_move(index, player):
    """Executes the move on the board and updates the UI."""
    show_thinking(False) # Hide thinking animation
    
    global board
    board[index] = player
    
    # Update UI
    cell = cells[index]
    cell.textContent = player
    cell.className += f" {player.lower()}"
    cell.disabled = True
    
    # Check for game end
    check_result()

# --- 6. Game Control Functions ---

def reset_board_ui():
    """Resets the visual state of the board."""
    for i in range(9):
        cells[i].textContent = ""
        # Reset the class name to just 'cell' and remove X, O, and winning classes
        cells[i].className = "cell"
        cells[i].disabled = False

def start_new_game(event=None):
    """Resets the game state for a new round."""
    global board, current_player, game_active
    
    hide_celebration()
    reset_board_ui()
    
    board = [""] * 9
    current_player = "X"
    game_active = True
    
    set_turn_display()
    
    # If the computer is X in two-player mode (unlikely but safe), check if it needs to go first
    if mode == 'single' and current_player == 'O':
        js.setTimeout(create_proxy(computer_move), 100) # Quick start for computer

def reset_all_scores(event=None):
    """Resets the entire scoreboard and starts a new game."""
    global scores
    scores = {"X": 0, "O": 0, "TIE": 0}
    update_scores()
    start_new_game()

def select_mode(selected_mode):
    """Sets the game mode and updates screen/labels."""
    global mode
    mode = selected_mode
    
    # 1. Update Labels and Title
    if mode == 'single':
        x_label.textContent = "You (X)"
        o_label.textContent = "Computer (O)"
        game_title.textContent = "You vs Computer"
    else: # two-player
        x_label.textContent = "Player 1 (X)"
        o_label.textContent = "Player 2 (O)"
        game_title.textContent = "Two Players"

    # 2. Switch Screens
    mode_selection_screen.className = "screen"
    game_screen.className = "screen active"
    
    # 3. Start the first game
    reset_all_scores() # Also calls start_new_game


# --- 7. Event Listeners (Setup) ---

def setup_event_listeners():
    """Attaches all event handlers to HTML elements."""
    
    # Mode Selection Buttons
    document.getElementById("singlePlayerBtn").addEventListener("click", create_proxy(lambda e: select_mode('single')))
    document.getElementById("twoPlayerBtn").addEventListener("click", create_proxy(lambda e: select_mode('two')))

    # Game Control Buttons
    document.getElementById("backBtn").addEventListener("click", create_proxy(lambda e: document.location.reload())) # Simple way to reset to mode screen
    document.getElementById("newGameBtn").addEventListener("click", create_proxy(start_new_game))
    document.getElementById("resetScoresBtn").addEventListener("click", create_proxy(reset_all_scores))
    
    # Cell Click Handlers
    for cell in cells:
        cell.addEventListener("click", create_proxy(handle_cell_click))

# --- 8. Initialization ---

# This is the entry point when Pyodide finishes loading and executes the script.
setup_event_listeners()
update_scores() # Ensure initial scores are 0
set_turn_display() # Set initial turn display
print("Tic-Tac-Toe Python logic loaded successfully via Pyodide.")