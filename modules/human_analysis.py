"""
Standalone post-game behavior analyzer.

This module only measures the bot's own move-selection and UI execution
telemetry. It does not alter move selection, board state, verification, or
retry behavior.

The reported "Human-like score" is a heuristic consistency score for this
bot's behavior, not a claim that the bot is indistinguishable from a human.
Remove this module and its two small hooks when the experiment is finished.
"""

import math
import statistics
import sys
import time


def _print(*args):
    sys.__stdout__.write(" ".join(str(x) for x in args) + "\n")


_SESSION = {
    "moves": [],
    "started_at": None,
}


def reset():
    _SESSION["moves"] = []
    _SESSION["started_at"] = time.perf_counter()


def _ensure_session():
    if _SESSION["started_at"] is None:
        reset()


def record_move_decision(
    move,
    rank,
    current_cp,
    selected_cp,
    reason,
    thinking_delay
):
    _ensure_session()

    _SESSION["moves"].append({
        "uci": move.uci(),
        "rank": int(rank) + 1,
        "current_cp": int(current_cp or 0),
        "selected_cp": int(selected_cp or 0),
        "reason": str(reason or ""),
        "thinking_delay": float(thinking_delay),
        "touch": None,
    })


def record_touch_behavior(
    move,
    source,
    target,
    path_points,
    drag_elapsed
):
    _ensure_session()

    for item in reversed(_SESSION["moves"]):
        if item["uci"] == move.uci() and item["touch"] is None:
            sx, sy = source
            tx, ty = target

            points = [
                (int(sx), int(sy)),
                *[
                    (int(x), int(y))
                    for x, y in path_points
                ],
                (int(tx), int(ty)),
            ]

            direct = max(
                1.0,
                math.hypot(
                    tx - sx,
                    ty - sy
                )
            )

            path_length = 0.0
            for a, b in zip(points, points[1:]):
                path_length += math.hypot(
                    b[0] - a[0],
                    b[1] - a[1]
                )

            item["touch"] = {
                "source": (sx, sy),
                "target": (tx, ty),
                "path_ratio": path_length / direct,
                "drag_elapsed": float(drag_elapsed),
                "path_points": len(path_points),
            }
            return


def _mean(values):
    return (
        statistics.mean(values)
        if values
        else 0.0
    )


def _stdev(values):
    return (
        statistics.pstdev(values)
        if len(values) > 1
        else 0.0
    )


def _clamp(value, low=0.0, high=100.0):
    return max(
        low,
        min(high, value)
    )


def _percentile(values, p):
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    index = (len(ordered) - 1) * p
    low = int(index)
    high = min(low + 1, len(ordered) - 1)
    fraction = index - low
    return ordered[low] + (ordered[high] - ordered[low]) * fraction


def _coefficient_of_variation(values):
    mean = _mean(values)
    if mean <= 0.0 or len(values) < 2:
        return 0.0
    return _stdev(values) / mean


def _adjacent_similarity(values):
    if len(values) < 3:
        return 0.0
    diffs = [abs(b - a) for a, b in zip(values, values[1:])]
    scale = max(_mean(values), 0.01)
    return _clamp(100.0 - (_mean(diffs) / scale) * 120.0)


def _rank_entropy(ranks):
    if not ranks:
        return 0.0
    counts = {}
    for rank in ranks:
        counts[rank] = counts.get(rank, 0) + 1
    total = float(len(ranks))
    entropy = 0.0
    for count in counts.values():
        p = count / total
        entropy -= p * math.log(p, 2)
    max_entropy = math.log(min(8, len(ranks)), 2) if len(ranks) > 1 else 1.0
    return _clamp(entropy / max_entropy * 100.0) if max_entropy > 0 else 0.0


def _touch_offset_stats(touch):
    if not touch:
        return 0.0, 0.0, 0.0
    radial = []
    source_target_lengths = []
    for item in touch:
        sx, sy = item['source']
        tx, ty = item['target']
        radial.append(math.hypot(sx % 100 - 50, sy % 100 - 50))
        source_target_lengths.append(math.hypot(tx - sx, ty - sy))
    return _mean(radial), _stdev(radial), _mean(source_target_lengths)

def print_report(game_board=None):
    _ensure_session()

    moves = _SESSION["moves"]

    _print("")
    _print("=" * 68)
    _print("              BOT HUMAN-BEHAVIOR ANALYSIS")
    _print("=" * 68)

    if not moves:
        _print("No bot moves were recorded.")
        _print("=" * 68)
        return

    timings = [
        x["thinking_delay"]
        for x in moves
    ]

    ranks = [
        x["rank"]
        for x in moves
    ]

    rank_hist = {}
    for rank in ranks:
        rank_hist[rank] = rank_hist.get(rank, 0) + 1

    touch = [
        x["touch"]
        for x in moves
        if x["touch"] is not None
    ]

    drag_times = [
        x["drag_elapsed"]
        for x in touch
    ]

    path_ratios = [
        x["path_ratio"]
        for x in touch
    ]

    tactical_count = sum(
        1
        for x in moves
        if (
            "MATE" in x["reason"].upper()
            or "CHECK" in x["reason"].upper()
            or "CAPTURE" in x["reason"].upper()
            or "DEEP CALC" in x["reason"].upper()
            or "GREAT MOVE" in x["reason"].upper()
        )
    )

    non_top = sum(
        1
        for x in moves
        if x["rank"] > 1
    )

    gaps = [
        max(
            0,
            x["current_cp"] - x["selected_cp"]
        )
        for x in moves
        if x["current_cp"] >= 0
    ]

    # Timing score: rewards variation without requiring slow moves.
    timing_mean = _mean(timings)
    timing_sd = _stdev(timings)

    if len(timings) <= 1:
        timing_score = 50.0
    else:
        timing_variation = _clamp(
            (timing_sd / max(timing_mean, 0.01)) * 28.0,
            0.0,
            35.0
        )
        timing_range = _clamp(
            (max(timings) - min(timings)) * 35.0,
            0.0,
            35.0
        )
        timing_score = _clamp(
            30.0
            + timing_variation
            + timing_range
        )

    # Cursor/touch score: checks that the recorded points actually vary and
    # remain close to square centers. Path ratio around 1.0 means straight;
    # modestly larger values mean a curved path.
    if not touch:
        cursor_score = 0.0
    else:
        unique_sources = len({
            item["source"]
            for item in touch
        })
        unique_targets = len({
            item["target"]
            for item in touch
        })
        point_variation = _clamp(
            (
                unique_sources + unique_targets
            )
            / max(1, 2 * len(touch))
            * 100.0
        )

        avg_path_ratio = _mean(path_ratios)
        curve_component = _clamp(
            abs(avg_path_ratio - 1.0) * 90.0,
            0.0,
            45.0
        )

        cursor_score = _clamp(
            40.0
            + point_variation * 0.45
            + curve_component
        )

    # Move-preference score: measures whether the bot actually uses the
    # MultiPV pool instead of always selecting rank #1.
    if len(ranks) <= 1:
        preference_score = 50.0
    else:
        rank_diversity = len(set(ranks)) / max(1, min(8, len(ranks)))
        non_top_rate = non_top / len(ranks)
        preference_score = _clamp(
            35.0
            + rank_diversity * 35.0
            + non_top_rate * 30.0
        )

    # Tactical timing coverage: tactical moves should not all have the same
    # near-zero delay, while quiet moves should not all wait a long time.
    tactical_delays = [
        x["thinking_delay"]
        for x in moves
        if (
            "MATE" in x["reason"].upper()
            or "DEEP CALC" in x["reason"].upper()
            or "GREAT MOVE" in x["reason"].upper()
            or "HUMAN CAPTURE" in x["reason"].upper()
        )
    ]

    tactical_timing_score = (
        _clamp(
            35.0
            + _mean(tactical_delays) * 55.0
            + _stdev(tactical_delays) * 45.0
        )
        if tactical_delays
        else 50.0
    )

    overall = _clamp(
        timing_score * 0.30
        + cursor_score * 0.25
        + preference_score * 0.30
        + tactical_timing_score * 0.15
    )

    _print(
        f"Moves analyzed       : {len(moves)}"
    )
    _print(
        f"Thinking time        : avg={timing_mean:.3f}s "
        f"sd={timing_sd:.3f}s "
        f"range={min(timings):.3f}-{max(timings):.3f}s"
    )
    _print(
        f"Timing behavior      : {timing_score:.1f}/100"
    )
    _print(
        f"Cursor/touch samples : {len(touch)}/{len(moves)}"
    )

    if touch:
        _print(
            f"Drag execution       : avg={_mean(drag_times):.3f}s "
            f"path-ratio={_mean(path_ratios):.3f}"
        )

    _print(
        f"Cursor behavior      : {cursor_score:.1f}/100"
    )
    _print(
        "Move ranks           : "
        + ", ".join(
            f"#{rank}={rank_hist[rank]}"
            for rank in sorted(rank_hist)
        )
    )
    _print(
        f"Non-#1 selections     : "
        f"{non_top}/{len(ranks)} "
        f"({non_top / len(ranks) * 100.0:.1f}%)"
    )
    _print(
        f"Move preference      : {preference_score:.1f}/100"
    )
    _print(
        f"Tactical moves       : {tactical_count}/{len(moves)}"
    )
    _print(
        f"Tactical timing      : {tactical_timing_score:.1f}/100"
    )

    if gaps:
        _print(
            f"Selection eval gap   : avg={_mean(gaps) / 100.0:.2f} "
            f"pawn"
        )

    _print("-" * 68)
    _print(
        f"OVERALL BEHAVIOR SCORE: {overall:.1f}/100"
    )
    _print(
        "Note: this is an internal heuristic measurement of the bot's "
        "behavior, not a detector-evasion or guarantee of human identity."
    )
    _print("=" * 68)

    reset()
