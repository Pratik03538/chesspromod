# Exact function source extracted from original main.py.

def clear_runtime_caches():
    """Clear transient image/geometry caches."""
    _SQUARE_GEOMETRY_CACHE.clear()
    _FRAME_SQUARE_CACHE.clear()
    _GRID_CONF_CACHE.clear()


def load_assets():
    if not os.path.exists(PIECES_DIR):
        print(f"[ERROR] '{PIECES_DIR}' folder not found.")
        return False

    loaded_count = 0

    for fname, symbol in PIECE_MAP.items():
        path = os.path.join(PIECES_DIR, fname)

        if not os.path.exists(path):
            print(f"[WARN] Missing: {fname}")
            continue

        img = cv2.imread(path, cv2.IMREAD_UNCHANGED)

        if img is None:
            print(f"[WARN] Could not read: {fname}")
            continue

        if len(img.shape) != 3 or img.shape[2] != 4:
            print(f"[WARN] {fname} must be BGRA PNG with transparency.")
            continue

        alpha = img[:, :, 3]
        coords = cv2.findNonZero(alpha)

        if coords is None:
            continue

        x, y, w, h = cv2.boundingRect(coords)
        RAW_TEMPLATES[symbol] = img[y:y + h, x:x + w]
        loaded_count += 1

    print(f"[INFO] Loaded {loaded_count}/12 piece templates.")
    return loaded_count == 12


def find_scrcpy_window():
    if not user32:
        return None

    found = []

    def enum_proc(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True

        length = user32.GetWindowTextLengthW(hwnd)

        if length <= 0:
            return True

        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value.lower()

        if (
            SCRCPY_WINDOW_TITLE.lower() in title
            or FALLBACK_TITLE_KEYWORD.lower() in title
        ):
            found.append(hwnd)

        return True

    callback = ctypes.WINFUNCTYPE(
        ctypes.c_int,
        wintypes.HWND,
        wintypes.LPARAM
    )(enum_proc)

    user32.EnumWindows(callback, 0)

    return found[0] if found else None


def focus_scrcpy(hwnd):
    if not user32:
        return False

    candidates = []
    if hwnd and user32.IsWindow(hwnd):
        candidates.append(hwnd)
    else:
        fresh = find_scrcpy_window()
        if fresh:
            candidates.append(fresh)

    for candidate in candidates:
        if not candidate or not user32.IsWindow(candidate):
            continue

        try:
            # Do not pay the old 10ms+ sleep cost on every move.
            if user32.GetForegroundWindow() == candidate:
                return True
            user32.ShowWindow(candidate, SW_RESTORE)
            user32.BringWindowToTop(candidate)
            user32.SetForegroundWindow(candidate)
            return True
        except Exception:
            continue

    return False


def rank_changed_squares(
    before_frame,
    after_frame,
    board_coords,
    black_perspective
):
    changes = []

    for square in chess.SQUARES:
        score = square_change_score(
            before_frame,
            after_frame,
            board_coords,
            square,
            black_perspective
        )

        if score >= CHANGE_THRESHOLD:
            changes.append(
                (
                    score,
                    square
                )
            )

    changes.sort(
        reverse=True,
        key=lambda item: item[0]
    )

    return changes


def validate_bot_move_frame(
    before_frame,
    after_frame,
    board,
    move,
    board_coords,
    black_perspective
):
    if (
        before_frame is None
        or after_frame is None
    ):
        return False, "missing frame"

    templates = get_scaled_templates(
        board_coords[2] / 8.0,
        board_coords[3] / 8.0
    )

    score = move_visual_score(
        before_frame,
        after_frame,
        board,
        move,
        board_coords,
        black_perspective,
        templates
    )

    if score is None:
        return (
            False,
            "expected visual transition not confirmed"
        )

    return (
        True,
        f"visual score {score:.3f}"
    )


def direct_move_state_confirmed(
    frame,
    board,
    move,
    board_coords,
    black_perspective
):
    """
    Check only the squares that must be different after the move.
    """
    if frame is None:
        return False, "missing frame"

    templates = get_scaled_templates(
        board_coords[2] / 8.0,
        board_coords[3] / 8.0
    )

    def detect_expected(
        square,
        expected_symbol,
        label
    ):
        crop = get_square_crop(
            frame,
            board_coords,
            square,
            black_perspective
        )

        detected, score = classify_square(
            crop,
            templates,
            expected_symbol=expected_symbol,
            match_threshold=BOT_POST_MATCH_THRESHOLD
        )

        if detected is None:
            return (
                False,
                f"{label} not detected"
            )

        if (
            detected.lower()
            != expected_symbol.lower()
        ):
            return (
                False,
                (
                    f"{label} type is "
                    f"{detected}, expected "
                    f"{expected_symbol}"
                )
            )

        return (
            True,
            (
                f"{label}="
                f"{detected},{score:.3f}"
            )
        )

    def require_empty(
        square,
        label
    ):
        crop = get_square_crop(
            frame,
            board_coords,
            square,
            black_perspective
        )

        detected, score = classify_square(
            crop,
            templates
        )

        if detected is not None:
            return (
                False,
                (
                    f"{label} still occupied "
                    f"({detected},{score:.3f})"
                )
            )

        return (
            True,
            f"{label}=empty"
        )

    ok, reason = require_empty(
        move.from_square,
        "source"
    )

    if not ok:
        return False, reason

    expected_target = expected_symbol_after(
        board,
        move,
        move.to_square
    )

    if expected_target is not None:
        ok, reason = detect_expected(
            move.to_square,
            expected_target,
            "destination"
        )

        if not ok:
            return False, reason

    if board.is_castling(move):
        if board.is_kingside_castling(move):
            rook_from = (
                chess.H1
                if board.turn == chess.WHITE
                else chess.H8
            )

            rook_to = (
                chess.F1
                if board.turn == chess.WHITE
                else chess.F8
            )

        else:
            rook_from = (
                chess.A1
                if board.turn == chess.WHITE
                else chess.A8
            )

            rook_to = (
                chess.D1
                if board.turn == chess.WHITE
                else chess.D8
            )

        ok, reason = require_empty(
            rook_from,
            "castling rook source"
        )

        if not ok:
            return False, reason

        expected_rook = (
            "R"
            if board.turn == chess.WHITE
            else "r"
        )

        ok, reason = detect_expected(
            rook_to,
            expected_rook,
            "castling rook destination"
        )

        if not ok:
            return False, reason

    if board.is_en_passant(move):
        captured_square = (
            move.to_square - 8
            if board.turn == chess.WHITE
            else move.to_square + 8
        )

        ok, reason = require_empty(
            captured_square,
            "en-passant captured square"
        )

        if not ok:
            return False, reason

    return (
        True,
        "direct changed-square state confirmed"
    )


def score_to_cp(score):
    if score.is_mate():
        mate = score.mate()

        if mate is None:
            return 0

        return (
            100000
            if mate > 0
            else -100000
        )

    value = score.score(
        mate_score=100000
    )

    return (
        0
        if value is None
        else int(value)
    )


def detect_existing_white_first_move(
    frame,
    board,
    board_coords,
    black_perspective
):
    if (
        frame is None
        or board.turn != chess.WHITE
        or board.move_stack
    ):
        return None

    grid, confidence, _ = scan_board(
        frame,
        board_coords
    )

    candidates = []

    for move in board.legal_moves:
        hypothesis = board_hypothesis_score(
            board,
            move,
            grid,
            confidence,
            black_perspective
        )
        candidates.append((
            hypothesis["normalized"],
            move
        ))

    if not candidates:
        return None

    candidates.sort(
        reverse=True,
        key=lambda item: item[0]
    )

    best_score, best_move = candidates[0]
    second_score = (
        candidates[1][0]
        if len(candidates) > 1
        else -999.0
    )

    if (
        best_score < 0.90
        or best_score - second_score < 0.020
    ):
        return None

    templates = get_scaled_templates(
        board_coords[2] / 8.0,
        board_coords[3] / 8.0
    )

    direct_ok, _ = human_direct_state_confirmed(
        frame,
        board,
        best_move,
        board_coords,
        black_perspective,
        templates
    )

    if not direct_ok:
        return None

    expected_board = expected_board_after_move(
        board,
        best_move
    )

    full_ok, _ = full_board_state_confirmed(
        frame,
        expected_board,
        board_coords,
        black_perspective
    )

    return best_move if full_ok else None


def main():
    global _advantage_progress_target_cp
    global _advantage_progress_hold_moves
    global _advantage_progress_hold_limit
    global _advantage_progress_side
    print(
        "============================================================"
    )

    print(
        "        CHESS VISION - HUMAN vs STOCKFISH"
    )

    print(
        "============================================================"
    )

    print(
        "R = initialize board"
    )

    print(
        "L = lock / unlock grid"
    )

    print(
        "W/A/S/D = move grid"
    )

    print(
        "+/- = resize grid"
    )

    print(
        "F = detect bottom side again"
    )

    print(
        "Q = quit"
    )

    print(
        "First chess move is always WHITE."
    )

    print(
        "The color physically at the BOTTOM is always STOCKFISH."
    )

    print(
        "============================================================"
    )

    if not load_assets():
        return

    if not os.path.exists(
        STOCKFISH_PATH
    ):
        print(
            "[ERROR] Stockfish executable not found: "
            f"{STOCKFISH_PATH}"
        )

        return

    try:
        engine = chess.engine.SimpleEngine.popen_uci(
            STOCKFISH_PATH
        )

        engine.configure({
            "Threads": 2,
            "Hash": 128
        })

    except Exception as e:
        print(
            f"[ERROR] Could not start Stockfish: {e}"
        )

        return

    try:
        board = chess.Board(
            INITIAL_FEN
        )

    except Exception as e:
        print(
            f"[ERROR] Invalid initial FEN: {e}"
        )

        engine.quit()

        return

    scrcpy_hwnd = None
    cached_board_coords = None
    cached_board_grid = None
    baseline_frame = None
    grid_locked = False
    game_ready = False
    bot_thinking = False
    last_scan_time_ms = 0.0
    last_bot_position_key = None
    pending_bot_moves = {}
    pending_recovered_human = None
    next_main_turn_rescan = time.perf_counter() + TURN_RESCAN_INTERVAL
    visual_black_perspective = False
    stockfish_color = None
    human_color = None
    status = "READY - PRESS R"
    analysis_state = None
    last_wait_status = ""
    last_wait_report = 0.0

    stockfish_moves_since_buffer = 0

    next_buffer_after = random.randint(
        RANDOM_BUFFER_MOVE_MIN,
        RANDOM_BUFFER_MOVE_MAX
    )

    opponent_match_history = []
    next_human_best_uci = None
    opponent_pressure = False

    # Screen-interruption guard. This is session state and does not alter
    # the chess board/grid state. A large unexpected visual change inside
    # the locked board pauses all gameplay until the board is visible again.
    screen_interrupted = False
    screen_interrupt_bad_samples = 0
    screen_interrupt_clear_samples = 0
    screen_interrupt_fraction = 0.0

    awaiting_new_match = False
    new_match_button_stable = 0
    new_match_button_center = None
    last_new_match_click = 0.0
    next_new_match_scan = 0.0
    new_match_click_attempts = 0
    new_match_start_stable = 0
    new_match_start_key = None
    new_match_scan_ms = 0.0

    def board_interruption_fraction(
        reference_frame,
        current_frame,
        board_coords
    ):
        if (
            reference_frame is None
            or current_frame is None
            or board_coords is None
        ):
            return 0.0

        try:
            x, y, w, h = board_coords
            x1 = max(0, int(x))
            y1 = max(0, int(y))
            x2 = min(
                reference_frame.shape[1],
                int(x + w)
            )
            y2 = min(
                reference_frame.shape[0],
                int(y + h)
            )

            if (
                x2 <= x1
                or y2 <= y1
                or x2 > current_frame.shape[1]
                or y2 > current_frame.shape[0]
            ):
                return 0.0

            size = 128

            before = cv2.resize(
                reference_frame[
                    y1:y2,
                    x1:x2
                ],
                (size, size),
                interpolation=cv2.INTER_AREA
            )

            current = cv2.resize(
                current_frame[
                    y1:y2,
                    x1:x2
                ],
                (size, size),
                interpolation=cv2.INTER_AREA
            )

            difference = cv2.absdiff(
                before,
                current
            )

            pixel_diff = np.max(
                difference,
                axis=2
            )

            # Estimate the board area occupied by unexpected visual content.
            # A normal chess move changes only a small part of the board;
            # notifications/call overlays covering >10% produce a much larger
            # changed-area fraction.
            changed_mask = (
                pixel_diff >= 20
            ).astype(
                np.uint8
            )

            kernel = np.ones(
                (3, 3),
                np.uint8
            )

            changed_mask = cv2.morphologyEx(
                changed_mask,
                cv2.MORPH_OPEN,
                kernel
            )

            return float(
                np.count_nonzero(
                    changed_mask
                )
                / changed_mask.size
            )

        except Exception:
            return 0.0

    def detect_new_game_button(frame):
        """Detect the right-side New <time-control> button on the result page.

        The label may be 1+1, 2+1, 3+2, 5 min, etc. The button position is
        stable, so detection is based on the result-page layout rather than
        OCR/text. A green Game Review bar near the bottom is required before
        returning the click point.
        """
        if frame is None:
            return None

        try:
            height, width = frame.shape[:2]

            button_x1 = int(width * 0.46)
            button_x2 = int(width * 0.88)
            button_y1 = int(height * 0.32)
            button_y2 = int(height * 0.40)

            button_roi = frame[
                button_y1:button_y2,
                button_x1:button_x2
            ]

            gray = cv2.cvtColor(
                button_roi,
                cv2.COLOR_BGR2GRAY
            )

            white_fraction = float(
                np.mean(gray > 175)
            )

            dark_fraction = float(
                np.mean(gray < 100)
            )

            if (
                white_fraction < 0.015
                or dark_fraction < 0.45
            ):
                return None

            review_y1 = int(height * 0.79)
            review_y2 = int(height * 0.87)
            review_x1 = int(width * 0.03)
            review_x2 = int(width * 0.88)

            review = frame[
                review_y1:review_y2,
                review_x1:review_x2
            ]

            hsv = cv2.cvtColor(
                review,
                cv2.COLOR_BGR2HSV
            )

            green_mask = (
                (hsv[:, :, 0] >= 30)
                & (hsv[:, :, 0] <= 95)
                & (hsv[:, :, 1] >= 60)
                & (hsv[:, :, 2] >= 70)
            )

            green_fraction = float(
                np.mean(green_mask)
            )

            if green_fraction < 0.035:
                return None

            # Center of the right-side New <time-control> button.
            # The text can vary, but the button position is stable.
            return (
                int(width * 0.735),
                int(height * 0.392)
            )

        except Exception:
            return None

    def wait_for_initial_match(
        sct,
        hwnd,
        board_coords
    ):
        """Wait until an actual chess position is visible after L.

        Blank board/searching/matchmaking frames never become GAME READY.
        The helper returns only after the real initial position is visible
        and strictly verified. Human-White first move is also accepted.
        """
        last_ready_key = None
        ready_samples = 0

        while True:
            candidate_frame = capture_screen(
                sct,
                hwnd
            )

            if candidate_frame is None:
                time.sleep(0.10)
                continue

            grid, _, _ = scan_board(
                candidate_frame,
                board_coords
            )

            detected_piece_count = sum(
                1
                for row in grid
                for symbol in row
                if symbol is not None
            )

            if detected_piece_count < 20:
                ready_samples = 0
                last_ready_key = None
                time.sleep(0.10)
                continue

            start_board = chess.Board(
                INITIAL_FEN
            )

            ready_key = None

            for black_perspective in (
                False,
                True
            ):
                full_ok, _ = (
                    full_board_state_confirmed(
                        candidate_frame,
                        start_board,
                        board_coords,
                        black_perspective
                    )
                )

                if full_ok:
                    ready_key = (
                        f"{int(black_perspective)}:START"
                    )
                    break

                if black_perspective:
                    first_move = (
                        detect_existing_white_first_move(
                            candidate_frame,
                            start_board,
                            board_coords,
                            black_perspective
                        )
                    )

                    if first_move is not None:
                        expected_board = (
                            expected_board_after_move(
                                start_board,
                                first_move
                            )
                        )

                        first_ok, _ = (
                            full_board_state_confirmed(
                                candidate_frame,
                                expected_board,
                                board_coords,
                                black_perspective
                            )
                        )

                        if first_ok:
                            ready_key = (
                                f"{int(black_perspective)}:"
                                f"{first_move.uci()}"
                            )
                            break

            if ready_key is None:
                ready_samples = 0
                last_ready_key = None

                progress(
                    "MATCH",
                    "waiting for chess pieces / real game board",
                    key="initial_match_wait",
                    interval=0.50
                )

                time.sleep(0.10)
                continue

            if ready_key == last_ready_key:
                ready_samples += 1
            else:
                last_ready_key = ready_key
                ready_samples = 1

            if ready_samples >= 2:
                print(
                    "[MATCH] Real chess board detected | "
                    f"state={ready_key}"
                )
                return (
                    candidate_frame,
                    grid
                )

            time.sleep(0.10)

    # ============================================================
    # ULTIMATE_GM_BULLET.BIN — exact Colab Polyglot book behavior.
    # The book is checked on every Stockfish turn while we remain
    # in-book. Once a position has no book entry, we permanently
    # switch to the human-like MultiPV selector, exactly like Colab.
    # The actual move execution/verification below remains unchanged.
    # ============================================================
    from chess import polyglot

    book_path = os.path.join(
        os.getcwd(),
        "Ultimate_GM_Bullet.bin"
    )
    book_reader = None
    out_of_book = False

    if os.path.exists(book_path):
        try:
            book_reader = polyglot.open_reader(
                book_path
            )
            print(
                "[BOOK] Ultimate_GM_Bullet.bin loaded:"
                f" {book_path}"
            )
        except Exception as e:
            print(
                f"[BOOK] Could not open Ultimate_GM_Bullet.bin: {e}"
            )
    else:
        print(
            "[BOOK] WARNING: Ultimate_GM_Bullet.bin not found: "
            f"{book_path}"
        )

    with mss.mss() as sct:
        try:
            while True:
                key = cv2.waitKey(
                    1
                ) & 0xFF

                if key == ord("q"):
                    break

                if (
                    not scrcpy_hwnd
                    or not user32.IsWindow(
                        scrcpy_hwnd
                    )
                ):
                    scrcpy_hwnd = find_scrcpy_window()

                frame = capture_screen(
                    sct,
                    scrcpy_hwnd
                )

                if frame is None:
                    time.sleep(
                        0.02
                    )
                    continue

                display_frame = frame.copy()

                if (
                    game_ready
                    and grid_locked
                    and cached_board_coords
                    and baseline_frame is not None
                    and not awaiting_new_match
                ):
                    screen_interrupt_fraction = (
                        board_interruption_fraction(
                            baseline_frame,
                            frame,
                            cached_board_coords
                        )
                    )

                    if screen_interrupt_fraction > 0.10:
                        screen_interrupt_bad_samples += 1
                        screen_interrupt_clear_samples = 0

                        if (
                            screen_interrupt_bad_samples >= 2
                            and not screen_interrupted
                        ):
                            screen_interrupted = True
                            print(
                                "[SCREEN GUARD] PAUSED | "
                                f"unexpected board obstruction="
                                f"{screen_interrupt_fraction * 100.0:.1f}% "
                                "| no move/click will be issued"
                            )
                    elif screen_interrupted:
                        screen_interrupt_bad_samples = 0
                        screen_interrupt_clear_samples += 1

                        if screen_interrupt_clear_samples >= 3:
                            screen_interrupted = False
                            screen_interrupt_clear_samples = 0
                            print(
                                "[SCREEN GUARD] RESUMED | "
                                "board visibility restored"
                            )
                    else:
                        screen_interrupt_bad_samples = 0
                        screen_interrupt_clear_samples = 0
                else:
                    screen_interrupt_fraction = 0.0
                    screen_interrupt_bad_samples = 0
                    screen_interrupt_clear_samples = 0

                if key == ord("r"):
                    height, width = frame.shape[:2]

                    board_size = (
                        min(
                            width,
                            height
                        )
                        - 40
                    )

                    start_x = (
                        width
                        - board_size
                    ) // 2

                    start_y = (
                        height
                        - board_size
                    ) // 2

                    cached_board_coords = [
                        start_x,
                        start_y,
                        board_size,
                        board_size
                    ]

                    clear_runtime_caches()

                    grid_locked = False
                    game_ready = False
                    baseline_frame = None
                    awaiting_new_match = False
                    new_match_button_stable = 0
                    new_match_button_center = None
                    last_new_match_click = 0.0
                    next_new_match_scan = 0.0
                    new_match_click_attempts = 0
                    new_match_start_stable = 0
                    new_match_start_key = None
                    new_match_scan_ms = 0.0
                    screen_interrupted = False
                    screen_interrupt_bad_samples = 0
                    screen_interrupt_clear_samples = 0
                    screen_interrupt_fraction = 0.0
                    analysis_state = None
                    out_of_book = False

                    opponent_match_history.clear()

                    next_human_best_uci = None
                    opponent_pressure = False
                    _advantage_progress_target_cp = None
                    _advantage_progress_hold_moves = 0
                    _advantage_progress_hold_limit = random.randint(
                        HUMAN_ADVANTAGE_HOLD_MIN_MOVES,
                        HUMAN_ADVANTAGE_HOLD_MAX_MOVES
                    )
                    _advantage_progress_side = None

                    status = (
                        "UNLOCKED - "
                        "ADJUST GRID, THEN PRESS L"
                    )

                    print(
                        "\n[INFO] Grid initialized."
                    )

                    print(
                        "[INFO] Adjust W/A/S/D/+/-"
                    )

                    print(
                        "[INFO] Press L when correct."
                    )

                if (
                    cached_board_coords
                    and not grid_locked
                ):
                    step = 2

                    if key == ord("w"):
                        cached_board_coords[1] -= step

                    elif key == ord("s"):
                        cached_board_coords[1] += step

                    elif key == ord("a"):
                        cached_board_coords[0] -= step

                    elif key == ord("d"):
                        cached_board_coords[0] += step

                    elif key in (
                        ord("="),
                        ord("+")
                    ):
                        cached_board_coords[2] += step
                        cached_board_coords[3] += step

                    elif key in (
                        ord("-"),
                        ord("_")
                    ):
                        cached_board_coords[2] -= step
                        cached_board_coords[3] -= step

                if (
                    key == ord("l")
                    and cached_board_coords
                ):
                    grid_locked = not grid_locked

                    if grid_locked:
                        awaiting_new_match = False
                        new_match_button_stable = 0
                        new_match_button_center = None
                        new_match_click_attempts = 0
                        new_match_start_stable = 0
                        new_match_start_key = None
                        new_match_scan_ms = 0.0

                        clear_runtime_caches()

                        (
                            locked_frame,
                            locked_grid
                        ) = wait_for_initial_match(
                            sct,
                            scrcpy_hwnd,
                            cached_board_coords
                        )

                        if (
                            locked_frame is None
                            or locked_grid is None
                        ):
                            grid_locked = False
                            game_ready = False

                            print(
                                "[ERROR] Could not scan board."
                            )

                        else:
                            visual_black_perspective = (
                                detect_board_orientation(
                                    locked_grid,
                                    board
                                )
                            )

                            stockfish_color = (
                                detect_bottom_stockfish_color(
                                    visual_black_perspective
                                )
                            )

                            human_color = (
                                chess.BLACK
                                if stockfish_color == chess.WHITE
                                else chess.WHITE
                            )

                            cached_board_grid = locked_grid
                            baseline_frame = locked_frame

                            if human_color == chess.WHITE:
                                first_move = detect_existing_white_first_move(
                                    locked_frame,
                                    board,
                                    cached_board_coords,
                                    visual_black_perspective
                                )

                                if first_move is not None:
                                    expected_first_board = expected_board_after_move(
                                        board,
                                        first_move
                                    )

                                    (
                                        first_ok,
                                        first_verified_frame,
                                        first_reason
                                    ) = verify_human_move_on_screen(
                                        sct,
                                        scrcpy_hwnd,
                                        expected_first_board,
                                        locked_frame,
                                        cached_board_coords,
                                        visual_black_perspective,
                                        first_move,
                                        board.copy(stack=False)
                                    )

                                    if first_ok:
                                        san = board.san(first_move)
                                        board.push(first_move)
                                        baseline_frame = (
                                            first_verified_frame
                                            if first_verified_frame is not None
                                            else locked_frame
                                        )
                                        print(
                                            f"[SYNC] White-human first move detected: {first_move.uci()}"
                                        )
                                        print(
                                            f"[SYNC] Board advanced to: {san}"
                                        )
                                        print(
                                            f"[SYNC] Physical board verified: {first_reason}"
                                        )
                                        print(
                                            f"[SYNC] Turn = {'BLACK' if board.turn == chess.BLACK else 'WHITE'} / "
                                            f"{'STOCKFISH' if board.turn == stockfish_color else 'HUMAN'}"
                                        )
                                    else:
                                        print(
                                            f"[SYNC] First move rejected; internal board NOT advanced: {first_move.uci()} | {first_reason}"
                                        )

                            game_ready = True
                            analysis_state = None

                            opponent_match_history.clear()
                            next_human_best_uci = None
                            opponent_pressure = False
                            _advantage_progress_target_cp = None
                            _advantage_progress_hold_moves = 0
                            _advantage_progress_hold_limit = random.randint(
                                HUMAN_ADVANTAGE_HOLD_MIN_MOVES,
                                HUMAN_ADVANTAGE_HOLD_MAX_MOVES
                            )
                            _advantage_progress_side = None
                            last_bot_position_key = None
                            pending_bot_moves.clear()

                            stockfish_moves_since_buffer = 0

                            next_buffer_after = random.randint(
                                RANDOM_BUFFER_MOVE_MIN,
                                RANDOM_BUFFER_MOVE_MAX
                            )

                            print(
                                "[INFO] Bottom side:",
                                (
                                    "BLACK"
                                    if stockfish_color == chess.BLACK
                                    else "WHITE"
                                )
                            )

                            print(
                                "[INFO] Stockfish:",
                                (
                                    "BLACK"
                                    if stockfish_color == chess.BLACK
                                    else "WHITE"
                                )
                            )

                            print(
                                "[INFO] Human:",
                                (
                                    "BLACK"
                                    if human_color == chess.BLACK
                                    else "WHITE"
                                )
                            )

                            print(
                                "[INFO] First move is WHITE."
                            )

                            print(
                                "[INFO] Game READY."
                            )

                    else:
                        game_ready = False
                        baseline_frame = None

                        clear_runtime_caches()

                        print(
                            "[INFO] Grid UNLOCKED."
                        )

                if (
                    key == ord("f")
                    and cached_board_coords
                ):
                    clear_runtime_caches()

                    (
                        fresh_frame,
                        fresh_grid
                    ) = stable_initial_scan(
                        sct,
                        scrcpy_hwnd,
                        cached_board_coords
                    )

                    if (
                        fresh_frame is not None
                        and fresh_grid is not None
                    ):
                        visual_black_perspective = (
                            detect_board_orientation(
                                fresh_grid,
                                board
                            )
                        )

                        stockfish_color = (
                            detect_bottom_stockfish_color(
                                visual_black_perspective
                            )
                        )

                        human_color = (
                            chess.BLACK
                            if stockfish_color == chess.WHITE
                            else chess.WHITE
                        )

                        cached_board_grid = fresh_grid
                        baseline_frame = fresh_frame

                        if human_color == chess.WHITE:
                            first_move = detect_existing_white_first_move(
                                fresh_frame,
                                board,
                                cached_board_coords,
                                visual_black_perspective
                            )

                            if first_move is not None:
                                expected_first_board = expected_board_after_move(
                                    board,
                                    first_move
                                )

                                (
                                    first_ok,
                                    first_verified_frame,
                                    first_reason
                                ) = verify_human_move_on_screen(
                                    sct,
                                    scrcpy_hwnd,
                                    expected_first_board,
                                    fresh_frame,
                                    cached_board_coords,
                                    visual_black_perspective,
                                    first_move,
                                    board.copy(stack=False)
                                )

                                if first_ok:
                                    san = board.san(first_move)
                                    board.push(first_move)
                                    baseline_frame = (
                                        first_verified_frame
                                        if first_verified_frame is not None
                                        else fresh_frame
                                    )
                                    print(
                                        f"[SYNC] White-human first move detected: {first_move.uci()}"
                                    )
                                    print(
                                        f"[SYNC] Board advanced to: {san}"
                                    )
                                    print(
                                        f"[SYNC] Physical board verified: {first_reason}"
                                    )
                                    print(
                                        f"[SYNC] Turn = {'BLACK' if board.turn == chess.BLACK else 'WHITE'} / "
                                        f"{'STOCKFISH' if board.turn == stockfish_color else 'HUMAN'}"
                                    )
                                else:
                                    print(
                                        f"[SYNC] First move rejected; internal board NOT advanced: {first_move.uci()} | {first_reason}"
                                    )

                        opponent_match_history.clear()
                        out_of_book = False
                        next_human_best_uci = None
                        last_bot_position_key = None
                        pending_bot_moves.clear()

                        stockfish_moves_since_buffer = 0

                        next_buffer_after = random.randint(
                            RANDOM_BUFFER_MOVE_MIN,
                            RANDOM_BUFFER_MOVE_MAX
                        )

                        game_ready = True

                        print(
                            "[INFO] Bottom side:",
                            (
                                "BLACK"
                                if stockfish_color == chess.BLACK
                                else "WHITE"
                            )
                        )

                        print(
                            "[INFO] Stockfish:",
                            (
                                "BLACK"
                                if stockfish_color == chess.BLACK
                                else "WHITE"
                            )
                        )

                        print(
                            "[INFO] Human:",
                            (
                                "BLACK"
                                if human_color == chess.BLACK
                                else "WHITE"
                            )
                        )

                # ============================================================
                # RESULT SCREEN -> NEW MATCH LIFECYCLE
                # ============================================================
                if (
                    grid_locked
                    and cached_board_coords
                    and not awaiting_new_match
                ):
                    result_button = detect_new_game_button(
                        frame
                    )

                    if result_button is not None:
                        result_obstruction = 0.0

                        if baseline_frame is not None:
                            result_obstruction = (
                                board_interruption_fraction(
                                    baseline_frame,
                                    frame,
                                    cached_board_coords
                                )
                            )

                        result_screen = (
                            board.is_game_over()
                            or result_obstruction > 0.10
                        )

                        if result_screen:
                            button_changed = (
                                new_match_button_center is None
                                or (
                                    abs(
                                        result_button[0]
                                        - new_match_button_center[0]
                                    )
                                    > frame.shape[1] * 0.04
                                )
                                or (
                                    abs(
                                        result_button[1]
                                        - new_match_button_center[1]
                                    )
                                    > frame.shape[0] * 0.04
                                )
                            )

                            if button_changed:
                                new_match_button_center = result_button
                                new_match_button_stable = 1
                            else:
                                new_match_button_stable += 1

                            if new_match_button_stable >= 2:
                                now = time.perf_counter()

                                if (
                                    now - last_new_match_click
                                    >= 0.50
                                ):
                                    origin = get_scrcpy_screen_origin(
                                        scrcpy_hwnd
                                    )

                                    if (
                                        origin is not None
                                        and focus_scrcpy(scrcpy_hwnd)
                                    ):
                                        click_x = (
                                            origin[0]
                                            + result_button[0]
                                        )
                                        click_y = (
                                            origin[1]
                                            + result_button[1]
                                        )

                                        left_click_screen(
                                            click_x,
                                            click_y
                                        )

                                        last_new_match_click = (
                                            time.perf_counter()
                                        )
                                        new_match_click_attempts += 1

                                        print(
                                            "[MATCH] New-button click "
                                            f"attempt "
                                            f"{new_match_click_attempts}/3"
                                        )

                                        # Do not enter matchmaking until the
                                        # click is visibly acknowledged. If the
                                        # same result-page button is still
                                        # present, the click did not register
                                        # (or the page did not leave the result
                                        # state yet), so a controlled retry is
                                        # allowed.
                                        click_ack_deadline = (
                                            time.perf_counter()
                                            + 0.60
                                        )
                                        button_still_present = True

                                        while (
                                            time.perf_counter()
                                            < click_ack_deadline
                                        ):
                                            ack_frame = capture_screen(
                                                sct,
                                                scrcpy_hwnd
                                            )

                                            if ack_frame is None:
                                                time.sleep(
                                                    0.03
                                                )
                                                continue

                                            ack_button = (
                                                detect_new_game_button(
                                                    ack_frame
                                                )
                                            )

                                            if ack_button is None:
                                                button_still_present = False
                                                break

                                            time.sleep(
                                                0.03
                                            )

                                        if not button_still_present:
                                            awaiting_new_match = True
                                            game_ready = False
                                            cached_board_grid = None
                                            baseline_frame = None
                                            screen_interrupted = False
                                            screen_interrupt_bad_samples = 0
                                            screen_interrupt_clear_samples = 0
                                            screen_interrupt_fraction = 0.0

                                            new_match_button_stable = 0
                                            new_match_button_center = None
                                            new_match_click_attempts = 0
                                            next_new_match_scan = (
                                                time.perf_counter()
                                                + 0.50
                                            )
                                            new_match_start_stable = 0
                                            new_match_start_key = None
                                            new_match_scan_ms = 0.0

                                            print(
                                                "[MATCH] New-button click "
                                                "confirmed | entering matchmaking"
                                            )
                                        else:
                                            print(
                                                "[MATCH] New-button click "
                                                "not confirmed; result screen "
                                                "still present"
                                            )

                                            if (
                                                new_match_click_attempts
                                                >= 3
                                            ):
                                                new_match_click_attempts = 0
                                                new_match_button_stable = 0
                                                new_match_button_center = None

                                                print(
                                                    "[MATCH] New-button click "
                                                    "failed 3/3 times | "
                                                    "will re-detect result screen"
                                                )

                # ============================================================
                # MATCHMAKING -> FRESH GAME DETECTION
                # ============================================================
                if (
                    awaiting_new_match
                    and grid_locked
                    and cached_board_coords
                ):
                    now = time.perf_counter()

                    if now >= next_new_match_scan:
                        next_new_match_scan = (
                            now + 0.25
                        )

                        fresh_grid, fresh_confidence, fresh_scan_ms = (
                            scan_board(
                                frame,
                                cached_board_coords
                            )
                        )

                        new_match_scan_ms = fresh_scan_ms

                        fresh_board = chess.Board(
                            INITIAL_FEN
                        )

                        fresh_black_perspective = (
                            detect_board_orientation(
                                fresh_grid,
                                fresh_board
                            )
                        )

                        fresh_stockfish_color = (
                            detect_bottom_stockfish_color(
                                fresh_black_perspective
                            )
                        )

                        fresh_human_color = (
                            chess.BLACK
                            if fresh_stockfish_color == chess.WHITE
                            else chess.WHITE
                        )

                        fresh_start_verified = False
                        fresh_first_move = None
                        fresh_start_key = None

                        # Exact untouched starting position.
                        fresh_initial_ok, _ = (
                            full_board_state_confirmed(
                                frame,
                                fresh_board,
                                cached_board_coords,
                                fresh_black_perspective
                            )
                        )

                        if fresh_initial_ok:
                            fresh_start_verified = True
                            fresh_start_key = (
                                f"{int(fresh_black_perspective)}:START"
                            )

                        # Human-White may already have made the first move
                        # before this polling frame arrived. Reuse the existing
                        # first-move detector and its strict physical check.
                        elif fresh_human_color == chess.WHITE:
                            fresh_first_move = (
                                detect_existing_white_first_move(
                                    frame,
                                    fresh_board,
                                    cached_board_coords,
                                    fresh_black_perspective
                                )
                            )

                            if fresh_first_move is not None:
                                fresh_start_verified = True
                                fresh_start_key = (
                                    f"{int(fresh_black_perspective)}:"
                                    f"{fresh_first_move.uci()}"
                                )

                        if fresh_start_verified:
                            if fresh_start_key == new_match_start_key:
                                new_match_start_stable += 1
                            else:
                                new_match_start_key = fresh_start_key
                                new_match_start_stable = 1

                            if new_match_start_stable >= 2:
                                board = fresh_board

                                visual_black_perspective = (
                                    fresh_black_perspective
                                )

                                stockfish_color = (
                                    fresh_stockfish_color
                                )

                                human_color = (
                                    fresh_human_color
                                )

                                cached_board_grid = fresh_grid
                                baseline_frame = frame

                                if fresh_first_move is not None:
                                    board.push(
                                        fresh_first_move
                                    )

                                awaiting_new_match = False
                                game_ready = True

                                out_of_book = False
                                analysis_state = None
                                opponent_match_history.clear()
                                next_human_best_uci = None
                                opponent_pressure = False
                                last_bot_position_key = None
                                pending_bot_moves.clear()
                                pending_recovered_human = None

                                stockfish_moves_since_buffer = 0
                                next_buffer_after = random.randint(
                                    RANDOM_BUFFER_MOVE_MIN,
                                    RANDOM_BUFFER_MOVE_MAX
                                )

                                _advantage_progress_target_cp = None
                                _advantage_progress_hold_moves = 0
                                _advantage_progress_hold_limit = random.randint(
                                    HUMAN_ADVANTAGE_HOLD_MIN_MOVES,
                                    HUMAN_ADVANTAGE_HOLD_MAX_MOVES
                                )
                                _advantage_progress_side = None

                                next_main_turn_rescan = (
                                    time.perf_counter()
                                    + TURN_RESCAN_INTERVAL
                                )

                                screen_interrupted = False
                                screen_interrupt_bad_samples = 0
                                screen_interrupt_clear_samples = 0
                                screen_interrupt_fraction = 0.0

                                new_match_start_stable = 0
                                new_match_start_key = None

                                print(
                                    "[MATCH] NEW GAME READY | "
                                    f"Stockfish="
                                    f"{'WHITE' if stockfish_color == chess.WHITE else 'BLACK'} "
                                    f"| Human="
                                    f"{'WHITE' if human_color == chess.WHITE else 'BLACK'}"
                                )

                                if fresh_first_move is not None:
                                    print(
                                        "[MATCH] White-human first move already present | "
                                        f"{fresh_first_move.uci()} | internal board synced"
                                    )
                            else:
                                progress(
                                    "MATCH",
                                    (
                                        "new board candidate stable "
                                        f"{new_match_start_stable}/2"
                                    ),
                                    key="new_match_stable",
                                    force=True
                                )
                        else:
                            new_match_start_stable = 0
                            new_match_start_key = None

                status = "READY - PRESS R"

                if (
                    grid_locked
                    and cached_board_coords
                ):
                    if awaiting_new_match:
                        status = (
                            "MATCHMAKING - WAITING FOR NEW GAME"
                        )
                    elif (
                        not game_ready
                        or stockfish_color is None
                    ):
                        status = (
                            "DETECT BOTTOM SIDE"
                        )

                    elif bot_thinking:
                        status = (
                            "STOCKFISH THINKING..."
                        )

                    elif (
                        board.turn
                        == stockfish_color
                    ):
                        status = (
                            "STOCKFISH TO MOVE | "
                            f"SCAN "
                            f"{last_scan_time_ms:.1f}ms"
                        )

                    else:
                        status = (
                            "WAITING HUMAN MOVE | "
                            f"SCAN "
                            f"{last_scan_time_ms:.1f}ms"
                        )

                    if screen_interrupted:
                        status = (
                            "PAUSED - SCREEN OBSTRUCTED | "
                            f"{screen_interrupt_fraction * 100.0:.1f}% BOARD"
                        )

                if (
                    game_ready
                    and grid_locked
                    and stockfish_color is not None
                    and not screen_interrupted
                    and not awaiting_new_match
                ):
                    if (
                        board.turn == human_color
                        and not bot_thinking
                    ):
                        progress(
                            "WAIT",
                            (
                                f"human "
                                f"{'WHITE' if human_color == chess.WHITE else 'BLACK'} "
                                "to move; scanning screen"
                            ),
                            key="turn_wait",
                            force=True
                        )

                        detection_source = None

                        if pending_recovered_human is not None:
                            move, move_frame = pending_recovered_human
                            pending_recovered_human = None
                            detection_source = "PERIODIC_FULL_RESCAN"
                            detect_human_move._last_detection_source = detection_source
                            print(
                                f"[RECOVERY] Consuming already-verified human move: {move.uci()}"
                            )
                        else:
                            (
                                move,
                                move_frame
                            ) = detect_human_move(
                                sct,
                                scrcpy_hwnd,
                                board,
                                baseline_frame,
                                cached_board_coords,
                                visual_black_perspective
                            )

                        if (
                            move is not None
                            and move_frame is not None
                        ):
                            san = board.san(
                                move
                            )

                            expected_human_uci = (
                                next_human_best_uci
                            )
                            opponent_pressure = False

                            if expected_human_uci:
                                exact_top_match = (
                                    100.0
                                    if move.uci()
                                    == expected_human_uci
                                    else 0.0
                                )

                                opponent_match_history.append(
                                    exact_top_match
                                )

                                (
                                    recent_accuracy,
                                    sample_count
                                ) = opponent_recent_accuracy(
                                    opponent_match_history
                                )

                                profile_now = adaptive_accuracy_profile(
                                    recent_accuracy,
                                    sample_count
                                )

                                opponent_pressure = not bool(exact_top_match)

                                print(
                                    f"[OPPONENT] "
                                    f"move={move.uci()} "
                                    f"expected=#1="
                                    f"{expected_human_uci} "
                                    f"TOP_MATCH="
                                    f"{'YES' if exact_top_match else 'NO'} "
                                    f"RECENT="
                                    f"{recent_accuracy:.1f}% "
                                    f"TARGET="
                                    f"{profile_now['target_accuracy']:.1f}% "
                                    f"{profile_now['state']}"
                                )

                            expected_human_board = expected_board_after_move(
                                board,
                                move
                            )

                            detection_source = getattr(
                                detect_human_move,
                                "_last_detection_source",
                                None
                            )
                            detect_human_move._last_detection_source = None

                            if detection_source in (
                                "ULTRA_DELTA",
                                "PERIODIC_FULL_RESCAN"
                            ):
                                # The ultra delta layer has already cross-validated
                                # the current board against the internal board in two
                                # scans and passed full-board physical verification.
                                # Do not run the old temporal-only verifier again on
                                # the same already-settled frame.
                                final_human_ok = True
                                final_human_frame = move_frame
                                final_human_reason = (
                                    "ultra internal-board delta + dual scan + "
                                    "full-board verification confirmed"
                                )
                            else:
                                (
                                    final_human_ok,
                                    final_human_frame,
                                    final_human_reason
                                ) = verify_human_move_on_screen(
                                    sct,
                                    scrcpy_hwnd,
                                    expected_human_board,
                                    baseline_frame,
                                    cached_board_coords,
                                    visual_black_perspective,
                                    move,
                                    board.copy(stack=False)
                                )

                            if not final_human_ok:
                                print(
                                    f"[HUMAN] Rejected before board.push(): "
                                    f"{move.uci()} | {final_human_reason}"
                                )

                                # This detected move was not physically verified,
                                # so undo only the provisional accuracy sample.
                                if expected_human_uci:
                                    if opponent_match_history:
                                        opponent_match_history.pop()

                                # Keep baseline_frame unchanged. It represents the
                                # last internally committed physical board state.
                                continue

                            move_frame = (
                                final_human_frame
                                if final_human_frame is not None
                                else move_frame
                            )

                            next_human_best_uci = None

                            board.push(
                                move
                            )

                            analysis_state = None

                            settled_frame = get_settled_frame(
                                sct,
                                scrcpy_hwnd,
                                move_frame,
                                timeout=HUMAN_SETTLE_TIMEOUT
                            )

                            baseline_frame = (
                                settled_frame
                                if settled_frame is not None
                                else move_frame
                            )

                            last_bot_position_key = None
                            pending_bot_moves.clear()
                            next_main_turn_rescan = time.perf_counter() + TURN_RESCAN_INTERVAL

                            print(
                                f"[HUMAN] Accepted: {san}"
                            )

                    if (
                        board.turn == stockfish_color
                        and not bot_thinking
                    ):
                        position_key = board.fen()

                        if (
                            position_key
                            != last_bot_position_key
                            or position_key
                            in pending_bot_moves
                        ):
                            bot_thinking = True

                            try:
                                pending_entry = (
                                    pending_bot_moves.get(
                                        position_key
                                    )
                                )

                                # Freeze the Stockfish decision for this board position.
                                # The same move is used for click, verification and retry.
                                locked_bot_move = None

                                if pending_entry is not None:
                                    locked_bot_move = (
                                        chess.Move.from_uci(
                                            pending_entry["uci"]
                                        )
                                    )
                                    best_move = locked_bot_move

                                    result = pending_entry[
                                        "result"
                                    ]

                                    best_info_move = pending_entry.get(
                                        "best_info_move"
                                    )

                                    best_san = pending_entry[
                                        "san"
                                    ]

                                    selection_meta = pending_entry.get(
                                        "selection_meta",
                                        {
                                            "rank": 0,
                                            "reason": "pending retry"
                                        }
                                    )

                                    engine_elapsed = 0.0

                                    print(
                                        "[STOCKFISH] "
                                        f"Retrying pending move: "
                                        f"{best_san}"
                                    )

                                else:
                                    # ========================================================
                                    # EXACT COLAB BOOK -> HUMAN-LIKE FALLBACK FLOW
                                    # ========================================================
                                    book_used = False

                                    if (
                                        book_reader is not None
                                        and not out_of_book
                                    ):
                                        try:
                                            book_entries = list(
                                                book_reader.find_all(
                                                    board
                                                )
                                            )
                                        except Exception as e:
                                            book_entries = []
                                            print(
                                                f"[BOOK] Lookup error: {e}"
                                            )

                                        if book_entries:
                                            chosen_book_entry = (
                                                book_reader.choice(
                                                    board
                                                )
                                            )

                                            best_move = (
                                                chosen_book_entry.move
                                            )

                                            if best_move not in board.legal_moves:
                                                raise RuntimeError(
                                                    "Polyglot book returned an illegal move."
                                                )

                                            result = None
                                            engine_elapsed = 0.0
                                            best_info_move = best_move
                                            best_san = board.san(
                                                best_move
                                            )
                                            selection_meta = {
                                                "rank": 0,
                                                "current_cp": 0,
                                                "selected_cp": 0,
                                                "reason": (
                                                    "BOOK | "
                                                    f"entries={len(book_entries)} | "
                                                    "weighted Polyglot choice"
                                                )
                                            }

                                            locked_bot_move = best_move

                                            pending_bot_moves[
                                                position_key
                                            ] = {
                                                "uci": best_move.uci(),
                                                "san": best_san,
                                                "result": result,
                                                "best_info_move": best_info_move,
                                                "selection_meta": selection_meta,
                                            }

                                            book_used = True

                                            print(
                                                "[BOOK] "
                                                f"POSITION IN BOOK | "
                                                f"entries={len(book_entries)} | "
                                                f"SELECTED={best_move.uci()} "
                                                f"{best_san} | "
                                                "weighted choice"
                                            )

                                        else:
                                            out_of_book = True

                                            print(
                                                "[BOOK] "
                                                "OUT OF BOOK -> switching to human-like engine logic"
                                            )

                                    if not book_used:
                                        print(
                                            "[STOCKFISH] Thinking..."
                                        )

                                        engine_start = time.perf_counter()

                                        multipv_result = engine.analyse(
                                            board,
                                            chess.engine.Limit(
                                                depth=STOCKFISH_DEPTH,
                                                time=HUMAN_LIKE_EVAL_TIME
                                            ),
                                            multipv=TRAINING_MULTI_PV
                                        )

                                        engine_elapsed = (
                                            time.perf_counter()
                                            - engine_start
                                        )

                                        if not isinstance(
                                            multipv_result,
                                            list
                                        ):
                                            multipv_result = [
                                                multipv_result
                                            ]

                                        result = multipv_result[0]

                                        selected_previous_eval = (
                                            analysis_state.get(
                                                "eval_cp"
                                            )
                                            if analysis_state is not None
                                            else None
                                        )

                                        (
                                            opponent_accuracy,
                                            opponent_sample_count
                                        ) = opponent_recent_accuracy(
                                            opponent_match_history
                                        )

                                        (
                                            best_move,
                                            selected_info,
                                            selection_meta
                                        ) = choose_stockfish_move(
                                            board,
                                            multipv_result,
                                            previous_eval_white_cp=selected_previous_eval,
                                            opponent_accuracy=opponent_accuracy,
                                            opponent_sample_count=opponent_sample_count,
                                            opponent_pressure=opponent_pressure,
                                            engine=engine
                                        )

                                        opponent_pressure = False

                                        if (
                                            best_move is None
                                            or best_move
                                            not in board.legal_moves
                                        ):
                                            raise RuntimeError(
                                                "Stockfish selector did not "
                                                "return a legal move."
                                            )

                                        # Freeze the newly selected Stockfish move immediately.
                                        locked_bot_move = best_move

                                        best_info_move = result.get(
                                            "pv",
                                            [None]
                                        )[0]

                                        best_san = board.san(
                                            best_move
                                        )

                                        pending_bot_moves[
                                            position_key
                                        ] = {
                                            "uci": best_move.uci(),
                                            "san": best_san,
                                            "result": result,
                                            "best_info_move": best_info_move,
                                            "selection_meta": selection_meta,
                                        }

                                        print(
                                            "[ENGINE] "
                                            f"depth={STOCKFISH_DEPTH} "
                                            f"time={engine_elapsed:.3f}s "
                                            f"MultiPV={len(multipv_result)}"
                                        )

                                        print(
                                            "[TRAINING] "
                                            f"BEST="
                                            f"{best_info_move.uci() if best_info_move else '-'} "
                                            f"SELECTED="
                                            f"{best_move.uci()} "
                                            f"RANK="
                                            f"#{selection_meta['rank'] + 1}"
                                        )

                                        print(
                                            "[TRAINING] "
                                            f"{selection_meta['reason']}"
                                        )

                                        (
                                            recent_accuracy,
                                            recent_samples
                                        ) = opponent_recent_accuracy(
                                            opponent_match_history
                                        )

                                        adaptive_profile = adaptive_accuracy_profile(
                                            recent_accuracy,
                                            recent_samples
                                        )

                                        print(
                                            "[ADAPT] "
                                            f"opponent="
                                            f"{recent_accuracy if recent_accuracy is not None else 0.0:.1f}% "
                                            f"target="
                                            f"{adaptive_profile['target_accuracy']:.1f}% "
                                            f"state="
                                            f"{adaptive_profile['state']} "
                                            f"rank_cap="
                                            f"#{adaptive_profile['max_rank'] + 1} "
                                            f"max_drop="
                                            f"{adaptive_profile['max_eval_drop']*100:.1f}%"
                                        )

                                # From this point until physical confirmation, only the
                                # frozen Stockfish decision is used; no fresh engine result
                                # can replace the move being clicked or verified.
                                if locked_bot_move is None:
                                    raise RuntimeError(
                                        "Stockfish move was not frozen."
                                    )
                                best_move = locked_bot_move

                                if best_move not in board.legal_moves:
                                    pending_bot_moves.pop(
                                        position_key,
                                        None
                                    )

                                    last_bot_position_key = None

                                    continue

                                # PENDING-MOVE RECOVERY:
                                # A previous click may already have landed even when
                                # transition verification missed it. Before doing ANY
                                # more click, compare the current physical board against
                                # the pending Stockfish move (and also bot+human in case
                                # the human already replied). This runs immediately on
                                # a pending retry, so a settled move is committed instead
                                # of being reported as a permanently frozen move.
                                verified = False
                                after_frame = None
                                reason = "pending Stockfish move not yet confirmed"

                                pending_recovery = None

                                if pending_entry is not None:
                                    pending_recovery = periodic_full_board_catchup_scan(
                                        sct,
                                        scrcpy_hwnd,
                                        board,
                                        cached_board_coords,
                                        visual_black_perspective,
                                        pending_bot_move=best_move,
                                        first_frame=None,
                                        legal_moves=list(board.legal_moves)
                                    )

                                    if (
                                        pending_recovery is not None
                                        and pending_recovery.get("bot_move") == best_move
                                        and pending_recovery.get("frame") is not None
                                        and pending_recovery.get("kind") in (
                                            "BOT_ONLY",
                                            "BOT_PLUS_HUMAN"
                                        )
                                    ):
                                        recovery_frame = pending_recovery["frame"]
                                        recovered_human = pending_recovery.get("human_move")

                                        if recovered_human is not None:
                                            pending_recovered_human = (
                                                recovered_human,
                                                recovery_frame
                                            )
                                            print(
                                                "[RECOVERY] Pending Stockfish move + human reply "
                                                "already on screen: "
                                                f"{best_san} + "
                                                f"{chess.square_name(recovered_human.from_square)}"
                                                f"{chess.square_name(recovered_human.to_square)}"
                                            )
                                        else:
                                            print(
                                                "[RECOVERY] Pending Stockfish move already on screen: "
                                                f"{best_san} | no additional click"
                                            )

                                        verified = True
                                        after_frame = recovery_frame
                                        reason = pending_recovery["reason"]

                                before_frame = capture_screen(
                                    sct,
                                    scrcpy_hwnd
                                )

                                if (
                                    not verified
                                    and before_frame is not None
                                    and baseline_frame is not None
                                ):
                                    immediate_obstruction_fraction = (
                                        board_interruption_fraction(
                                            baseline_frame,
                                            before_frame,
                                            cached_board_coords
                                        )
                                    )

                                    if immediate_obstruction_fraction > 0.10:
                                        print(
                                            "[SCREEN GUARD] PAUSED BEFORE CLICK | "
                                            f"unexpected board obstruction="
                                            f"{immediate_obstruction_fraction * 100.0:.1f}% "
                                            "| pending move remains uncommitted"
                                        )
                                        screen_interrupted = True
                                        screen_interrupt_bad_samples = 2
                                        screen_interrupt_clear_samples = 0
                                        screen_interrupt_fraction = (
                                            immediate_obstruction_fraction
                                        )
                                        last_bot_position_key = position_key
                                        continue

                                if before_frame is None and not verified:
                                    last_bot_position_key = (
                                        position_key
                                    )

                                    continue

                                # PROMOTION RECOVERY:
                                # The pawn move itself may already have landed and
                                # opened the promotion menu even when click/transition
                                # verification failed. In that state the source square
                                # is empty, so re-clicking source+destination would be
                                # wrong. First look ONLY for the exact promotion piece
                                # requested by Stockfish. No fallback location is used
                                # during this recovery probe, so it cannot click a random
                                # board square when no promotion menu is open.
                                if (
                                    not verified
                                    and best_move.promotion is not None
                                    and pending_entry is not None
                                ):
                                    promotion_recovered = select_promotion_piece(
                                        sct,
                                        scrcpy_hwnd,
                                        best_move,
                                        board.turn,
                                        cached_board_coords,
                                        visual_black_perspective,
                                        allow_fallback=False
                                    )

                                    if promotion_recovered:
                                        promotion_check_frame = capture_screen(
                                            sct,
                                            scrcpy_hwnd
                                        )

                                        if promotion_check_frame is not None:
                                            expected_promotion_board = expected_board_after_move(
                                                board,
                                                best_move
                                            )

                                            promotion_full_ok, promotion_full_reason = full_board_state_confirmed(
                                                promotion_check_frame,
                                                expected_promotion_board,
                                                cached_board_coords,
                                                visual_black_perspective
                                            )

                                            promotion_fast_ok = False
                                            promotion_fast_reason = ""

                                            if not promotion_full_ok:
                                                promotion_fast_ok, promotion_fast_reason = fast_expected_post_state_confirmed(
                                                    baseline_frame,
                                                    promotion_check_frame,
                                                    board,
                                                    best_move,
                                                    cached_board_coords,
                                                    visual_black_perspective
                                                )

                                            if promotion_full_ok or promotion_fast_ok:
                                                verified = True
                                                after_frame = promotion_check_frame
                                                reason = (
                                                    "promotion menu recovery confirmed; "
                                                    + (
                                                        promotion_full_reason
                                                        if promotion_full_ok
                                                        else promotion_fast_reason
                                                    )
                                                )
                                                print(
                                                    "[PROMOTION] PENDING RECOVERY SUCCESS | "
                                                    f"{best_san} -> "
                                                    f"{chess.piece_name(best_move.promotion).upper()}"
                                                )

                                if verified:
                                    pre_ok = True
                                    pre_reason = reason
                                else:
                                    # FAST pre-click path: the current frame is first
                                    # checked against the last verified physical board using
                                    # the cheap all-square motion map + exact source/target
                                    # checks. The expensive 64-square template scan is only
                                    # a fallback if the fast gate cannot prove safety.
                                    pre_reference = (
                                        baseline_frame
                                        if baseline_frame is not None
                                        else before_frame
                                    )
                                    pre_ok, pre_reason = fast_preclick_board_confirmed(
                                        pre_reference,
                                        before_frame,
                                        board,
                                        best_move,
                                        cached_board_coords,
                                        visual_black_perspective
                                    )

                                    if not pre_ok:
                                        full_pre_ok, full_pre_reason = full_board_state_confirmed(
                                            before_frame,
                                            board,
                                            cached_board_coords,
                                            visual_black_perspective
                                        )

                                        if full_pre_ok:
                                            pre_ok = True
                                            pre_reason = (
                                                "full-board pre-click fallback: "
                                                + full_pre_reason
                                            )

                                if not pre_ok:
                                    # Never click while the physical board is not
                                    # known to be the exact internal pre-move board.
                                    # A previous tap may still be settling; first
                                    # check whether the requested move has already
                                    # landed. Only a confirmed post-state can commit
                                    # the move. Otherwise keep waiting without any
                                    # internal board change and without declaring a
                                    # terminal desync.
                                    post_already_ok, post_already_reason = (
                                        screen_matches_expected_bot_move(
                                            before_frame,
                                            board,
                                            best_move,
                                            cached_board_coords,
                                            visual_black_perspective,
                                            baseline_frame
                                        )
                                    )

                                    if post_already_ok:
                                        verified = True
                                        after_frame = before_frame
                                        reason = post_already_reason
                                        print(
                                            "[VALIDATION] POST-STATE ALREADY PRESENT | "
                                            f"{best_move.uci()} | committing only after physical confirmation"
                                        )
                                    else:
                                        # The source mismatch can mean the Stockfish move
                                        # is already settled on screen. Re-check the complete
                                        # board before declaring the pending move blocked.
                                        late_recovery = periodic_full_board_catchup_scan(
                                            sct,
                                            scrcpy_hwnd,
                                            board,
                                            cached_board_coords,
                                            visual_black_perspective,
                                            pending_bot_move=best_move,
                                            first_frame=before_frame,
                                            legal_moves=list(board.legal_moves)
                                        )

                                        if (
                                            late_recovery is not None
                                            and late_recovery.get("bot_move") == best_move
                                            and late_recovery.get("frame") is not None
                                            and late_recovery.get("kind") in (
                                                "BOT_ONLY",
                                                "BOT_PLUS_HUMAN"
                                            )
                                        ):
                                            recovery_frame = late_recovery["frame"]
                                            recovered_human = late_recovery.get("human_move")

                                            if recovered_human is not None:
                                                pending_recovered_human = (
                                                    recovered_human,
                                                    recovery_frame
                                                )

                                            verified = True
                                            after_frame = recovery_frame
                                            reason = late_recovery["reason"]
                                            print(
                                                "[RECOVERY] Pending move recovered from full-board state: "
                                                f"{best_san}"
                                                + (
                                                    " + human reply already present"
                                                    if recovered_human is not None
                                                    else ""
                                                )
                                            )
                                        else:
                                            last_bot_position_key = position_key
                                            print(
                                                "[VALIDATION] WAITING | pending Stockfish move "
                                                "not yet physically confirmed; no click and no board.push() | "
                                                f"{pre_reason}"
                                            )
                                            time.sleep(BOT_RECOVERY_POLL)
                                            continue

                                if (
                                    stockfish_moves_since_buffer
                                    >= next_buffer_after
                                ):
                                    buffer_delay = random.choice(
                                        RANDOM_BUFFER_OPTIONS
                                    )

                                    print(
                                        "[BOT BUFFER] "
                                        f"after "
                                        f"{stockfish_moves_since_buffer} "
                                        f"Stockfish moves -> "
                                        f"{buffer_delay:.1f}s"
                                    )

                                    if buffer_delay > 0.0:
                                        time.sleep(buffer_delay)

                                    stockfish_moves_since_buffer = 0

                                    next_buffer_after = random.randint(
                                        RANDOM_BUFFER_MOVE_MIN,
                                        RANDOM_BUFFER_MOVE_MAX
                                    )

                                if not verified:
                                    if screen_interrupted:
                                        print(
                                            "[SCREEN GUARD] CLICK BLOCKED | "
                                            "screen interruption active"
                                        )
                                        last_bot_position_key = position_key
                                        continue

                                    print(
                                        "[VALIDATION] PRE-CLICK PASS | "
                                        "physical board matches internal board 64/64"
                                    )

                                    clicked = click_move(
                                        best_move,
                                        cached_board_coords,
                                        visual_black_perspective,
                                        scrcpy_hwnd,
                                        sct=sct,
                                        promotion_color=board.turn
                                    )

                                    if not clicked:
                                        print(
                                            "[BOT] CLICK DISPATCH FAILED | "
                                            f"pending={best_move.uci()} | "
                                            "no board change; will retry normally"
                                        )

                                        last_bot_position_key = (
                                            position_key
                                        )

                                        continue

                                    (
                                        verified,
                                        after_frame,
                                        reason
                                    ) = verify_bot_move(
                                        sct,
                                        scrcpy_hwnd,
                                        board,
                                        best_move,
                                        before_frame,
                                        cached_board_coords,
                                        visual_black_perspective
                                    )

                                    retry_count = 0

                                    while (
                                        not verified
                                        and retry_count
                                        < BOT_CLICK_RETRIES
                                    ):
                                        retry_count += 1

                                        # EXTRA 2-second whole-board catch-up while a
                                        # frozen Stockfish move is being retried. This
                                        # specifically handles: bot move already on
                                        # screen + human reply already on screen.
                                        now_rescan = time.perf_counter()
                                        if now_rescan >= next_main_turn_rescan:
                                            catchup = periodic_full_board_catchup_scan(
                                                sct,
                                                scrcpy_hwnd,
                                                board,
                                                cached_board_coords,
                                                visual_black_perspective,
                                                pending_bot_move=best_move,
                                                first_frame=None,
                                                legal_moves=list(board.legal_moves)
                                            )
                                            next_main_turn_rescan = (
                                                now_rescan + TURN_RESCAN_INTERVAL
                                            )

                                            if (
                                                catchup is not None
                                                and catchup.get("bot_move") == best_move
                                                and catchup.get("frame") is not None
                                                and catchup.get("kind") in (
                                                    "BOT_ONLY",
                                                    "BOT_PLUS_HUMAN"
                                                )
                                            ):
                                                recovery_frame = catchup["frame"]
                                                recovered_human = catchup.get("human_move")

                                                # The normal verified-Stockfish commit below
                                                # will push only the pending bot move. If a
                                                # human reply is already visible too, queue
                                                # that verified move for the human branch so
                                                # it is consumed immediately after the bot
                                                # position is committed.
                                                if recovered_human is not None:
                                                    pending_recovered_human = (
                                                        recovered_human,
                                                        recovery_frame
                                                    )
                                                    print(
                                                        "[RECOVERY] Found bot+human already "
                                                        f"on screen: {best_san} + "
                                                        f"{board.san(recovered_human) if recovered_human in expected_board_after_move(board, best_move).legal_moves else recovered_human.uci()}"
                                                    )

                                                verified = True
                                                after_frame = recovery_frame
                                                reason = catchup["reason"]
                                                break

                                        retry_frame = capture_screen(
                                            sct,
                                            scrcpy_hwnd
                                        )

                                        post_ok, post_reason = (
                                            screen_matches_expected_bot_move(
                                                retry_frame,
                                                board,
                                                best_move,
                                                cached_board_coords,
                                                visual_black_perspective,
                                                before_frame
                                            )
                                        )

                                        if post_ok:
                                            verified = True
                                            after_frame = retry_frame
                                            reason = post_reason
                                            break

                                        pre_retry_ok, pre_retry_reason = fast_preclick_board_confirmed(
                                            before_frame,
                                            retry_frame,
                                            board,
                                            best_move,
                                            cached_board_coords,
                                            visual_black_perspective
                                        )

                                        if not pre_retry_ok:
                                            # Do not click through an intermediate/unknown
                                            # frame. Leave the frozen move pending and let
                                            # the next loop confirm the exact pre-state or
                                            # already-landed post-state.
                                            print(
                                                "[VALIDATION] WAITING RETRY | physical board "
                                                "not yet stable; no additional click | "
                                                f"{pre_retry_reason}"
                                            )
                                            break

                                        print(
                                            "[BOT] "
                                            f"Click retry "
                                            f"{retry_count}/"
                                            f"{BOT_CLICK_RETRIES}"
                                        )

                                        clicked_retry = click_move(
                                            best_move,
                                            cached_board_coords,
                                            visual_black_perspective,
                                            scrcpy_hwnd,
                                            sct=sct,
                                            promotion_color=board.turn
                                        )

                                        if not clicked_retry:
                                            break

                                        (
                                            verified,
                                            after_frame,
                                            reason
                                        ) = verify_bot_move(
                                            sct,
                                            scrcpy_hwnd,
                                            board,
                                            best_move,
                                            retry_frame,
                                            cached_board_coords,
                                            visual_black_perspective
                                        )

                                if (
                                    verified
                                    and after_frame is not None
                                ):
                                    before_board = board.copy()

                                    board.push(
                                        best_move
                                    )

                                    analysis_state = build_analysis(
                                        engine,
                                        before_board,
                                        board,
                                        best_move,
                                        best_info=result
                                    )

                                    if analysis_state:
                                        predicted = analysis_state.get(
                                            "best_move"
                                        )

                                        next_human_best_uci = (
                                            predicted
                                            if predicted
                                            and predicted != "-"
                                            else None
                                        )

                                    else:
                                        next_human_best_uci = None

                                    settled_frame = get_settled_frame(
                                        sct,
                                        scrcpy_hwnd,
                                        after_frame,
                                        timeout=0.10
                                    )

                                    baseline_frame = (
                                        settled_frame
                                        if settled_frame is not None
                                        else after_frame
                                    )

                                    (
                                        cached_board_grid,
                                        _,
                                        last_scan_time_ms
                                    ) = scan_board(
                                        baseline_frame,
                                        cached_board_coords
                                    )

                                    pending_bot_moves.pop(
                                        position_key,
                                        None
                                    )

                                    last_bot_position_key = None
                                    next_main_turn_rescan = time.perf_counter() + TURN_RESCAN_INTERVAL

                                    stockfish_moves_since_buffer += 1

                                    print(
                                        f"[VALIDATION] "
                                        f"PASS | {reason}"
                                    )

                                    print_game_state(
                                        board,
                                        stockfish_color,
                                        human_color,
                                        visual_black_perspective,
                                        f"[STOCKFISH] Confirmed: {best_san}",
                                        analysis_state
                                    )

                                else:
                                    # Verification failure is recoverable. Keep the exact
                                    # Stockfish move pending, but do NOT label it as a
                                    # permanent/frozen state. The next iteration first
                                    # checks whether the move already landed, then clicks
                                    # again only when the true internal pre-state is visible.
                                    last_bot_position_key = position_key
                                    print(
                                        "[VALIDATION] WAITING | "
                                        f"pending={best_move.uci()} "
                                        "| physical post-state not yet confirmed; "
                                        "internal board NOT advanced | "
                                        f"{reason}"
                                    )
                                    time.sleep(BOT_RECOVERY_POLL)

                            except Exception as e:
                                print(
                                    f"[STOCKFISH ERROR] {e}"
                                )

                            finally:
                                bot_thinking = False

                    if board.is_game_over():
                        game_ready = False

                        print_game_state(
                            board,
                            stockfish_color,
                            human_color,
                            visual_black_perspective,
                            f"GAME OVER: {board.outcome()}"
                        )

                if (
                    grid_locked
                    and game_ready
                    and not bot_thinking
                ):
                    current_status = status
                    now = time.perf_counter()

                    if (
                        current_status
                        != last_wait_status
                        or
                        now - last_wait_report
                        >= 1.5
                    ):
                        progress(
                            "STATE",
                            current_status,
                            key="state",
                            force=True
                        )

                        last_wait_status = current_status
                        last_wait_report = now

                if cached_board_coords:
                    draw_overlay(
                        display_frame,
                        cached_board_coords,
                        cached_board_grid,
                        grid_locked,
                        visual_black_perspective,
                        last_scan_time_ms,
                        status,
                        (
                            stockfish_color
                            if stockfish_color is not None
                            else chess.BLACK
                        ),
                        (
                            human_color
                            if human_color is not None
                            else chess.WHITE
                        ),
                        analysis_state
                    )

                else:
                    cv2.rectangle(
                        display_frame,
                        (0, 0),
                        (
                            frame.shape[1],
                            48
                        ),
                        (0, 0, 0),
                        -1
                    )

                    cv2.putText(
                        display_frame,
                        "PRESS R TO INITIALIZE BOARD",
                        (8, 28),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.55,
                        (0, 255, 255),
                        2
                    )

                cv2.imshow(
                    "Chess Vision Tracker",
                    display_frame
                )

        finally:
            cv2.destroyAllWindows()

            if book_reader is not None:
                try:
                    book_reader.close()
                except Exception:
                    pass

            try:
                engine.quit()
            except Exception:
                pass


