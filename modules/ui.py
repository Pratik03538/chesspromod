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

    # Keep the board itself clean. All controls and status information live
    # outside the chessboard in one compact side panel.
    match_state = getattr(
        draw_overlay,
        "_match_state",
        "WAITING"
    )

    game_number = getattr(
        draw_overlay,
        "_game_number",
        None
    )

    game_started_at = getattr(
        draw_overlay,
        "_game_started_at",
        None
    )

    game_elapsed = (
        max(
            0.0,
            time.perf_counter() - game_started_at
        )
        if game_started_at is not None
        else 0.0
    )

    bot_state = getattr(
        draw_overlay,
        "_bot_state",
        "WAITING"
    )

    bot_state_since = getattr(
        draw_overlay,
        "_bot_state_since",
        time.perf_counter()
    )

    state_age = max(
        0.0,
        time.perf_counter() - bot_state_since
    )

    panel_w = min(
        340,
        max(
            285,
            int(width * 0.27)
        )
    )

    x, y, w, h = board_coords

    move_text = getattr(
        draw_overlay,
        "_move_history_text",
        ""
    )

    tokens = move_text.split(
        "  "
    ) if move_text else []

    max_move_lines = 12
    if len(tokens) > max_move_lines:
        tokens = tokens[-max_move_lines:]

    button_h = 38
    button_gap = 8
    button_w = int(
        (panel_w - 28 - button_gap) / 2
    )

    panel_h = (
        18
        + 24
        + 24
        + 42
        + 74
        + 16
        + button_h
        + 16
        + 24
        + max(1, len(tokens)) * 21
        + 16
    )

    if panel_h > height - 20:
        panel_h = height - 20

    # Prefer right side, then left side, then below/above. Never draw the
    # information panel over the chessboard when an outside position exists.
    if x + w + panel_w + 16 <= width:
        panel_x = x + w + 12
        panel_y = max(
            10,
            min(
                y,
                height - panel_h - 10
            )
        )
    elif x - panel_w - 16 >= 0:
        panel_x = x - panel_w - 16
        panel_y = max(
            10,
            min(
                y,
                height - panel_h - 10
            )
        )
    elif y + h + panel_h + 16 <= height:
        panel_x = max(
            10,
            min(
                x,
                width - panel_w - 10
            )
        )
        panel_y = y + h + 12
    else:
        panel_x = max(
            10,
            min(
                x,
                width - panel_w - 10
            )
        )
        panel_y = max(
            10,
            y - panel_h - 12
        )

    overlay = display_frame.copy()

    cv2.rectangle(
        overlay,
        (panel_x, panel_y),
        (
            panel_x + panel_w,
            panel_y + panel_h
        ),
        (12, 12, 16),
        -1
    )

    cv2.addWeighted(
        overlay,
        0.90,
        display_frame,
        0.10,
        0,
        display_frame
    )

    cv2.rectangle(
        display_frame,
        (panel_x, panel_y),
        (
            panel_x + panel_w,
            panel_y + panel_h
        ),
        (90, 90, 100),
        1
    )

    cv2.putText(
        display_frame,
        "CHESS VISION",
        (
            panel_x + 12,
            panel_y + 20
        ),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.52,
        (245, 245, 245),
        1,
        cv2.LINE_AA
    )

    game_label = (
        f"GAME #{int(game_number):03d}"
        if game_number is not None
        else "GAME"
    )

    cv2.putText(
        display_frame,
        game_label,
        (
            panel_x + 12,
            panel_y + 43
        ),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.40,
        (245, 245, 245),
        1,
        cv2.LINE_AA
    )

    cv2.putText(
        display_frame,
        match_state,
        (
            panel_x + 130,
            panel_y + 43
        ),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.40,
        (210, 210, 220),
        1,
        cv2.LINE_AA
    )

    game_time_text = (
        f"TIME {int(game_elapsed // 60):02d}:"
        f"{int(game_elapsed % 60):02d}"
        if match_state == "PLAYING"
        else "TIME --:--"
    )

    cv2.putText(
        display_frame,
        game_time_text,
        (
            panel_x + 12,
            panel_y + 84
        ),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.34,
        (165, 165, 175),
        1,
        cv2.LINE_AA
    )

    side_text = (
        f"BOT: {'BLACK' if stockfish_color == chess.BLACK else 'WHITE'}  "
        f"YOU: {'BLACK' if human_color == chess.BLACK else 'WHITE'}"
    )

    cv2.putText(
        display_frame,
        side_text,
        (
            panel_x + 12,
            panel_y + 64
        ),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.34,
        (185, 185, 195),
        1,
        cv2.LINE_AA
    )

    cv2.putText(
        display_frame,
        "BOT",
        (
            panel_x + 12,
            panel_y + 109
        ),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.36,
        (155, 155, 165),
        1,
        cv2.LINE_AA
    )

    cv2.putText(
        display_frame,
        bot_state,
        (
            panel_x + 58,
            panel_y + 109
        ),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.41,
        (245, 245, 245),
        1,
        cv2.LINE_AA
    )

    cv2.putText(
        display_frame,
        f"{state_age:.1f}s",
        (
            panel_x + panel_w - 52,
            panel_y + 109
        ),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.34,
        (165, 165, 175),
        1,
        cv2.LINE_AA
    )

    watchdog_states = {
        "THINKING",
        "PRE-CLICK CHECK",
        "CLICKING",
        "VERIFYING BOT MOVE",
        "RETRYING BOT MOVE"
    }

    if (
        bot_state in watchdog_states
        and state_age >= 5.0
    ):
        cv2.putText(
            display_frame,
            "CHECK",
            (
                panel_x + panel_w - 50,
                panel_y + 126
            ),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.28,
            (190, 190, 195),
            1,
            cv2.LINE_AA
        )

    buttons_y = panel_y + 126
    new_x1 = panel_x + 12
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

    def draw_pill(
        x1,
        y1,
        x2,
        y2,
        active,
        label
    ):
        radius = min(
            10,
            int((y2 - y1) / 2)
        )
        fill = (
            (35, 150, 82)
            if active
            else (55, 55, 62)
        )
        edge = (
            (80, 205, 125)
            if active
            else (100, 100, 110)
        )

        cv2.rectangle(
            display_frame,
            (
                x1 + radius,
                y1
            ),
            (
                x2 - radius,
                y2
            ),
            fill,
            -1
        )
        cv2.rectangle(
            display_frame,
            (
                x1,
                y1 + radius
            ),
            (
                x2,
                y2 - radius
            ),
            fill,
            -1
        )
        cv2.circle(
            display_frame,
            (
                x1 + radius,
                y1 + radius
            ),
            radius,
            fill,
            -1
        )
        cv2.circle(
            display_frame,
            (
                x2 - radius,
                y1 + radius
            ),
            radius,
            fill,
            -1
        )
        cv2.circle(
            display_frame,
            (
                x1 + radius,
                y2 - radius
            ),
            radius,
            fill,
            -1
        )
        cv2.circle(
            display_frame,
            (
                x2 - radius,
                y2 - radius
            ),
            radius,
            fill,
            -1
        )
        cv2.rectangle(
            display_frame,
            (x1, y1),
            (x2, y2),
            edge,
            1
        )

        label_size = cv2.getTextSize(
            label,
            cv2.FONT_HERSHEY_SIMPLEX,
            0.38,
            1
        )[0]

        cv2.putText(
            display_frame,
            label,
            (
                int(
                    (x1 + x2 - label_size[0]) / 2
                ),
                y1 + 24
            ),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.38,
            (255, 255, 255),
            1,
            cv2.LINE_AA
        )

    draw_pill(
        new_x1,
        new_y1,
        new_x2,
        new_y2,
        bool(ui_state["new_game"]),
        "NEW ON" if ui_state["new_game"] else "NEW OFF"
    )

    draw_pill(
        rematch_x1,
        rematch_y1,
        rematch_x2,
        rematch_y2,
        bool(ui_state["rematch"]),
        "REMATCH ON" if ui_state["rematch"] else "REMATCH OFF"
    )

    moves_y = buttons_y + button_h + 22

    cv2.putText(
        display_frame,
        "MOVES",
        (
            panel_x + 12,
            moves_y
        ),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.40,
        (155, 155, 165),
        1,
        cv2.LINE_AA
    )

    text_y = moves_y + 21

    if not tokens:
        tokens = [
            "No moves yet"
        ]

    max_drawable_lines = max(
        1,
        int((panel_h - (text_y - panel_y) - 12) / 21)
    )

    if len(tokens) > max_drawable_lines:
        tokens = tokens[-max_drawable_lines:]

    for token in tokens:
        cv2.putText(
            display_frame,
            token,
            (
                panel_x + 12,
                text_y
            ),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.37,
            (225, 225, 230),
            1,
            cv2.LINE_AA
        )
        text_y += 21

    # Keep the visual grid only while the grid is being positioned.
    if not locked:
        sq_w = w / 8.0
        sq_h = h / 8.0

        grid_color = (0, 255, 255)

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


