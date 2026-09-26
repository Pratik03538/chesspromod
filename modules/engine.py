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



def choose_human_candidate(
    board,
    candidate_list
):
    """Choose a human-like candidate without making MultiPV rank dominant.

    Every candidate already passed by the caller remains eligible. Rank only
    has a very small effect; safe captures receive a much stronger preference,
    matching the tendency to take an available opponent piece.
    """
    if not candidate_list:
        return None

    if len(candidate_list) == 1:
        return candidate_list[0]

    weighted = []

    for candidate in candidate_list:
        rank = int(candidate.get("rank", 0))

        # Keep rank influence intentionally flat: #1/#2 should not dominate
        # simply because Stockfish listed them first.
        rank_weight = max(
            0.90,
            1.0 - (rank * 0.006)
        )

        weight = rank_weight
        move = candidate["move"]

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

            capture_weight = (
                4.0
                + min(
                    captured_value,
                    900
                ) / 900.0 * 2.0
            )

            weight *= capture_weight

        weighted.append(
            (candidate, weight)
        )

    return random.choices(
        [item[0] for item in weighted],
        weights=[item[1] for item in weighted],
        k=1
    )[0]

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
        current_eval_info = engine.analyse(
            board,
            chess.engine.Limit(
                time=HUMAN_LIKE_EVAL_TIME
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

    # 1. GM LAZY CONVERSION: preserve the +8 start, but exit once the
    # advantage is already very large. Inside the window, all sufficiently
    # winning candidates are eligible instead of only #1-#4.
    if (
        current_advantage >= HUMAN_LIKE_LAZY_MIN_ADVANTAGE_CP
        and current_advantage < HUMAN_LIKE_LAZY_MAX_ADVANTAGE_CP
    ):
        acceptable_finishers = [
            candidate
            for candidate in candidates
            if (
                candidate["cp"]
                > HUMAN_LIKE_LAZY_MIN_RESULT_CP
            )
        ]

        if not acceptable_finishers:
            acceptable_finishers = [
                best
            ]

        chosen = choose_human_candidate(
            board,
            acceptable_finishers
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
                    f"GM Lazy Conversion "
                    f"(#{chosen['rank'] + 1}) | "
                    f"SAFE_POOL={len(acceptable_finishers)} "
                    f"BEST={current_advantage / 100:+.2f} "
                    f"SELECTED={chosen['cp'] / 100:+.2f}"
                    f"{capture_note}"
                )
            }
        )

    # 2. EMERGENCY PULL-UP: below +1.50.
    if current_advantage < HUMAN_LIKE_PULLUP_MAX_ADVANTAGE_CP:
        acceptable_defense = [best]

        for i in range(
            1,
            min(
                HUMAN_LIKE_PULLUP_MAX_RANK_INDEX,
                len(candidates)
            )
        ):
            candidate = candidates[i]

            if (
                abs(
                    best_cp
                    - candidate["cp"]
                )
                <= HUMAN_LIKE_PULLUP_MAX_CP_GAP
            ):
                acceptable_defense.append(
                    candidate
                )

        if current_advantage > 0:
            positive_defense = [
                candidate
                for candidate in acceptable_defense
                if candidate["cp"] > 0
            ]

            if positive_defense:
                acceptable_defense = positive_defense

        chosen = choose_human_candidate(
            board,
            acceptable_defense
        )

        return (
            chosen["move"],
            chosen["info"],
            {
                "rank": chosen["rank"],
                "current_cp": current_advantage,
                "selected_cp": chosen["cp"],
                "reason": (
                    f"Pull-Up Mode "
                    f"(#{chosen['rank'] + 1}) | "
                    f"BEST={current_advantage / 100:+.2f} "
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

            if deep_move is not None:
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
    
    # 4. BAKWAS: +5.00 to +8.00.
    if (
        HUMAN_LIKE_BAKWAS_MIN_ADVANTAGE_CP
        < current_advantage
        < HUMAN_LIKE_BAKWAS_MAX_ADVANTAGE_CP
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

    # 6. NORMAL HUMAN PLAY: every positive-evaluation candidate is
    # eligible. MultiPV rank is only a tiny weight, so #3/#4/#5 and deeper
    # safe choices can naturally appear. Losing/negative candidates remain
    # excluded whenever a positive candidate exists.
    human_safe_candidates = [
        candidate
        for candidate in candidates
        if candidate["cp"] > 0
    ]

    if not human_safe_candidates:
        # No positive continuation exists in the MultiPV set; fall back to
        # the existing best move rather than inventing a losing preference.
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
                f"BEST={current_advantage / 100:+.2f} "
                f"SELECTED={chosen['cp'] / 100:+.2f}"
                f"{capture_note}"
            )
        }
    )

    if best_cp > MIN_POSITIVE_CP:
        normal_max_drop = safe_drop_fraction(
            best_cp
        )

        max_drop = min(
            normal_max_drop,
            adaptive_max_drop
        )

        floor_cp = max(
            5,
            int(
                best_cp
                * (
                    1.0
                    - max_drop
                )
            )
        )

        global _advantage_progress_target_cp
        global _advantage_progress_hold_moves
        global _advantage_progress_hold_limit
        global _advantage_progress_side

        advantage_mode = False
        advantage_maintain = False
        advantage_growth = False
        advantage_target_cp = None

        if best_cp < HUMAN_ADVANTAGE_START_CP:
            _advantage_progress_target_cp = None
            _advantage_progress_hold_moves = 0
            _advantage_progress_hold_limit = random.randint(
                HUMAN_ADVANTAGE_HOLD_MIN_MOVES,
                HUMAN_ADVANTAGE_HOLD_MAX_MOVES
            )
            _advantage_progress_side = None

        else:
            if _advantage_progress_side != mover:
                _advantage_progress_target_cp = None
                _advantage_progress_hold_moves = 0
                _advantage_progress_hold_limit = random.randint(
                    HUMAN_ADVANTAGE_HOLD_MIN_MOVES,
                    HUMAN_ADVANTAGE_HOLD_MAX_MOVES
                )
                _advantage_progress_side = mover

            if _advantage_progress_target_cp is None:
                _advantage_progress_target_cp = best_cp
                _advantage_progress_hold_moves = 0
                _advantage_progress_hold_limit = random.randint(
                    HUMAN_ADVANTAGE_HOLD_MIN_MOVES,
                    HUMAN_ADVANTAGE_HOLD_MAX_MOVES
                )

            # Do not lower the stored winning target for a small evaluation
            # fluctuation. Only reset it when the engine's best itself has
            # fallen materially below the protected winning level.
            if (
                best_cp
                < _advantage_progress_target_cp
                - HUMAN_ADVANTAGE_PROTECT_BAND_CP
            ):
                _advantage_progress_target_cp = best_cp
                _advantage_progress_hold_moves = 0

            advantage_target_cp = int(
                _advantage_progress_target_cp
            )

            advantage_mode = True

            # Every few actual Stockfish moves, make a progress move. This is
            # independent of whether the evaluation changed on the previous
            # move, so the bot cannot sit on +6.0 for dozens of moves simply
            # because the short engine scores happen to repeat.
            _advantage_progress_hold_moves += 1

            progress_due = (
                _advantage_progress_hold_moves
                >= _advantage_progress_hold_limit
                or
                best_cp
                >= advantage_target_cp
                + HUMAN_ADVANTAGE_GROWTH_TRIGGER_CP
                or
                opponent_pressure
            )

            if progress_due:
                # If the position genuinely improved, advance only a small
                # step toward the new best instead of jumping straight there.
                if best_cp > advantage_target_cp + 10:
                    growth_step = random.randint(
                        HUMAN_ADVANTAGE_GROWTH_STEP_MIN_CP,
                        HUMAN_ADVANTAGE_GROWTH_STEP_MAX_CP
                    )

                    _advantage_progress_target_cp = min(
                        best_cp,
                        advantage_target_cp + growth_step
                    )
                    advantage_target_cp = int(
                        _advantage_progress_target_cp
                    )
                    advantage_growth = True

                else:
                    # Even without a visible CP jump, deliberately use a
                    # stronger move from the current safe top end so the game
                    # keeps developing instead of repeating a passive hold.
                    advantage_growth = True

                _advantage_progress_hold_moves = 0
                _advantage_progress_hold_limit = random.randint(
                    HUMAN_ADVANTAGE_HOLD_MIN_MOVES,
                    HUMAN_ADVANTAGE_HOLD_MAX_MOVES
                )
            else:
                advantage_maintain = True

            # Protect the current winning advantage. +6 should not casually
            # fall toward +4 just because a lower MultiPV move exists.
            floor_cp = max(
                floor_cp,
                int(
                    advantage_target_cp
                    - HUMAN_ADVANTAGE_PROTECT_BAND_CP
                )
            )
        safe = [
            c
            for c in candidates
            if (
                c["cp"] >= floor_cp
                and c["cp"] > 0
                and c["rank"] <= adaptive_max_rank
            )
        ]

        if not safe:
            safe = [best]

        non_best = [
            c
            for c in safe
            if c["rank"] > 0
        ]

        if (
            len(non_best) >= 2
            and random.random() < 0.72
        ):
            pool = non_best
        else:
            pool = safe

        roll = random.random()

        if roll < 0.45:
            target_drop = random.uniform(
                0.00,
                max_drop * 0.35
            )

        elif roll < 0.78:
            target_drop = random.uniform(
                max_drop * 0.35,
                max_drop * 0.70
            )

        elif roll < 0.95:
            target_drop = random.uniform(
                max_drop * 0.70,
                max_drop * 0.90
            )

        else:
            target_drop = random.uniform(
                max_drop * 0.90,
                max_drop
            )

        desired_cp = max(
            floor_cp,
            int(
                best_cp
                * (
                    1.0
                    - target_drop
                )
            )
        )

        if advantage_mode:
            if advantage_maintain:
                desired_cp = min(
                    best_cp,
                    max(
                        floor_cp,
                        int(
                            advantage_target_cp
                            + random.uniform(
                                -HUMAN_ADVANTAGE_MAINTAIN_BAND_CP * 0.20,
                                HUMAN_ADVANTAGE_MAINTAIN_BAND_CP * 0.20
                            )
                        )
                    )
                )
            else:
                desired_cp = min(
                    best_cp,
                    max(
                        floor_cp,
                        int(
                            advantage_target_cp
                        )
                    )
                )

        if advantage_mode:
            if advantage_growth:
                # Progress move: prefer the strongest few safe continuations.
                # This is what keeps a +6 position actively developing even
                # when the short evaluation does not move on every turn.
                progress_pool = [
                    c
                    for c in safe
                    if c["cp"] >= max(
                        floor_cp,
                        advantage_target_cp,
                        best_cp - 25
                    )
                ]

                if progress_pool:
                    pool = progress_pool
                else:
                    pool = safe
            else:
                maintain_min = max(
                    floor_cp,
                    int(
                        advantage_target_cp
                        - HUMAN_ADVANTAGE_MAINTAIN_BAND_CP
                    )
                )

                maintain_pool = [
                    c
                    for c in safe
                    if (
                        c["cp"] >= maintain_min
                        and c["cp"] <= best_cp
                    )
                ]

                if maintain_pool:
                    pool = maintain_pool

        if advantage_mode and advantage_growth:
            rank_factors = {
                0: 4.50,
                1: 2.35,
                2: 1.55,
                3: 1.05,
                4: 0.70,
                5: 0.50,
                6: 0.35,
                7: 0.25,
            }
        else:
            rank_factors = {
                0: 0.95,
                1: 1.20,
                2: 1.25,
                3: 1.15,
                4: 1.00,
                5: 0.85,
                6: 0.70,
                7: 0.55,
            }

        weighted = []

        for candidate in pool:
            distance = abs(
                candidate["cp"]
                - desired_cp
            )

            weight = (
                1.0
                / (
                    1.0
                    + distance / 35.0
                )
            )

            weight *= (
                rank_factors.get(
                    candidate["rank"],
                    0.45
                )
            )

            weighted.append(
                (
                    candidate,
                    max(
                        0.01,
                        weight
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
                    (
                        "advantage growth"
                        if advantage_mode and advantage_growth
                        else "advantage maintain"
                        if advantage_mode
                        else "controlled shuffle"
                    )
                    + " | "
                    + f"BEST={best_cp/100:+.2f} "
                    + f"SELECTED={selected['cp']/100:+.2f} "
                    + f"RANK=#{selected['rank'] + 1} "
                    + f"FLOOR={floor_cp/100:+.2f} "
                    + f"MAX_DROP={max_drop*100:.1f}% "
                    + f"OPP="
                    f"{profile['opponent_accuracy'] if profile['opponent_accuracy'] is not None else 0.0:.1f}% "
                    f"TARGET="
                    f"{profile['target_accuracy']:.1f}% "
                    f"RANKCAP=#"
                    f"{adaptive_max_rank + 1}"
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


