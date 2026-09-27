# Exact function source extracted from original main.py.

def promotion_symbol(
    move,
    color
):
    if move.promotion is None:
        return None

    return chess.Piece(
        move.promotion,
        color
    ).symbol()


def promotion_candidate_squares(move):
    rank = chess.square_rank(
        move.to_square
    )

    file_ = chess.square_file(
        move.to_square
    )

    result = []

    if rank == 7:
        for step in range(4):
            candidate_rank = rank - step

            if candidate_rank >= 0:
                result.append(
                    chess.square(
                        file_,
                        candidate_rank
                    )
                )

    elif rank == 0:
        for step in range(4):
            candidate_rank = rank + step

            if candidate_rank <= 7:
                result.append(
                    chess.square(
                        file_,
                        candidate_rank
                    )
                )

    else:
        for direction in (-1, 1):
            for step in range(4):
                candidate_rank = (
                    rank
                    + direction * step
                )

                if 0 <= candidate_rank <= 7:
                    result.append(
                        chess.square(
                            file_,
                            candidate_rank
                        )
                    )

    return list(
        dict.fromkeys(result)
    )


def find_promotion_choice(
    sct,
    hwnd,
    move,
    promotion_color,
    board_coords,
    black_perspective,
    allow_fallback=True
):
    expected = promotion_symbol(
        move,
        promotion_color
    )

    if expected is None:
        return None

    frame = capture_screen(
        sct,
        hwnd
    )

    if frame is None:
        return None

    templates = get_scaled_templates(
        board_coords[2] / 8.0,
        board_coords[3] / 8.0
    )

    candidates = promotion_candidate_squares(
        move
    )

    scored = []

    for square in candidates:
        crop = get_square_crop(
            frame,
            board_coords,
            square,
            black_perspective
        )

        if crop is None:
            continue

        detected, score = classify_square(
            crop,
            templates,
            expected_symbol=expected
        )

        if detected == expected:
            scored.append(
                (
                    float(score),
                    square
                )
            )

    if scored:
        scored.sort(
            key=lambda item: item[0]
        )

        return scored[0][1]

    if allow_fallback and PROMOTION_FALLBACK:
        ordered = {
            chess.QUEEN: 0,
            chess.ROOK: 1,
            chess.BISHOP: 2,
            chess.KNIGHT: 3,
        }

        index = ordered.get(
            move.promotion
        )

        if (
            index is not None
            and index < len(candidates)
        ):
            fallback_square = candidates[index]

            print(
                f"[PROMOTION] fallback selected {expected}"
            )

            return fallback_square

    return None


def select_promotion_piece(
    sct,
    hwnd,
    move,
    promotion_color,
    board_coords,
    black_perspective,
    allow_fallback=True
):
    if move.promotion is None:
        return True

    expected = promotion_symbol(
        move,
        promotion_color
    )

    if expected is None:
        return False

    piece_name = chess.piece_name(
        move.promotion
    ).upper()

    progress(
        "PROMOTION",
        (
            f"Stockfish requested {piece_name} "
            f"({expected}); waiting for promotion menu"
        ),
        key="promotion_stage",
        force=True
    )

    for attempt in range(
        1,
        PROMOTION_RETRIES + 1
    ):
        time.sleep(
            random.uniform(
                PROMOTION_WAIT_MIN,
                PROMOTION_WAIT_MAX
            )
        )

        square = find_promotion_choice(
            sct,
            hwnd,
            move,
            promotion_color,
            board_coords,
            black_perspective,
            allow_fallback=allow_fallback
        )

        if square is None:
            progress(
                "PROMOTION",
                (
                    f"menu choice {expected} not detected; "
                    f"attempt {attempt}/{PROMOTION_RETRIES}"
                ),
                key="promotion_loop",
                interval=0.20,
                force=True
            )

            continue

        px, py = square_screen_center(
            square,
            board_coords,
            black_perspective,
            hwnd
        )

        print(
            f"[PROMOTION] selecting {piece_name}"
        )

        if not focus_scrcpy(hwnd):
            continue

        left_click_screen(
            px,
            py
        )

        # Confirm that the exact promotion piece requested by Stockfish is
        # already on the destination square before accepting the promotion.
        promotion_ok = False
        promotion_reason = "promotion state not yet confirmed"
        promotion_deadline = time.perf_counter() + 0.10

        while time.perf_counter() < promotion_deadline:
            check_frame = capture_screen(
                sct,
                hwnd
            )

            if check_frame is None:
                time.sleep(
                    SCAN_INTERVAL
                )
                continue

            # Confirm directly on the destination square that the exact
            # promotion piece requested by Stockfish is now visible.
            target_crop = get_square_crop(
                check_frame,
                board_coords,
                move.to_square,
                black_perspective
            )

            templates = get_scaled_templates(
                board_coords[2] / 8.0,
                board_coords[3] / 8.0
            )

            detected_piece, detected_score = classify_square(
                target_crop,
                templates,
                expected_symbol=expected,
                match_threshold=BOT_POST_MATCH_THRESHOLD
            )

            source_crop = get_square_crop(
                check_frame,
                board_coords,
                move.from_square,
                black_perspective
            )

            source_piece, _ = classify_square(
                source_crop,
                templates
            )

            if (
                detected_piece == expected
                and source_piece is None
            ):
                promotion_ok = True
                promotion_reason = (
                    f"source=empty destination={expected} "
                    f"({detected_score:.3f})"
                )
                break

            time.sleep(
                SCAN_INTERVAL
            )

        if promotion_ok:
            time.sleep(
                CLICK_SETTLE_DELAY
            )

            progress(
                "PROMOTION",
                f"selected {piece_name}; {promotion_reason}",
                key="promotion_stage",
                force=True
            )

            return True

        progress(
            "PROMOTION",
            (
                f"{piece_name} click not confirmed; "
                f"attempt {attempt}/{PROMOTION_RETRIES}"
            ),
            key="promotion_loop",
            force=True
        )

    progress(
        "PROMOTION",
        (
            f"FAILED to select {piece_name}; "
            "game position not advanced"
        ),
        key="promotion_stage",
        force=True
    )

    return False


def _verify_source_click_selected(
    sct,
    hwnd,
    move,
    before_frame,
    board_coords,
    black_perspective
):
    """Confirm the intended SOURCE square was actually selected.

    A fast motion map is used first. The intended source must be the only
    changed board square, and it must remain the dominant changed square for
    two consecutive frames. This is deliberately strict: when Stockfish asks
    for Bxg5, a click that lands on the queen must never be allowed to reach
    the destination click and become Qxg5.
    """
    if sct is None or before_frame is None:
        return True, "source-click visual check unavailable"

    try:
        source_piece = move.from_square
    except Exception:
        return False, "invalid source square"

    start = time.perf_counter()
    deadline = start + BOT_SOURCE_SELECT_TIMEOUT
    stable_samples = 0
    last_reason = "source selection transition not detected"

    while time.perf_counter() < deadline:
        frame = capture_screen(sct, hwnd)
        if frame is None:
            time.sleep(BOT_SOURCE_SELECT_POLL)
            continue

        changes = fast_square_motion_scores(
            before_frame,
            frame,
            board_coords,
            black_perspective
        )
        if changes is None:
            last_reason = "source selection motion map unavailable"
            time.sleep(BOT_SOURCE_SELECT_POLL)
            continue

        source_change = changes.get(source_piece, 0.0)

        other_changes = sorted(
            (
                (change, square)
                for square, change in changes.items()
                if square != source_piece
                and change >= BOT_SOURCE_SELECT_CHANGE_MIN
            ),
            reverse=True,
            key=lambda item: item[0]
        )

        dominant_other = other_changes[0][0] if other_changes else 0.0
        source_is_dominant = (
            source_change >= BOT_SOURCE_SELECT_CHANGE_MIN
            and dominant_other <= source_change * BOT_SOURCE_SELECT_DOMINANCE_RATIO
        )

        if (
            source_is_dominant
            and len(other_changes) <= BOT_SOURCE_SELECT_MAX_EXTRA_CHANGES
        ):
            stable_samples += 1
            if stable_samples >= BOT_SOURCE_SELECT_STABLE_SAMPLES:
                last_reason = (
                    f"source selected {chess.square_name(source_piece)} "
                    f"change={source_change:.4f}; stable={stable_samples}"
                )
                return True, last_reason

            last_reason = (
                f"source selection seen; waiting stable sample "
                f"{stable_samples}/{BOT_SOURCE_SELECT_STABLE_SAMPLES}; "
                f"change={source_change:.4f}"
            )
        else:
            stable_samples = 0
            if other_changes:
                preview = ", ".join(
                    f"{chess.square_name(sq)}:{change:.4f}"
                    for change, sq in other_changes[:3]
                )
                last_reason = (
                    f"wrong/extra square changed; source="
                    f"{source_change:.4f}; {preview}"
                )
            else:
                last_reason = (
                    f"source change too weak: "
                    f"{source_change:.4f}"
                )

        time.sleep(BOT_SOURCE_SELECT_POLL)

    return False, last_reason


def human_reaction_delay_seconds(move, board):
    """Return a very small low-latency response variation for bullet play."""
    try:
        # Keep most moves very fast; only a small fraction gets an extra
        # hesitation so the total game time is not materially increased.
        if random.random() < REACTION_OCCASIONAL_CHANCE:
            return random.uniform(
                REACTION_OCCASIONAL_MIN,
                REACTION_OCCASIONAL_MAX
            )

        if board.is_capture(move) or board.gives_check(move):
            return random.uniform(
                REACTION_NORMAL_MIN,
                REACTION_NORMAL_MAX
            )

        return random.uniform(
            REACTION_FAST_MIN,
            REACTION_FAST_MAX
        )
    except Exception:
        return 0.0


def mate_pause_seconds(info, mover_color):
    """Return a small optional pause when the selected line reaches mate."""
    if not info:
        return 0.0

    try:
        score = info.get("score")
        if score is None:
            return 0.0

        mate = score.pov(mover_color).mate()
        if mate is None or mate <= 0:
            return 0.0

        if mate == 5:
            if random.random() <= MATE_PAUSE_CHANCE_M5:
                return random.uniform(
                    MATE_PAUSE_M5_MIN,
                    MATE_PAUSE_M5_MAX
                )
            return 0.0

        if mate == 6:
            if random.random() <= MATE_PAUSE_CHANCE_M6:
                return random.uniform(
                    MATE_PAUSE_M6_MIN,
                    MATE_PAUSE_M6_MAX
                )
            return 0.0

        if 7 <= mate <= 8:
            if random.random() <= MATE_PAUSE_CHANCE_M7_8:
                return random.uniform(
                    MATE_PAUSE_M7_8_MIN,
                    MATE_PAUSE_M7_8_MAX
                )

    except Exception:
        return 0.0

    return 0.0


def click_move(
    move,
    board_coords,
    black_perspective,
    scrcpy_hwnd,
    sct=None,
    promotion_color=None
):
    if not focus_scrcpy(
        scrcpy_hwnd
    ):
        print(
            "[BOT ERROR] Could not focus scrcpy window."
        )

        return False

    # SPEED OPTIMIZATION:
    # Only resolve the scrcpy screen origin once for source + target.
    screen_origin = get_scrcpy_screen_origin(
        scrcpy_hwnd
    )

    if screen_origin is None:
        print(
            "[BOT ERROR] Could not determine scrcpy screen origin."
        )
        return False

    # Re-sample both pickup and drop points for every click attempt. Every
    # point remains inside the centered 40%-area circle of its own square.
    sx, sy = square_screen_center(
        move.from_square,
        board_coords,
        black_perspective,
        scrcpy_hwnd,
        screen_origin=screen_origin
    )

    tx, ty = square_screen_center(
        move.to_square,
        board_coords,
        black_perspective,
        scrcpy_hwnd,
        screen_origin=screen_origin
    )

    print(
        f"[BOT CLICK] {move.uci()} "
        f"source=({sx},{sy}) target=({tx},{ty})"
    )

    # Move to the source along a short, slightly curved path.
    # Timing stays intentionally small so the playing speed remains high.
    move_cursor_human_like(sx, sy)
    time.sleep(
        random.uniform(
            CLICK_CURSOR_SETTLE_MIN,
            CLICK_CURSOR_SETTLE_MAX
        )
    )

    # Select the locked source with a real press/hold/release sequence.
    user32.mouse_event(
        MOUSEEVENTF_LEFTDOWN,
        0,
        0,
        0,
        0
    )
    time.sleep(
        random.uniform(
            CLICK_HOLD_MIN,
            CLICK_HOLD_MAX
        )
    )
    user32.mouse_event(
        MOUSEEVENTF_LEFTUP,
        0,
        0,
        0,
        0
    )

    time.sleep(
        random.uniform(
            CLICK_BETWEEN_MIN,
            CLICK_BETWEEN_MAX
        )
    )

    # Move to the locked destination with the same short natural path.
    move_cursor_human_like(tx, ty)
    time.sleep(
        random.uniform(
            CLICK_CURSOR_SETTLE_MIN,
            CLICK_CURSOR_SETTLE_MAX
        )
    )

    # Drop using a real press/hold/release sequence.
    user32.mouse_event(
        MOUSEEVENTF_LEFTDOWN,
        0,
        0,
        0,
        0
    )
    time.sleep(
        random.uniform(
            CLICK_HOLD_MIN,
            CLICK_HOLD_MAX
        )
    )
    user32.mouse_event(
        MOUSEEVENTF_LEFTUP,
        0,
        0,
        0,
        0
    )

    if move.promotion is not None:
        if promotion_color is None:
            promotion_color = chess.WHITE

        if sct is None:
            print(
                "[PROMOTION ERROR] "
                "Screen capture context unavailable."
            )

            return False

        promotion_ok = select_promotion_piece(
            sct,
            scrcpy_hwnd,
            move,
            promotion_color,
            board_coords,
            black_perspective
        )

        # Leave the pointer at the promotion choice instead of teleporting it away.
        return promotion_ok

    return True


def safe_drop_fraction(
    current_cp
):
    current_eval = (
        current_cp / 100.0
    )

    if current_eval < 2.0:
        return 0.10

    if current_eval < 3.0:
        return 0.15

    if current_eval < 4.0:
        return 0.20

    if current_eval < 5.0:
        return 0.25

    return 0.30


