# Exact function source extracted from original main.py.

def format_eval(cp):
    if cp >= 100000:
        return "MATE WHITE"

    if cp <= -100000:
        return "MATE BLACK"

    return f"{cp / 100.0:+.2f}"


def favor_text(cp):
    if cp >= 100000:
        return "WHITE MATE"

    if cp <= -100000:
        return "BLACK MATE"

    if abs(cp) <= 8:
        return "EQUAL"

    side = (
        "WHITE"
        if cp > 0
        else "BLACK"
    )

    return (
        f"{side} "
        f"+{abs(cp) / 100.0:.2f}"
    )


def material_value(
    piece_type
):
    return {
        chess.PAWN: 100,
        chess.KNIGHT: 320,
        chess.BISHOP: 330,
        chess.ROOK: 500,
        chess.QUEEN: 900,
        chess.KING: 0,
    }.get(
        piece_type,
        0
    )


def side_material(
    board,
    color
):
    total = 0

    for square, piece in board.piece_map().items():
        if piece.color == color:
            total += material_value(
                piece.piece_type
            )

    return total



def classify_move_quality(
    before_board,
    after_board,
    move,
    mover_color,
    best_move,
    best_eval_cp,
    after_eval_cp
):
    if move == best_move:
        if (
            before_board.is_castling(move)
            or move.promotion is not None
            or before_board.gives_check(move)
        ):
            return "BEST"

        return "EXCELLENT"

    if best_eval_cp >= 100000:
        if after_eval_cp >= 100000:
            return "BRILLIANT*"

        return "BLUNDER"

    loss = max(
        0,
        best_eval_cp - after_eval_cp
    )

    material_before = side_material(
        before_board,
        mover_color
    )

    material_after = side_material(
        after_board,
        mover_color
    )

    sacrifice = (
        material_after
        < material_before
    )

    if loss <= 10 and sacrifice:
        return "BRILLIANT*"

    if loss <= 10:
        return "EXCELLENT"

    if loss <= 25:
        return "GREAT"

    if loss <= 70:
        return "GOOD"

    if loss <= 150:
        return "INACCURACY"

    if loss <= 300:
        return "MISTAKE"

    return "BLUNDER"


def build_analysis(
    engine,
    before_board,
    after_board,
    move,
    best_info=None
):
    mover_color = before_board.turn

    try:
        if best_info is None:
            best_info = engine.analyse(
                before_board,
                chess.engine.Limit(
                    depth=ANALYSIS_DEPTH,
                    time=ANALYSIS_TIME
                )
            )

        best_score_obj = best_info.get(
            "score"
        )

        if best_score_obj is None:
            return None

        best_score_white = (
            best_score_obj.pov(
                chess.WHITE
            )
        )

        best_eval_cp = score_to_cp(
            best_score_white
        )

        best_move = best_info.get(
            "pv",
            [None]
        )[0]

        after_info = engine.analyse(
            after_board,
            chess.engine.Limit(
                depth=ANALYSIS_DEPTH,
                time=ANALYSIS_TIME
            )
        )

        after_score_obj = after_info.get(
            "score"
        )

        if after_score_obj is None:
            return None

        after_score_white = (
            after_score_obj.pov(
                chess.WHITE
            )
        )

        after_eval_cp = score_to_cp(
            after_score_white
        )

        quality = classify_move_quality(
            before_board,
            after_board,
            move,
            mover_color,
            best_move,
            score_to_cp(
                best_score_obj.pov(
                    mover_color
                )
            ),
            score_to_cp(
                after_score_obj.pov(
                    mover_color
                )
            )
        )

        pv = []
        temp = after_board.copy()

        for pv_move in after_info.get(
            "pv",
            []
        )[:6]:
            if pv_move not in temp.legal_moves:
                break

            pv.append(
                temp.san(
                    pv_move
                )
            )

            temp.push(
                pv_move
            )

        return {
            "eval_cp": after_eval_cp,
            "eval_text": format_eval(
                after_eval_cp
            ),
            "favor": favor_text(
                after_eval_cp
            ),
            "quality": quality,
            "last_move": (
                after_board.peek().uci()
                if after_board.move_stack
                else move.uci()
            ),
            "best_move": (
                best_move.uci()
                if best_move is not None
                else "-"
            ),
            "depth": after_info.get(
                "depth",
                ANALYSIS_DEPTH
            ),
            "pv": (
                " ".join(pv)
                if pv
                else "-"
            )
        }

    except Exception as exc:
        print(
            f"[ANALYSIS ERROR] {exc}"
        )

        return None


def adaptive_accuracy_profile(
    opponent_accuracy,
    sample_count
):
    if (
        opponent_accuracy is None
        or sample_count < OPPONENT_MIN_SAMPLES
    ):
        return {
            "opponent_accuracy": opponent_accuracy,
            "target_accuracy": 88.0,
            "max_rank": 3,
            "max_eval_drop": 0.12,
            "state": (
                f"WARMUP "
                f"{sample_count}/"
                f"{OPPONENT_MIN_SAMPLES}"
            ),
        }

    score = float(
        opponent_accuracy
    )

    target = min(
        ADAPTIVE_MAX_TARGET,
        max(
            ADAPTIVE_MIN_TARGET,
            score + ADAPTIVE_SAFETY_MARGIN
        )
    )

    if score < 70.0:
        max_rank = 4
        max_eval_drop = 0.18
        state = "OPPONENT LIGHT"

    elif score < 80.0:
        max_rank = 3
        max_eval_drop = 0.14
        state = "OPPONENT MEDIUM"

    elif score < 88.0:
        max_rank = 2
        max_eval_drop = 0.10
        state = "OPPONENT STRONG"

    elif score < ADAPTIVE_STRONG_THRESHOLD:
        max_rank = 2
        max_eval_drop = 0.075
        state = "OPPONENT VERY STRONG"

    elif score < ADAPTIVE_VERY_STRONG_THRESHOLD:
        max_rank = 1
        max_eval_drop = 0.050
        state = "OPPONENT ELITE"

    else:
        max_rank = 1
        max_eval_drop = 0.035
        state = "OPPONENT EXTREME"

    return {
        "opponent_accuracy": score,
        "target_accuracy": target,
        "max_rank": max_rank,
        "max_eval_drop": max_eval_drop,
        "state": state,
    }


def choose_stockfish_move(
    board,
    multipv_infos,
    previous_eval_white_cp=None,
    opponent_accuracy=None,
    opponent_sample_count=0,
    opponent_pressure=False,
    engine=None
):
    def choose_human_candidate(
        board,
        candidate_list
    ):
        """Choose a human-like candidate after safety filtering.

        MultiPV rank is deliberately weak. Captures, checks, castling and
        promotion receive small human-behavior preferences, while the caller
        ensures that every candidate is position-safe.
        """
        if not candidate_list:
            return None

        # Keep the human-like randomness, but do not let the selector
        # collapse into repeated #1/#2 choices when lower safe choices exist.
        # After a top-two move, prefer a genuinely lower MultiPV choice.
        selection_pool = list(candidate_list)
        recent_ranks = list(
            getattr(
                choose_stockfish_move,
                "_recent_human_ranks",
                []
            )
        )

        if recent_ranks:
            previous_rank = int(
                recent_ranks[-1]
            )
        else:
            previous_rank = getattr(
                choose_stockfish_move,
                "_last_human_rank",
                None
            )

        lower_candidates = [
            candidate
            for candidate in candidate_list
            if int(
                candidate.get(
                    "rank",
                    0
                )
            ) >= 2
        ]

        # When the current safety branch contains only #1/#2, do not fall
        # back to another top-two move merely because that branch is narrow.
        # Pull a lower MultiPV choice from the full position when it remains
        # within a controlled evaluation band.
        broad_lower_candidates = [
            candidate
            for candidate in candidates
            if (
                int(
                    candidate.get(
                        "rank",
                        0
                    )
                ) >= 2
                and int(
                    candidate.get(
                        "rank",
                        0
                    )
                ) <= 7
                and int(
                    candidate.get(
                        "cp",
                        0
                    )
                )
                >= max(
                    50,
                    int(
                        current_advantage
                        - 300
                    )
                )
            )
        ]

        if (
            previous_rank in (0, 1)
            and lower_candidates
        ):
            selection_pool = lower_candidates

        elif (
            previous_rank in (0, 1)
            and broad_lower_candidates
        ):
            selection_pool = broad_lower_candidates

        elif (
            len(recent_ranks) >= 2
            and recent_ranks[-1] in (0, 1)
            and recent_ranks[-2] in (0, 1)
            and lower_candidates
        ):
            selection_pool = lower_candidates

        elif (
            len(recent_ranks) >= 2
            and recent_ranks[-1] in (0, 1)
            and recent_ranks[-2] in (0, 1)
            and broad_lower_candidates
        ):
            selection_pool = broad_lower_candidates

        if len(selection_pool) == 1:
            selected_candidate = selection_pool[0]
            selected_rank = int(
                selected_candidate.get(
                    "rank",
                    0
                )
            )

            choose_stockfish_move._last_human_rank = selected_rank
            choose_stockfish_move._recent_human_ranks = (
                recent_ranks + [selected_rank]
            )[-3:]

            if current_advantage >= 300:
                choose_stockfish_move._winning_conversion_cycle = (
                    getattr(
                        choose_stockfish_move,
                        "_winning_conversion_cycle",
                        0
                    )
                    + 1
                )
            else:
                choose_stockfish_move._winning_conversion_cycle = 0

            selected_move = selected_candidate["move"]

            choose_stockfish_move._last_winning_move_uci = (
                selected_move.uci()
            )

            if current_advantage >= HUMAN_ADVANTAGE_START_CP:
                is_progress_move = (
                    board.is_capture(selected_move)
                    or board.gives_check(selected_move)
                    or selected_move.promotion is not None
                    or selected_candidate["cp"]
                    >= (
                        current_advantage
                        + HUMAN_ADVANTAGE_GROWTH_TRIGGER_CP
                    )
                )

                if is_progress_move:
                    choose_stockfish_move._winning_quiet_streak = 0
                else:
                    choose_stockfish_move._winning_quiet_streak = (
                        getattr(
                            choose_stockfish_move,
                            "_winning_quiet_streak",
                            0
                        )
                        + 1
                    )
            else:
                choose_stockfish_move._winning_quiet_streak = 0

            selected_move = selected_candidate["move"]

        choose_stockfish_move._last_winning_move_uci = (
            selected_move.uci()
        )

        if current_advantage >= HUMAN_ADVANTAGE_START_CP:
            is_progress_move = (
                board.is_capture(selected_move)
                or board.gives_check(selected_move)
                or selected_move.promotion is not None
                or selected_candidate["cp"]
                >= (
                    current_advantage
                    + HUMAN_ADVANTAGE_GROWTH_TRIGGER_CP
                )
            )

            if is_progress_move:
                choose_stockfish_move._winning_quiet_streak = 0
            else:
                choose_stockfish_move._winning_quiet_streak = (
                    getattr(
                        choose_stockfish_move,
                        "_winning_quiet_streak",
                        0
                    )
                    + 1
                )
        else:
            choose_stockfish_move._winning_quiet_streak = 0

        return selected_candidate

        weighted = []

        for candidate in selection_pool:
            rank = int(
                candidate.get(
                    "rank",
                    0
                )
            )

            # MultiPV rank is deliberately almost neutral. The point is
            # not to imitate Stockfish's ordering; it is to let a safe human
            # choice emerge from several reasonable moves.
            rank_weight = max(
                0.94,
                1.0 / (
                    1.0
                    + (0.015 * rank)
                )
            )

            # Keep engine quality relevant, but make it much weaker than
            # human-behavior features. A move that is 0.5-1.0 pawns below
            # the best safe line can still be chosen when the position allows
            # it.
            pool_best_cp = max(
                item.get("cp", 0)
                for item in selection_pool
            )
            quality_gap = abs(
                pool_best_cp
                - int(
                    candidate.get("cp", 0)
                )
            )
            quality_weight = (
                0.93
                + (
                    0.12
                    / (
                        1.0
                        + quality_gap / 150.0
                    )
                )
            )

            weight = (
                rank_weight
                * quality_weight
            )
            move = candidate["move"]

            # Humans tend to notice an available capture, especially when
            # the captured piece is valuable. The safety floor is applied
            # before this helper is called.
            if board.is_capture(move):
                captured_piece = board.piece_at(
                    move.to_square
                )

                if (
                    captured_piece is None
                    and board.is_en_passant(move)
                ):
                    captured_value = material_value(
                        chess.PAWN
                    )
                elif captured_piece is not None:
                    captured_value = material_value(
                        captured_piece.piece_type
                    )
                else:
                    captured_value = 0

                weight *= (
                    3.5
                    + min(
                        captured_value,
                        900
                    ) / 900.0 * 2.5
                )

            if board.gives_check(move):
                weight *= 1.22

            if board.is_castling(move):
                weight *= 1.18

            if move.promotion is not None:
                weight *= 1.28

            # Natural human development gets a small preference. These are
            # deliberately modest so tactical/evaluative safety still wins.
            moving_piece = board.piece_at(
                move.from_square
            )

            if moving_piece is not None:
                if moving_piece.piece_type in (
                    chess.KNIGHT,
                    chess.BISHOP
                ):
                    home_rank = (
                        0
                        if moving_piece.color == chess.WHITE
                        else 7
                    )

                    if chess.square_rank(
                        move.from_square
                    ) == home_rank:
                        weight *= 1.10

                if (
                    moving_piece.piece_type
                    == chess.PAWN
                    and move.from_square // 8 in (1, 6)
                    and chess.square_file(
                        move.from_square
                    ) in (
                        2,
                        3,
                        4,
                        5
                    )
                ):
                    weight *= 1.06

                if moving_piece.piece_type == chess.KING:
                    weight *= 0.92

            weighted.append(
                (
                    candidate,
                    weight
                )
            )

        selected_candidate = random.choices(
            [item[0] for item in weighted],
            weights=[item[1] for item in weighted],
            k=1
        )[0]

        selected_rank = int(
            selected_candidate.get(
                "rank",
                0
            )
        )

        choose_stockfish_move._last_human_rank = selected_rank
        choose_stockfish_move._recent_human_ranks = (
            recent_ranks + [selected_rank]
        )[-3:]

        if current_advantage >= 300:
            choose_stockfish_move._winning_conversion_cycle = (
                getattr(
                    choose_stockfish_move,
                    "_winning_conversion_cycle",
                    0
                )
                + 1
            )
        else:
            choose_stockfish_move._winning_conversion_cycle = 0

        return selected_candidate


    def human_safety_floor_cp(
        best_cp
    ):
        """Keep human variation close to the best line on either side."""
        best_cp = int(
            best_cp
        )

        # Positive positions keep the original conservative floor so a
        # small winning/equal position cannot cross below zero just for
        # randomness. Negative positions use a symmetric relative floor so
        # reasonable negative alternatives remain available.
        if best_cp >= 0:
            if best_cp <= 5:
                return 5

            if best_cp < 250:
                allowed_drop = 50
            elif best_cp < 500:
                allowed_drop = 80
            elif best_cp < 800:
                allowed_drop = 120
            elif best_cp < 1000:
                allowed_drop = 150
            else:
                allowed_drop = min(
                    250,
                    max(
                        120,
                        int(
                            best_cp
                            * 0.05
                        )
                    )
                )

            return max(
                5,
                best_cp - allowed_drop
            )

        magnitude = abs(
            best_cp
        )

        if magnitude < 250:
            allowed_drop = 50
        elif magnitude < 500:
            allowed_drop = 80
        elif magnitude < 800:
            allowed_drop = 120
        elif magnitude < 1000:
            allowed_drop = 150
        else:
            allowed_drop = min(
                250,
                max(
                    120,
                    int(
                        magnitude
                        * 0.05
                    )
                )
            )

        return best_cp - allowed_drop



    if not multipv_infos:
        return (
            None,
            None,
            {
                "rank": 0,
                "current_cp": 0,
                "selected_cp": 0,
                "reason": "no MultiPV candidates"
            }
        )

    # Reset the human-like rank history only at the start of a new game
    # (or at the first already-played position). Repeated calls on the same
    # first position keep the same history instead of resetting randomly.
    if len(board.move_stack) <= 1:
        first_position_marker = board.fen()

        if (
            getattr(
                choose_stockfish_move,
                "_first_position_marker",
                None
            )
            != first_position_marker
        ):
            choose_stockfish_move._last_human_rank = None
            choose_stockfish_move._recent_human_ranks = []
            choose_stockfish_move._winning_conversion_cycle = 0
            choose_stockfish_move._winning_quiet_streak = 0
            choose_stockfish_move._last_winning_move_uci = None
            choose_stockfish_move._first_position_marker = first_position_marker

    mover = board.turn
    candidates = []

    for rank, info in enumerate(
        multipv_infos[
            :TRAINING_MULTI_PV
        ]
    ):
        pv = info.get(
            "pv",
            []
        )

        if not pv:
            continue

        move = pv[0]

        if move not in board.legal_moves:
            continue

        score_obj = info.get(
            "score"
        )

        if score_obj is None:
            continue

        pov_score = score_obj.pov(
            mover
        )

        cp = pov_score.score(
            mate_score=100000
        )

        if cp is None:
            cp = 0

        candidates.append({
            "rank": rank,
            "move": move,
            "info": info,
            "cp": int(cp),
            "mate": pov_score.mate(),
        })

    if not candidates:
        return (
            None,
            None,
            {
                "rank": 0,
                "current_cp": 0,
                "selected_cp": 0,
                "reason": "no legal MultiPV candidates"
            }
        )

    best = candidates[0]
    best_cp = best["cp"]

    profile = adaptive_accuracy_profile(
        opponent_accuracy,
        opponent_sample_count
    )

    adaptive_max_rank = int(
        profile["max_rank"]
    )

    adaptive_max_drop = float(
        profile["max_eval_drop"]
    )

    # The Colab selector does not force #1 from the previous evaluation.
    # Human-like selection below is driven by the current MultiPV scores.
    if (
        best["mate"] is not None
        and best["mate"] > 0
    ):
        global _mate_progress_target_mate, _mate_progress_hold_moves, _mate_progress_hold_limit

        # M4 or closer: stop humanizing and take the fastest mate immediately.
        if best["mate"] <= MATE_FORCE_FAST_MAX:
            _mate_progress_target_mate = None
            _mate_progress_hold_moves = 0
            _mate_progress_hold_limit = MATE_SUSTAIN_MIN_MOVES
            choose_stockfish_move._winning_conversion_cycle = 0

            selected = best

            return (
                selected["move"],
                selected["info"],
                {
                    "rank": selected["rank"],
                    "current_cp": best_cp,
                    "selected_cp": selected["cp"],
                    "reason": (
                        f"MATE FORCE | "
                        f"M{selected['mate']} "
                        f"RANK=#"
                        f"{selected['rank'] + 1}"
                    )
                }
            )

        # The human-like mate window remains M5-M15. Outside that window,
        # keep the existing direct #1 behavior.
        if not (
            MATE_GRACE_MIN
            <= best["mate"]
            <= MATE_GRACE_MAX
        ):
            _mate_progress_target_mate = None
            _mate_progress_hold_moves = 0
            _mate_progress_hold_limit = MATE_SUSTAIN_MIN_MOVES

            selected = best

            return (
                selected["move"],
                selected["info"],
                {
                    "rank": selected["rank"],
                    "current_cp": best_cp,
                    "selected_cp": selected["cp"],
                    "reason": (
                        f"MATE #1 | "
                        f"M{selected['mate']} "
                        f"RANK=#"
                        f"{selected['rank'] + 1}"
                    )
                }
            )

        # Start/recover the sustained mate target. The target represents the
        # mate level the bot is currently willing to play around. It can move
        # faster only one step at a time; it may move slower when the actual
        # engine mate itself has become slower because the opponent defended.
        if _mate_progress_target_mate is None:
            _mate_progress_target_mate = best["mate"]
            _mate_progress_hold_moves = 0
            _mate_progress_hold_limit = random.randint(
                MATE_SUSTAIN_MIN_MOVES,
                MATE_SUSTAIN_MAX_MOVES
            )
        elif best["mate"] > _mate_progress_target_mate:
            _mate_progress_target_mate = best["mate"]
            _mate_progress_hold_moves = 0
            _mate_progress_hold_limit = random.randint(
                MATE_SUSTAIN_MIN_MOVES,
                MATE_SUSTAIN_MAX_MOVES
            )
        elif best["mate"] < _mate_progress_target_mate:
            # Do not follow M10 -> M9 -> M8 immediately. Hold the current
            # target for a few moves first, then improve it by exactly one.
            _mate_progress_hold_moves += 1

            if (
                _mate_progress_hold_moves
                >= _mate_progress_hold_limit
            ):
                _mate_progress_target_mate = max(
                    MATE_GRACE_MIN,
                    _mate_progress_target_mate - 1
                )
                _mate_progress_hold_moves = 0
                _mate_progress_hold_limit = random.randint(
                    MATE_SUSTAIN_MIN_MOVES,
                    MATE_SUSTAIN_MAX_MOVES
                )

        target_mate = int(
            _mate_progress_target_mate
        )

        # Never jump multiple mate steps in a single decision. The active
        # target is the anchor; one slower line is allowed to preserve a
        # natural sustain feel, but it cannot become an accumulating +5 cap.
        allowed_mate_max = target_mate + 1

        mate_candidates = [
            c
            for c in candidates
            if (
                c["mate"] is not None
                and c["mate"] > 0
                and target_mate
                <= c["mate"]
                <= allowed_mate_max
            )
        ]

        # If the engine's current best mate is already faster than the target
        # but no exact target line exists, allow the current best only when
        # the target has caught up to that one-step improvement. Otherwise
        # keep the slower candidate to sustain the plan.
        if not mate_candidates:
            exact_best = [
                c
                for c in candidates
                if (
                    c["mate"] is not None
                    and c["mate"] == best["mate"]
                )
            ]

            if exact_best:
                selected = max(
                    exact_best,
                    key=lambda c: c["rank"]
                )

                return (
                    selected["move"],
                    selected["info"],
                    {
                        "rank": selected["rank"],
                        "current_cp": best_cp,
                        "selected_cp": selected["cp"],
                        "reason": (
                            f"MATE ADAPT | "
                            f"TARGET=M{target_mate} "
                            f"BEST=M{best['mate']} "
                            f"SELECTED=M{selected['mate']} "
                            f"RANK=#"
                            f"{selected['rank'] + 1}"
                        )
                    }
                )

            selected = best

            return (
                selected["move"],
                selected["info"],
                {
                    "rank": selected["rank"],
                    "current_cp": best_cp,
                    "selected_cp": selected["cp"],
                    "reason": (
                        f"MATE BEST | "
                        f"TARGET=M{target_mate} "
                        f"BEST=M{best['mate']} "
                        f"RANK=#"
                        f"{selected['rank'] + 1}"
                    )
                }
            )

        exact_target = [
            c
            for c in mate_candidates
            if c["mate"] == target_mate
        ]

        slower_target = [
            c
            for c in mate_candidates
            if c["mate"] == allowed_mate_max
        ]

        if exact_target:
            # Same mate distance: keep the earlier rule—take the lowest
            # MultiPV line, e.g. #1 M6/#2 M6/#3 M6 -> #3.
            selected = max(
                exact_target,
                key=lambda c: c["rank"]
            )

            # Occasionally sustain with the one-step slower mate when it is
            # available, but never jump several mate moves at once.
            if (
                slower_target
                and random.random() < MATE_SLOWER_LINE_CHANCE
            ):
                selected = max(
                    slower_target,
                    key=lambda c: c["rank"]
                )
        else:
            selected = max(
                slower_target,
                key=lambda c: c["rank"]
            )

        return (
            selected["move"],
            selected["info"],
            {
                "rank": selected["rank"],
                "current_cp": best_cp,
                "selected_cp": selected["cp"],
                "reason": (
                    f"MATE SUSTAIN | "
                    f"TARGET=M{target_mate} "
                    f"BEST=M{best['mate']} "
                    f"SELECTED=M{selected['mate']} "
                    f"HOLD={_mate_progress_hold_moves}/"
                    f"{_mate_progress_hold_limit} "
                    f"RANK=#"
                    f"{selected['rank'] + 1}"
                )
            }
        )

    # ================================================================
    # EXACT HUMAN-LIKE PLAYING LOGIC
    # Based directly on the supplied Colab get_dynamic_human_move().
    #
    # In the Colab code, current_advantage comes from a separate 0.1s
    # evaluation, while top_score comes from the MultiPV list. Preserve
    # that distinction here as well.
    # ================================================================
    current_advantage = best_cp

    if engine is not None:
        # Keep the extra human-like position check, but use the same
        # fast analysis budget as the normal evaluator so move latency does
        # not grow just because human-like selection is enabled.
        current_eval_info = engine.analyse(
            board,
            chess.engine.Limit(
                time=min(
                    HUMAN_LIKE_EVAL_TIME,
                    ANALYSIS_TIME
                )
            )
        )
        current_eval_score = current_eval_info.get(
            "score"
        )

        if current_eval_score is not None:
            current_eval = current_eval_score.pov(
                mover
            ).score(
                mate_score=100000
            )

            if current_eval is not None:
                current_advantage = int(
                    current_eval
                )

    # 1. GM ACTIVE WINNING PLAY.
    # A clear advantage should create forward progress, not endless holding.
    # Captures/checks/promotions and useful pawn/king progress receive
    # stronger weight, while safe human variation remains available.
    if current_advantage >= HUMAN_ADVANTAGE_START_CP:
        quiet_streak = int(
            getattr(
                choose_stockfish_move,
                "_winning_quiet_streak",
                0
            )
        )

        # Rare deep calculation = occasional "great move" moment even in a
        # winning position. Keep the existing 1/15 frequency.
        if (
            engine is not None
            and random.randint(
                1,
                HUMAN_LIKE_DEEP_CHANCE_DENOM
            ) == 1
        ):
            deep_result = engine.analyse(
                board,
                chess.engine.Limit(
                    depth=HUMAN_LIKE_DEEP_DEPTH
                )
            )

            deep_move = deep_result.get(
                "pv",
                [None]
            )[0]

            deep_score = deep_result.get(
                "score"
            )

            deep_cp = (
                deep_score.pov(
                    board.turn
                ).score(
                    mate_score=100000
                )
                if deep_score is not None
                else None
            )

            deep_floor_cp = max(
                200,
                current_advantage - 80
            )

            if (
                deep_move is not None
                and deep_move in board.legal_moves
                and deep_cp is not None
                and deep_cp >= deep_floor_cp
            ):
                choose_stockfish_move._last_winning_move_uci = (
                    deep_move.uci()
                )
                choose_stockfish_move._winning_quiet_streak = 0
                choose_stockfish_move._winning_conversion_cycle = 0

                capture_note = (
                    " | HUMAN CAPTURE"
                    if board.is_capture(deep_move)
                    else ""
                )

                return (
                    deep_move,
                    deep_result,
                    {
                        "rank": 0,
                        "current_cp": current_advantage,
                        "selected_cp": int(deep_cp),
                        "reason": (
                            "GREAT MOVE (Deep Calc) | "
                            f"BEST={current_advantage / 100:+.2f} "
                            f"DEEP={deep_cp / 100:+.2f}"
                            f"{capture_note}"
                        )
                    }
                )

        # Controlled mistake: still human-like, but never allowed to destroy
        # the winning cushion.
        if random.randint(
            1,
            12
        ) == 1:
            mistake_candidates = [
                candidate
                for candidate in candidates[
                    2:10
                ]
                if (
                    candidate["cp"]
                    <= best_cp - 60
                    and candidate["cp"]
                    >= max(
                        200,
                        current_advantage - 180
                    )
                )
            ]

            if mistake_candidates:
                chosen = choose_human_candidate(
                    board,
                    mistake_candidates
                )

                return (
                    chosen["move"],
                    chosen["info"],
                    {
                        "rank": chosen["rank"],
                        "current_cp": current_advantage,
                        "selected_cp": chosen["cp"],
                        "reason": (
                            f"HUMAN MISTAKE "
                            f"(Engine #{chosen['rank'] + 1}) | "
                            f"BEST={best_cp / 100:+.2f} "
                            f"SELECTED={chosen['cp'] / 100:+.2f}"
                        )
                    }
                )

        # Rare controlled blunder at a very large advantage.
        if (
            current_advantage >= 700
            and random.randint(
                1,
                30
            ) == 1
        ):
            blunder_candidates = [
                candidate
                for candidate in candidates[
                    4:15
                ]
                if (
                    candidate["cp"]
                    <= best_cp - 120
                    and candidate["cp"]
                    >= max(
                        300,
                        current_advantage - 280
                    )
                )
            ]

            if blunder_candidates:
                chosen = choose_human_candidate(
                    board,
                    blunder_candidates
                )

                return (
                    chosen["move"],
                    chosen["info"],
                    {
                        "rank": chosen["rank"],
                        "current_cp": current_advantage,
                        "selected_cp": chosen["cp"],
                        "reason": (
                            f"HUMAN BLUNDER "
                            f"(Engine #{chosen['rank'] + 1}) | "
                            f"BEST={best_cp / 100:+.2f} "
                            f"SELECTED={chosen['cp'] / 100:+.2f}"
                        )
                    }
                )

        # Inaccuracy remains possible while winning, but with a much smaller
        # evaluation loss than the old +6 -> +3 style BAKWAS choices.
        if random.randint(
            1,
            7
        ) == 1:
            inaccuracy_candidates = [
                candidate
                for candidate in candidates[
                    3:8
                ]
                if (
                    candidate["cp"]
                    <= best_cp - 20
                    and candidate["cp"]
                    >= max(
                        250,
                        current_advantage - 120
                    )
                )
            ]

            if inaccuracy_candidates:
                chosen = choose_human_candidate(
                    board,
                    inaccuracy_candidates
                )

                return (
                    chosen["move"],
                    chosen["info"],
                    {
                        "rank": chosen["rank"],
                        "current_cp": current_advantage,
                        "selected_cp": chosen["cp"],
                        "reason": (
                            f"INACCURACY "
                            f"(Engine #{chosen['rank'] + 1}) | "
                            f"BEST={best_cp / 100:+.2f} "
                            f"SELECTED={chosen['cp'] / 100:+.2f}"
                        )
                    }
                )

        # Two quiet winning moves are enough to trigger active conversion.
        # At +8 or more, always use the active winning pool.
        active_conversion = (
            current_advantage >= HUMAN_LIKE_LAZY_MIN_ADVANTAGE_CP
            or quiet_streak >= 2
            or random.random() < 0.60
            or opponent_pressure
        )

        if active_conversion:
            progress_floor_cp = max(
                200,
                current_advantage - 160
            )

            previous_winning_move_uci = getattr(
                choose_stockfish_move,
                "_last_winning_move_uci",
                None
            )

            progress_candidates = [
                candidate
                for candidate in candidates
                if (
                    candidate["rank"] <= min(
                        7,
                        len(candidates) - 1
                    )
                    and candidate["cp"] >= progress_floor_cp
                    and (
                        previous_winning_move_uci is None
                        or candidate["move"].uci()
                        != previous_winning_move_uci
                    )
                )
            ]

            if progress_candidates:
                weighted = []

                for candidate in progress_candidates:
                    move = candidate["move"]
                    weight = 1.0

                    if (
                        candidate["cp"]
                        >= current_advantage
                        + HUMAN_ADVANTAGE_GROWTH_TRIGGER_CP
                    ):
                        weight *= 3.0

                    rank = int(
                        candidate.get(
                            "rank",
                            0
                        )
                    )

                    if 1 <= rank <= 4:
                        weight *= 1.10

                    if board.is_capture(move):
                        captured_piece = board.piece_at(
                            move.to_square
                        )

                        if (
                            captured_piece is None
                            and board.is_en_passant(move)
                        ):
                            captured_value = material_value(
                                chess.PAWN
                            )
                        elif captured_piece is not None:
                            captured_value = material_value(
                                captured_piece.piece_type
                            )
                        else:
                            captured_value = 0

                        weight *= (
                            4.0
                            + min(
                                captured_value,
                                900
                            ) / 180.0
                        )

                    if board.gives_check(move):
                        weight *= 3.0

                    if move.promotion is not None:
                        weight *= 6.0

                    moving_piece = board.piece_at(
                        move.from_square
                    )

                    if moving_piece is not None:
                        if (
                            moving_piece.piece_type
                            == chess.PAWN
                        ):
                            weight *= 1.40

                        if (
                            moving_piece.piece_type
                            == chess.KING
                            and len(board.piece_map()) <= 12
                        ):
                            weight *= 1.30

                    weighted.append(
                        (
                            candidate,
                            max(
                                0.05,
                                weight
                            )
                        )
                    )

                chosen = random.choices(
                    [item[0] for item in weighted],
                    weights=[item[1] for item in weighted],
                    k=1
                )[0]

                chosen = choose_human_candidate(
                    board,
                    [chosen]
                )

                capture_note = (
                    " | HUMAN CAPTURE"
                    if board.is_capture(chosen["move"])
                    else ""
                )

                return (
                    chosen["move"],
                    chosen["info"],
                    {
                        "rank": chosen["rank"],
                        "current_cp": current_advantage,
                        "selected_cp": chosen["cp"],
                        "reason": (
                            f"GM ACTIVE CONVERSION "
                            f"(#{chosen['rank'] + 1}) | "
                            f"STREAK={quiet_streak} "
                            f"FLOOR={progress_floor_cp / 100:+.2f} "
                            f"BEST={best_cp / 100:+.2f} "
                            f"SELECTED={chosen['cp'] / 100:+.2f}"
                            f"{capture_note}"
                        )
                    }
                )

    # 2. LOW-ADVANTAGE HUMAN PLAY.
    # Replace the old top-3 Pull-Up cage with a safe human pool. The pool
    # expands when the opponent is weak/unknown and contracts against a
    # genuinely strong opponent. Negative candidates are never invited while
    # a safe positive continuation exists.
    if current_advantage < HUMAN_LIKE_PULLUP_MAX_ADVANTAGE_CP:
        low_floor_cp = human_safety_floor_cp(
            best_cp
        )

        if (
            opponent_sample_count
            < OPPONENT_MIN_SAMPLES
        ):
            low_rank_cap = 5
        elif opponent_accuracy is None or opponent_accuracy < 70.0:
            low_rank_cap = 5
        elif opponent_accuracy < 80.0:
            low_rank_cap = 4
        elif opponent_accuracy < 88.0:
            low_rank_cap = 3
        else:
            low_rank_cap = 2

        # At low advantage, keep the position safe but do not require
        # every move to improve the current evaluation. Human players often
        # choose a reasonable move that maintains the position.
        low_variation_drop_cp = min(
            120,
            max(
                25,
                int(
                    max(
                        50,
                        abs(best_cp)
                    ) * 0.30
                )
            )
        )

        low_variation_floor_cp = (
            best_cp
            - low_variation_drop_cp
        )

        if best_cp >= 0:
            low_variation_floor_cp = max(
                5,
                low_variation_floor_cp
            )

        low_safe_candidates = [
            candidate
            for candidate in candidates
            if (
                candidate["rank"] <= low_rank_cap
                and candidate["cp"] >= low_variation_floor_cp
            )
        ]

        if not low_safe_candidates:
            low_safe_candidates = [
                best
            ]

        chosen = choose_human_candidate(
            board,
            low_safe_candidates
        )

        capture_note = (
            " | HUMAN CAPTURE"
            if board.is_capture(chosen["move"])
            else ""
        )

        return (
            chosen["move"],
            chosen["info"],
            {
                "rank": chosen["rank"],
                "current_cp": current_advantage,
                "selected_cp": chosen["cp"],
                "reason": (
                    f"Human Safe Play "
                    f"(#{chosen['rank'] + 1}) | "
                    f"SAFE_POOL={len(low_safe_candidates)} "
                    f"FLOOR={low_floor_cp / 100:+.2f} "
                    f"BEST={best_cp / 100:+.2f} "
                    f"SELECTED={chosen['cp'] / 100:+.2f}"
                    f"{capture_note}"
                )
            }
        )

    # 3. WINNING CONVERSION.
    # A human player with a clear advantage does not endlessly shuffle the
    # position. After several human-like choices, force a near-best conversion
    # move while still avoiding a permanent #1 habit. This is what turns a
    # growing advantage into an actual win.
    if (
        current_advantage >= 300
        and getattr(
            choose_stockfish_move,
            "_winning_conversion_cycle",
            0
        ) >= 3
    ):
        conversion_candidates = [
            candidate
            for candidate in candidates
            if (
                candidate["rank"] <= 5
                and candidate["cp"]
                >= max(
                    150,
                    best_cp - 100
                )
                and candidate["cp"]
                >= max(
                    200,
                    current_advantage - 120
                )
            )
        ]

        if conversion_candidates:
            chosen = choose_human_candidate(
                board,
                conversion_candidates
            )

            choose_stockfish_move._winning_conversion_cycle = 0

            return (
                chosen["move"],
                chosen["info"],
                {
                    "rank": chosen["rank"],
                    "current_cp": current_advantage,
                    "selected_cp": chosen["cp"],
                    "reason": (
                        f"WINNING CONVERSION "
                        f"(Engine #{chosen['rank'] + 1}) | "
                        f"BEST={best_cp / 100:+.2f} "
                        f"SELECTED={chosen['cp'] / 100:+.2f}"
                    )
                }
            )

    # 3. KILLER INSTINCT: exact 1/15 chance.
    if (
        engine is not None
        and random.randint(
            1,
            HUMAN_LIKE_DEEP_CHANCE_DENOM
        ) == 1
    ):
        deep_result = engine.analyse(
            board,
            chess.engine.Limit(
                depth=HUMAN_LIKE_DEEP_DEPTH
            )
        )

        deep_move = deep_result.get(
            "pv",
            [None]
        )[0]

        if (
            deep_move is not None
            and deep_move in board.legal_moves
        ):
            deep_score = deep_result.get(
                "score"
            )

            deep_cp = (
                deep_score.pov(
                    board.turn
                ).score(
                    mate_score=100000
                )
                if deep_score is not None
                else best_cp
            )

            if deep_cp is None:
                deep_cp = best_cp

            if deep_cp <= 0:
                deep_move = None

            deep_floor_cp = human_safety_floor_cp(
                best_cp
            )

            if (
                current_advantage > 0
                and deep_move is not None
                and deep_cp < deep_floor_cp
            ):
                deep_move = None

            if deep_move is not None:
                # Record Deep Calc as a top-rank decision for the
                # anti-repeat history, so the next human-like choice does
                # not immediately return to #1/#2 again.
                choose_stockfish_move._last_human_rank = 0
                recent_ranks = list(
                    getattr(
                        choose_stockfish_move,
                        "_recent_human_ranks",
                        []
                    )
                )
                choose_stockfish_move._recent_human_ranks = (
                    recent_ranks + [0]
                )[-3:]
                choose_stockfish_move._last_winning_move_uci = (
                    deep_move.uci()
                )
                choose_stockfish_move._winning_quiet_streak = 0
                choose_stockfish_move._winning_conversion_cycle = 0

                return (
                    deep_move,
                    deep_result,
                    {
                        "rank": 0,
                        "current_cp": current_advantage,
                        "selected_cp": int(deep_cp),
                        "reason": (
                            "GREAT MOVE (Deep Calc) | "
                            f"BEST={current_advantage / 100:+.2f} "
                            f"DEEP={deep_cp / 100:+.2f}"
                        )
                    }
                )

    # 4. CONTROLLED HUMAN MISTAKE / BLUNDER.
    # These choices deliberately use lower MultiPV lines only when the bot
    # already has a meaningful cushion. The move stays legal and the remaining
    # evaluation is kept positive so the bot can still play to a win.
    if (
        current_advantage >= 400
        and random.randint(
            1,
            12
        ) == 1
    ):
        mistake_candidates = [
            candidate
            for candidate in candidates[
                2:10
            ]
            if (
                candidate["cp"]
                <= best_cp - 60
                and candidate["cp"]
                >= max(
                    150,
                    current_advantage - 220
                )
            )
        ]

        if mistake_candidates:
            chosen = choose_human_candidate(
                board,
                mistake_candidates
            )

            return (
                chosen["move"],
                chosen["info"],
                {
                    "rank": chosen["rank"],
                    "current_cp": current_advantage,
                    "selected_cp": chosen["cp"],
                    "reason": (
                        f"HUMAN MISTAKE "
                        f"(Engine #{chosen['rank'] + 1}) | "
                        f"BEST={best_cp / 100:+.2f} "
                        f"SELECTED={chosen['cp'] / 100:+.2f}"
                    )
                }
            )

    if (
        current_advantage >= 700
        and random.randint(
            1,
            30
        ) == 1
    ):
        blunder_candidates = [
            candidate
            for candidate in candidates[
                4:15
            ]
            if (
                candidate["cp"]
                <= best_cp - 150
                and candidate["cp"]
                >= max(
                    200,
                    current_advantage - 350
                )
            )
        ]

        if blunder_candidates:
            chosen = choose_human_candidate(
                board,
                blunder_candidates
            )

            return (
                chosen["move"],
                chosen["info"],
                {
                    "rank": chosen["rank"],
                    "current_cp": current_advantage,
                    "selected_cp": chosen["cp"],
                    "reason": (
                        f"HUMAN BLUNDER "
                        f"(Engine #{chosen['rank'] + 1}) | "
                        f"BEST={best_cp / 100:+.2f} "
                        f"SELECTED={chosen['cp'] / 100:+.2f}"
                    )
                }
            )

    # 4. BAKWAS: +5.00 to +8.00.
    if (
        HUMAN_LIKE_BAKWAS_MIN_ADVANTAGE_CP
        < current_advantage
        < HUMAN_LIKE_BAKWAS_MAX_ADVANTAGE_CP
        and current_advantage < HUMAN_LIKE_LAZY_MIN_ADVANTAGE_CP
        and random.randint(
            1,
            HUMAN_LIKE_BAKWAS_CHANCE_DENOM
        ) == 1
    ):
        start_rank = (
            HUMAN_LIKE_BAKWAS_START_RANK_INDEX
        )
        end_rank = min(
            HUMAN_LIKE_BAKWAS_END_RANK_INDEX,
            len(candidates)
        )

        if start_rank < end_rank:
            bakwas_candidates = [
                candidate
                for candidate in candidates[
                    start_rank:end_rank
                ]
                if (
                    candidate["cp"]
                    > HUMAN_LIKE_BAKWAS_MIN_RESULT_CP
                    and candidate["cp"]
                    >= max(
                        100,
                        current_advantage
                        - 150
                    )
                    and candidate["cp"]
                    <= best_cp - 50
                )
            ]

            if bakwas_candidates:
                chosen = choose_human_candidate(
                    board,
                    bakwas_candidates
                )

                return (
                    chosen["move"],
                    chosen["info"],
                    {
                        "rank": chosen["rank"],
                        "current_cp": current_advantage,
                        "selected_cp": chosen["cp"],
                        "reason": (
                            f"BAKWAS MOVE "
                            f"(Engine #{chosen['rank'] + 1}) | "
                            f"BEST={current_advantage / 100:+.2f} "
                            f"SELECTED={chosen['cp'] / 100:+.2f}"
                        )
                    }
                )

    # 5. NORMAL INACCURACY: +2.50 to +5.00.
    if (
        HUMAN_LIKE_INACCURACY_MIN_ADVANTAGE_CP
        < current_advantage
        <= HUMAN_LIKE_INACCURACY_MAX_ADVANTAGE_CP
        and random.randint(
            1,
            HUMAN_LIKE_INACCURACY_CHANCE_DENOM
        ) == 1
    ):
        start_rank = (
            HUMAN_LIKE_INACCURACY_START_RANK_INDEX
        )
        end_rank = min(
            HUMAN_LIKE_INACCURACY_END_RANK_INDEX,
            len(candidates)
        )

        inaccuracy_candidates = [
            candidate
            for candidate in candidates[
                start_rank:end_rank
            ]
            if (
                candidate["cp"]
                > HUMAN_LIKE_INACCURACY_MIN_RESULT_CP
                and candidate["cp"]
                <= best_cp - 20
                and candidate["cp"]
                >= max(
                    50,
                    best_cp - 180
                )
            )
        ]

        if inaccuracy_candidates:
            chosen = choose_human_candidate(
                board,
                inaccuracy_candidates
            )

            return (
                chosen["move"],
                chosen["info"],
                {
                    "rank": chosen["rank"],
                    "current_cp": current_advantage,
                    "selected_cp": chosen["cp"],
                    "reason": (
                        f"INACCURACY "
                        f"(Engine #{chosen['rank'] + 1}) | "
                        f"BEST={current_advantage / 100:+.2f} "
                        f"SELECTED={chosen['cp'] / 100:+.2f}"
                    )
                }
            )

    # 6. NORMAL HUMAN PLAY.
    # Use a broader safe pool so #4/#5/#6/#7/#8 can appear naturally.
    # Human feature preferences are applied only after the safety floor.
    # Normal human play: use a wider evaluation band. The old
    # safety floor was narrow enough to leave only #1/#2 in many positions.
    normal_variation_drop_cp = min(
        350,
        max(
            100,
            int(
                max(
                    150,
                    abs(best_cp)
                ) * 0.35
            )
        )
    )

    human_floor_cp = (
        best_cp
        - normal_variation_drop_cp
    )

    if best_cp >= 0:
        human_floor_cp = max(
            5,
            human_floor_cp
        )

    if opponent_sample_count < OPPONENT_MIN_SAMPLES:
        normal_rank_cap = 7
    elif opponent_accuracy is None or opponent_accuracy < 70.0:
        normal_rank_cap = 7
    elif opponent_accuracy < 80.0:
        normal_rank_cap = 6
    elif opponent_accuracy < 88.0:
        normal_rank_cap = 5
    else:
        normal_rank_cap = 3

    human_safe_candidates = [
        candidate
        for candidate in candidates
        if (
            candidate["rank"] <= normal_rank_cap
            and candidate["cp"] >= human_floor_cp
        )
    ]

    if not human_safe_candidates:
        human_safe_candidates = [
            best
        ]

    chosen = choose_human_candidate(
        board,
        human_safe_candidates
    )

    capture_note = (
        " | HUMAN CAPTURE"
        if board.is_capture(chosen["move"])
        else ""
    )

    return (
        chosen["move"],
        chosen["info"],
        {
            "rank": chosen["rank"],
            "current_cp": current_advantage,
            "selected_cp": chosen["cp"],
            "reason": (
                f"Human Safe Fuzzy "
                f"(#{chosen['rank'] + 1}) | "
                f"SAFE_POOL={len(human_safe_candidates)} "
                f"CAP=#"
                f"{normal_rank_cap + 1} "
                f"FLOOR={human_floor_cp / 100:+.2f} "
                f"BEST={best_cp / 100:+.2f} "
                f"SELECTED={chosen['cp'] / 100:+.2f}"
                f"{capture_note}"
            )
        }
    )

    near_equal_floor = (
        best_cp - 20
    )

    safe = [
        c
        for c in candidates
        if (
            c["cp"] >= near_equal_floor
            and c["rank"] <= adaptive_max_rank
        )
    ]

    if not safe:
        safe = [best]

    rank_weights = {
        0: 5.0,
        1: 3.8,
        2: 3.2,
        3: 2.4,
        4: 1.8,
        5: 1.2,
        6: 0.8,
        7: 0.5,
    }

    weighted = []

    for candidate in safe:
        weighted.append(
            (
                candidate,
                rank_weights.get(
                    candidate["rank"],
                    0.3
                )
            )
        )

    total = sum(
        weight
        for _, weight
        in weighted
    )

    pick = random.uniform(
        0,
        total
    )

    running = 0.0
    selected = weighted[0][0]

    for candidate, weight in weighted:
        running += weight

        if pick <= running:
            selected = candidate
            break

    return (
        selected["move"],
        selected["info"],
        {
            "rank": selected["rank"],
            "current_cp": best_cp,
            "selected_cp": selected["cp"],
            "reason": (
                f"near-equal shuffle | "
                f"BEST="
                f"{best_cp/100:+.2f} "
                f"SELECTED="
                f"{selected['cp']/100:+.2f} "
                f"RANK=#"
                f"{selected['rank'] + 1}"
            )
        }
    )


