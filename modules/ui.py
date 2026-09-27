# Exact function source extracted from original main.py.

def progress(stage, detail="", key=None, interval=None, force=False):
    if not VERBOSE_LOGS and stage not in {"STATE", "PROMOTION"}:
        return

    if interval is None:
        interval = PROGRESS_INTERVAL

    if key is None:
        key = stage

    now = time.perf_counter()
    last = _progress_times.get(key, 0.0)
    text = f"[{stage}] {detail}" if detail else f"[{stage}]"

    if (
        force
        or text != _progress_last_text.get(key)
        or now - last >= interval
    ):
        _progress_times[key] = now
        _progress_last_text[key] = text
        print(
            f"[{time.strftime('%H:%M:%S')}] {text}",
            flush=True
        )


def draw_overlay(
    display_frame,
    board_coords,
    grid,
    locked,
    black_perspective,
    scan_ms,
    status,
    stockfish_color,
    human_color,
    analysis_state=None
):
    height, width = display_frame.shape[:2]

    ui_state = getattr(
        draw_overlay,
        "_ui_state",
        None
    )

    if ui_state is None:
        ui_state = {
            "new_game": True,
            "rematch": False,
            "new_rect": None,
            "rematch_rect": None,
            "mouse_ready": False,
        }
        draw_overlay._ui_state = ui_state

        def _mouse_callback(
            event,
            mx,
            my,
            flags,
            param
        ):
            if event != cv2.EVENT_LBUTTONDOWN:
                return

            state = getattr(
                draw_overlay,
                "_ui_state",
                None
            )

            if state is None:
                return

            new_rect = state.get(
                "new_rect"
            )

            if (
                new_rect is not None
                and new_rect[0] <= mx <= new_rect[2]
                and new_rect[1] <= my <= new_rect[3]
            ):
                state["new_game"] = not bool(
                    state.get(
                        "new_game",
                        True
                    )
                )

                if state["new_game"]:
                    state["rematch"] = False

                return

            rematch_rect = state.get(
                "rematch_rect"
            )

            if (
                rematch_rect is not None
                and rematch_rect[0] <= mx <= rematch_rect[2]
                and rematch_rect[1] <= my <= rematch_rect[3]
            ):
                state["rematch"] = not bool(
                    state.get(
                        "rematch",
                        False
                    )
                )

                if state["rematch"]:
                    state["new_game"] = False

        try:
            cv2.namedWindow(
                "Chess Vision Tracker",
                cv2.WINDOW_AUTOSIZE
            )
            cv2.setMouseCallback(
                "Chess Vision Tracker",
                _mouse_callback
            )
            ui_state["mouse_ready"] = True
        except Exception:
            ui_state["mouse_ready"] = False

    button_h = 34
    button_gap = 8
    button_w = min(
        150,
        max(
            120,
            int(width * 0.17)
        )
    )

    buttons_x = max(
        10,
        width - (
            button_w * 2
            + button_gap
            + 12
        )
    )
    buttons_y = 10

    new_x1 = buttons_x
    new_y1 = buttons_y
    new_x2 = new_x1 + button_w
    new_y2 = new_y1 + button_h

    rematch_x1 = new_x2 + button_gap
    rematch_y1 = buttons_y
    rematch_x2 = rematch_x1 + button_w
    rematch_y2 = rematch_y1 + button_h

    ui_state["new_rect"] = (
        new_x1,
        new_y1,
        new_x2,
        new_y2
    )

    ui_state["rematch_rect"] = (
        rematch_x1,
        rematch_y1,
        rematch_x2,
        rematch_y2
    )

    button_radius = 8

    cv2.rectangle(
        display_frame,
        (new_x1, new_y1),
        (new_x2, new_y2),
        (
            (35, 150, 70)
            if ui_state["new_game"]
            else (70, 70, 70)
        ),
        -1
    )

    cv2.rectangle(
        display_frame,
        (rematch_x1, rematch_y1),
        (rematch_x2, rematch_y2),
        (
            (35, 150, 70)
            if ui_state["rematch"]
            else (70, 70, 70)
        ),
        -1
    )

    new_label = (
        "NEW GAME: ON"
        if ui_state["new_game"]
        else "NEW GAME: OFF"
    )

    rematch_label = (
        "REMATCH: ON"
        if ui_state["rematch"]
        else "REMATCH: OFF"
    )

    cv2.putText(
        display_frame,
        new_label,
        (
            new_x1 + 10,
            new_y1 + 23
        ),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.40,
        (255, 255, 255),
        1,
        cv2.LINE_AA
    )

    cv2.putText(
        display_frame,
        rematch_label,
        (
            rematch_x1 + 10,
            rematch_y1 + 23
        ),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.40,
        (255, 255, 255),
        1,
        cv2.LINE_AA
    )

    # Keep the visual grid only while the grid is being positioned.
    # Once locked, the captured chessboard stays clean.
    if not locked:
        x, y, w, h = board_coords
        sq_w = w / 8.0
        sq_h = h / 8.0

        grid_color = (
            (0, 255, 255)
            if not locked
            else (0, 255, 0)
        )

        cv2.rectangle(
            display_frame,
            (x, y),
            (x + w, y + h),
            grid_color,
            2
        )

        for i in range(1, 8):
            cv2.line(
                display_frame,
                (
                    x,
                    y + int(i * sq_h)
                ),
                (
                    x + w,
                    y + int(i * sq_h)
                ),
                grid_color,
                1
            )

            cv2.line(
                display_frame,
                (
                    x + int(i * sq_w),
                    y
                ),
                (
                    x + int(i * sq_w),
                    y + h
                ),
                grid_color,
                1
            )

    move_text = getattr(
        draw_overlay,
        "_move_history_text",
        ""
    )

    if not move_text:
        return

    tokens = move_text.split(
        "  "
    )

    max_lines = 16
    if len(tokens) > max_lines:
        tokens = tokens[-max_lines:]

    panel_w = min(
        420,
        max(
            280,
            int(width * 0.34)
        )
    )
    line_h = 21
    header_h = 12
    panel_h = 18 + header_h + (
        len(tokens)
        * line_h
    )

    x, y, w, h = board_coords

    if (
        x + w + panel_w + 18
        <= width
    ):
        panel_x = x + w + 10
        panel_y = max(
            54,
            min(
                y,
                height - panel_h - 10
            )
        )
    else:
        panel_x = 10
        panel_y = 54

    overlay = display_frame.copy()

    cv2.rectangle(
        overlay,
        (
            panel_x,
            panel_y
        ),
        (
            panel_x + panel_w,
            panel_y + panel_h
        ),
        (10, 10, 10),
        -1
    )

    cv2.addWeighted(
        overlay,
        0.88,
        display_frame,
        0.12,
        0,
        display_frame
    )

    cv2.putText(
        display_frame,
        "MOVES",
        (
            panel_x + 10,
            panel_y + 16
        ),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.48,
        (255, 255, 255),
        1,
        cv2.LINE_AA
    )

    text_y = panel_y + 35

    for token in tokens:
        cv2.putText(
            display_frame,
            token,
            (
                panel_x + 10,
                text_y
            ),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.43,
            (235, 235, 235),
            1,
            cv2.LINE_AA
        )

        text_y += line_h


def format_board_for_screen(
    board,
    black_perspective
):
    lines = []

    if black_perspective:
        ranks = range(0, 8)
        files = range(7, -1, -1)
    else:
        ranks = range(7, -1, -1)
        files = range(0, 8)

    for rank in ranks:
        row = []

        for file_ in files:
            piece = board.piece_at(
                chess.square(
                    file_,
                    rank
                )
            )

            row.append(
                piece.symbol()
                if piece
                else "."
            )

        lines.append(
            " ".join(row)
        )

    return "\n".join(lines)


def format_move_history(
    board,
    rank_history=None
):
    if rank_history is None:
        rank_history = {}

    temp = chess.Board(
        INITIAL_FEN
    )

    moves = []
    move_number = 1

    for ply_index, move in enumerate(
        board.move_stack,
        start=1
    ):
        san = temp.san(
            move
        )

        rank = rank_history.get(
            ply_index
        )

        rank_text = (
            f" [RANK #{int(rank)}]"
            if rank is not None
            else ""
        )

        if temp.turn == chess.WHITE:
            moves.append(
                f"{move_number}. {san}{rank_text}"
            )
        else:
            if moves:
                moves[-1] += (
                    f" {san}{rank_text}"
                )
            else:
                moves.append(
                    f"{move_number}... {san}{rank_text}"
                )

            move_number += 1

        temp.push(
            move
        )

    return (
        "  ".join(moves)
        if moves
        else "-"
    )


def print_game_state(
    board,
    stockfish_color,
    human_color,
    black_perspective,
    message="",
    analysis_state=None
):
    builtins_module = __import__(
        "builtins"
    )

    real_print = getattr(
        builtins_module,
        "_chess_original_print",
        builtins_module.print
    )

    rank_history = getattr(
        draw_overlay,
        "_rank_history",
        {}
    )

    real_print(
        f"[MOVES] {format_move_history(board, rank_history)}",
        flush=True
    )


