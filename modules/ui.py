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

    panel_margin = 16
    panel_w = min(
        390,
        max(
            330,
            int(width * 0.29)
        )
    )

    canvas_pad = (
        panel_margin
        + panel_w
        + panel_margin
    )

    canvas = cv2.copyMakeBorder(
        display_frame,
        0,
        0,
        0,
        canvas_pad,
        cv2.BORDER_CONSTANT,
        value=(10, 13, 20)
    )

    display_frame = canvas
    width = canvas.shape[1]

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

    x, y, w, h = board_coords

    move_text = getattr(
        draw_overlay,
        "_move_history_text",
        ""
    )

    tokens = (
        move_text.split("  ")
        if move_text
        else []
    )

    max_move_lines = 9
    if len(tokens) > max_move_lines:
        tokens = tokens[-max_move_lines:]

    ui_now = time.perf_counter()
    pulse = (
        0.5
        + 0.5
        * math.sin(
            ui_now * 4.0
        )
    )

    active_states = {
        "THINKING",
        "PRE-CLICK CHECK",
        "CLICKING",
        "VERIFYING BOT MOVE",
        "RETRYING BOT MOVE",
        "VERIFYING HUMAN MOVE",
    }

    bot_active = (
        bot_state
        in active_states
    )

    panel_x = width - panel_w - panel_margin
    panel_y = max(
        10,
        min(
            y,
            height - min(
                720,
                height - 20
            ) - 10
        )
    )

    panel_h = min(
        720,
        height - 20
    )

    # Modern dark glass-style panel.
    panel_overlay = display_frame.copy()

    cv2.rectangle(
        panel_overlay,
        (
            panel_x,
            panel_y
        ),
        (
            panel_x + panel_w,
            panel_y + panel_h
        ),
        (15, 20, 30),
        -1
    )

    cv2.addWeighted(
        panel_overlay,
        0.94,
        display_frame,
        0.06,
        0,
        display_frame
    )

    # Animated accent edge.
    accent_b = int(
        70
        + 70 * pulse
    )
    accent_g = int(
        145
        + 80 * pulse
    )
    accent_r = int(
        210
        + 40 * pulse
    )

    cv2.rectangle(
        display_frame,
        (
            panel_x,
            panel_y
        ),
        (
            panel_x + panel_w,
            panel_y + panel_h
        ),
        (
            accent_b,
            accent_g,
            accent_r
        ),
        1
    )

    def card(
        top,
        bottom,
        fill=(22, 28, 40),
        edge=(48, 63, 82)
    ):
        cv2.rectangle(
            display_frame,
            (
                panel_x + 10,
                top
            ),
            (
                panel_x + panel_w - 10,
                bottom
            ),
            fill,
            -1
        )
        cv2.rectangle(
            display_frame,
            (
                panel_x + 10,
                top
            ),
            (
                panel_x + panel_w - 10,
                bottom
            ),
            edge,
            1
        )

    def put(
        text,
        px,
        py,
        scale=0.38,
        color=(225, 230, 238),
        thickness=1
    ):
        cv2.putText(
            display_frame,
            str(text),
            (
                px,
                py
            ),
            cv2.FONT_HERSHEY_SIMPLEX,
            scale,
            color,
            thickness,
            cv2.LINE_AA
        )

    def rounded_button(
        rect,
        label,
        active,
        color_on=(65, 195, 130)
    ):
        x1, y1, x2, y2 = rect

        radius = min(
            12,
            int((y2 - y1) / 2)
        )

        bg = (
            (
                int(color_on[0] * 0.30),
                int(color_on[1] * 0.30),
                int(color_on[2] * 0.30)
            )
            if active
            else (38, 43, 54)
        )

        edge = (
            color_on
            if active
            else (82, 91, 106)
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
            bg,
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
            bg,
            -1
        )

        for cx, cy in (
            (x1 + radius, y1 + radius),
            (x2 - radius, y1 + radius),
            (x1 + radius, y2 - radius),
            (x2 - radius, y2 - radius),
        ):
            cv2.circle(
                display_frame,
                (
                    cx,
                    cy
                ),
                radius,
                bg,
                -1
            )

        cv2.rectangle(
            display_frame,
            (
                x1,
                y1
            ),
            (
                x2,
                y2
            ),
            edge,
            1
        )

        size = cv2.getTextSize(
            label,
            cv2.FONT_HERSHEY_SIMPLEX,
            0.34,
            1
        )[0]

        put(
            label,
            int(
                (x1 + x2 - size[0]) / 2
            ),
            y1 + 24,
            0.34,
            (245, 247, 250),
            1
        )

    title_y = panel_y + 25

    put(
        "CHESS VISION",
        panel_x + 16,
        title_y,
        0.58,
        (244, 247, 252),
        2
    )

    game_label = (
        f"GAME #{int(game_number):03d}"
        if game_number is not None
        else "GAME"
    )

    put(
        game_label,
        panel_x + 17,
        panel_y + 48,
        0.36,
        (132, 151, 176),
        1
    )

    side_text = (
        f"BOT {'BLACK' if stockfish_color == chess.BLACK else 'WHITE'}"
        f"   •   YOU {'BLACK' if human_color == chess.BLACK else 'WHITE'}"
    )

    put(
        side_text,
        panel_x + 16,
        panel_y + 68,
        0.34,
        (178, 190, 208),
        1
    )

    card(
        panel_y + 82,
        panel_y + 137
    )

    status_color = (
        (90, 205, 145)
        if bot_active
        else (105, 165, 220)
    )

    if match_state == "PLAYING" and bot_active:
        status_color = (
            int(80 + 40 * pulse),
            int(170 + 50 * pulse),
            int(210 + 30 * pulse)
        )

    orb_x = panel_x + 28
    orb_y = panel_y + 109

    if bot_active:
        orb_radius = int(
            5
            + 2 * pulse
        )
    else:
        orb_radius = 5

    cv2.circle(
        display_frame,
        (
            orb_x,
            orb_y
        ),
        orb_radius + 3,
        (
            int(status_color[0] * 0.20),
            int(status_color[1] * 0.20),
            int(status_color[2] * 0.20)
        ),
        -1
    )

    cv2.circle(
        display_frame,
        (
            orb_x,
            orb_y
        ),
        orb_radius,
        status_color,
        -1
    )

    put(
        "STATUS",
        panel_x + 43,
        panel_y + 102,
        0.30,
        (120, 140, 165),
        1
    )

    visible_state = (
        bot_state
        if bot_active
        else (
            "YOUR MOVE"
            if match_state == "PLAYING"
            else match_state
        )
    )

    animated_dots = (
        "."
        * (
            int(ui_now * 2.0) % 4
        )
    ) if bot_active else ""

    put(
        f"{visible_state}{animated_dots}",
        panel_x + 43,
        panel_y + 123,
        0.40,
        (239, 243, 249),
        1
    )

    put(
        f"{state_age:.1f}s",
        panel_x + panel_w - 54,
        panel_y + 102,
        0.30,
        (125, 144, 167),
        1
    )

    eval_card_top = panel_y + 149
    eval_card_bottom = panel_y + 273

    card(
        eval_card_top,
        eval_card_bottom,
        fill=(19, 27, 39),
        edge=(51, 70, 92)
    )

    eval_cp = None
    eval_text = "EVAL --"
    favor_text = "WAITING"

    if isinstance(analysis_state, dict):
        try:
            eval_cp = float(
                analysis_state.get(
                    "eval_cp"
                )
            )
        except Exception:
            eval_cp = None

        eval_text = str(
            analysis_state.get(
                "eval_text",
                "EVAL --"
            )
        )

        favor_text = str(
            analysis_state.get(
                "favor",
                "WAITING"
            )
        )

    if eval_cp is not None:
        draw_overlay._last_eval_cp = eval_cp
        draw_overlay._last_eval_text = eval_text
        draw_overlay._last_favor_text = favor_text

    shown_eval_cp = getattr(
        draw_overlay,
        "_last_eval_cp",
        None
    )

    shown_eval_text = getattr(
        draw_overlay,
        "_last_eval_text",
        eval_text
    )

    shown_favor_text = getattr(
        draw_overlay,
        "_last_favor_text",
        favor_text
    )

    put(
        "MATCH EVALUATION",
        panel_x + 18,
        eval_card_top + 24,
        0.34,
        (127, 148, 174),
        1
    )

    if shown_eval_cp is None:
        eval_bar_text = "No engine evaluation yet"
    elif (
        analysis_state is None
        and match_state == "PLAYING"
    ):
        eval_bar_text = "Last engine evaluation"
    else:
        eval_bar_text = "Current engine evaluation"

    put(
        eval_bar_text,
        panel_x + 18,
        eval_card_top + 43,
        0.29,
        (105, 124, 148),
        1
    )

    bar_x1 = panel_x + 18
    bar_x2 = panel_x + panel_w - 18
    bar_y1 = eval_card_top + 60
    bar_y2 = bar_y1 + 24
    center_x = (
        bar_x1
        + (bar_x2 - bar_x1) // 2
    )

    cv2.rectangle(
        display_frame,
        (
            bar_x1,
            bar_y1
        ),
        (
            bar_x2,
            bar_y2
        ),
        (39, 47, 60),
        -1
    )

    cv2.line(
        display_frame,
        (
            center_x,
            bar_y1 - 4
        ),
        (
            center_x,
            bar_y2 + 4
        ),
        (171, 185, 201),
        1
    )

    if shown_eval_cp is not None:
        target = (
            100000.0
            if abs(shown_eval_cp) >= 100000.0
            else max(
                -500.0,
                min(
                    500.0,
                    shown_eval_cp
                )
            )
        )

        animated_eval = getattr(
            draw_overlay,
            "_animated_eval_cp",
            target
        )

        animated_eval += (
            target - animated_eval
        ) * 0.18

        draw_overlay._animated_eval_cp = animated_eval

        frac = min(
            1.0,
            abs(animated_eval) / 500.0
        )

        fill_width = int(
            (bar_x2 - center_x)
            * frac
        )

        if fill_width > 0:
            fill_color = (
                (90, 205, 145)
                if animated_eval > 0
                else (90, 150, 235)
            )

            if abs(animated_eval) >= 100000.0:
                fill_width = (
                    bar_x2 - center_x
                )

            if animated_eval > 0:
                cv2.rectangle(
                    display_frame,
                    (
                        center_x,
                        bar_y1 + 2
                    ),
                    (
                        center_x + fill_width,
                        bar_y2 - 2
                    ),
                    fill_color,
                    -1
                )
            else:
                cv2.rectangle(
                    display_frame,
                    (
                        center_x - fill_width,
                        bar_y1 + 2
                    ),
                    (
                        center_x,
                        bar_y2 - 2
                    ),
                    fill_color,
                    -1
                )

    left_label = "BLACK"
    right_label = "WHITE"

    put(
        left_label,
        bar_x1,
        bar_y2 + 20,
        0.28,
        (105, 155, 225),
        1
    )

    white_label_width = cv2.getTextSize(
        right_label,
        cv2.FONT_HERSHEY_SIMPLEX,
        0.28,
        1
    )[0][0]

    put(
        right_label,
        bar_x2 - white_label_width,
        bar_y2 + 20,
        0.28,
        (105, 205, 155),
        1
    )

    put(
        shown_eval_text,
        panel_x + 18,
        eval_card_top + 108,
        0.46,
        (242, 245, 250),
        1
    )

    put(
        shown_favor_text,
        panel_x + 18,
        eval_card_top + 128,
        0.31,
        (
            (100, 205, 155)
            if shown_eval_cp is not None
            and shown_eval_cp > 8
            else (
                (100, 155, 225)
                if shown_eval_cp is not None
                and shown_eval_cp < -8
                else (185, 195, 210)
            )
        ),
        1
    )

    ctl_top = panel_y + 286
    ctl_bottom = panel_y + 340
    card(
        ctl_top,
        ctl_bottom,
        fill=(20, 27, 38),
        edge=(45, 60, 78)
    )

    button_h = 34
    button_gap = 8
    button_w = int(
        (
            panel_w
            - 36
            - button_gap
        ) / 2
    )

    new_rect = (
        panel_x + 18,
        ctl_top + 10,
        panel_x + 18 + button_w,
        ctl_top + 10 + button_h
    )

    rematch_rect = (
        new_rect[2] + button_gap,
        ctl_top + 10,
        new_rect[2] + button_gap + button_w,
        ctl_top + 10 + button_h
    )

    ui_state["new_rect"] = new_rect
    ui_state["rematch_rect"] = rematch_rect

    rounded_button(
        new_rect,
        (
            "NEW GAME ON"
            if ui_state["new_game"]
            else "NEW GAME OFF"
        ),
        bool(ui_state["new_game"]),
        (75, 200, 135)
    )

    rounded_button(
        rematch_rect,
        (
            "REMATCH ON"
            if ui_state["rematch"]
            else "REMATCH OFF"
        ),
        bool(ui_state["rematch"]),
        (235, 170, 75)
    )

    moves_top = panel_y + 353
    moves_bottom = panel_y + panel_h - 12

    card(
        moves_top,
        moves_bottom,
        fill=(18, 24, 34),
        edge=(43, 57, 75)
    )

    put(
        "MOVE HISTORY",
        panel_x + 18,
        moves_top + 25,
        0.34,
        (127, 148, 174),
        1
    )

    move_start_y = moves_top + 50

    if not tokens:
        put(
            "No moves yet",
            panel_x + 18,
            move_start_y,
            0.34,
            (112, 130, 151),
            1
        )
    else:
        visible_lines = min(
            len(tokens),
            max(
                1,
                int(
                    (
                        moves_bottom
                        - move_start_y
                        - 10
                    ) / 25
                )
            )
        )

        tokens = tokens[-visible_lines:]

        for index, token in enumerate(tokens):
            row_y = (
                move_start_y
                + index * 25
            )

            if index % 2 == 0:
                cv2.rectangle(
                    display_frame,
                    (
                        panel_x + 16,
                        row_y - 17
                    ),
                    (
                        panel_x + panel_w - 16,
                        row_y + 6
                    ),
                    (22, 29, 41),
                    -1
                )

            put(
                token,
                panel_x + 20,
                row_y,
                0.34,
                (226, 232, 241),
                1
            )

    # Keep the visual grid only while the grid is being positioned.
    if not locked:
        sq_w = w / 8.0
        sq_h = h / 8.0

        grid_color = (
            0,
            205,
            255
        )

        cv2.rectangle(
            display_frame,
            (
                x,
                y
            ),
            (
                x + w,
                y + h
            ),
            grid_color,
            2
        )

        for index in range(1, 8):
            cv2.line(
                display_frame,
                (
                    x,
                    y + int(index * sq_h)
                ),
                (
                    x + w,
                    y + int(index * sq_h)
                ),
                grid_color,
                1
            )

            cv2.line(
                display_frame,
                (
                    x + int(index * sq_w),
                    y
                ),
                (
                    x + int(index * sq_w),
                    y + h
                ),
                grid_color,
                1
            )

    return display_frame


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


