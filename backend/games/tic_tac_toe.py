WINNING_CONDITIONS = (
    (0, 1, 2),
    (3, 4, 5),
    (6, 7, 8),
    (0, 3, 6),
    (1, 4, 7),
    (2, 5, 8),
)


def check_result(board):
    for a, b, c in WINNING_CONDITIONS:
        if board[a] and board[a] == board[b] == board[c]:
            return board[a], [a, b, c]

    if all(board):
        return "TIE", None

    return None, None
