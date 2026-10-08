"""Deterministic perceptual wording for the bundled acoustic analyzer.

Thresholds and ranking scales are heuristics, not population statistics or
calibrated probabilities. Do not infer identity, accent, gender, or placement.
"""
import math


def _number(metrics, key):
    value = metrics.get(key)
    return float(value) if isinstance(value, (int, float)) and math.isfinite(value) else None


def _label(value, boundaries, labels):
    return labels[sum(value >= boundary for boundary in boundaries)]


def describe_timbre(m):
    """Classify, rank, and format measurements directly; never shorten prose."""
    duration = _number(m, "duration") or 0
    active = _number(m, "active_ratio")
    # Short/sparsely voiced samples do not support confident style estimates.
    evidence = min(1.0, duration / 3) * min(1.0, (active or 0) / .35)
    timbre, style = [], []

    def add(group, text, value, center, scale, confidence):
        score = min(3.0, abs(value - center) / scale) * confidence * evidence
        if score >= .18:
            group.append((score, len(group), text))

    pitch = _number(m, "f0_median")
    pitch_text = ""
    if pitch is not None and pitch > 0 and evidence >= .15:
        register = _label(pitch, (100, 165, 220, 240, 280, 350),
                          ("very low", "low", "mid-low", "medium", "mid-high", "high", "very high"))
        pitch_text = register + " pitch"

    rolloff = _number(m, "rolloff85_median")
    low = _number(m, "low_energy")
    if rolloff is not None:
        tone = _label(rolloff, (300, 450, 700, 900, 2500),
                      ("very dark", "dark", "warm", "balanced", "bright", "very bright"))
        add(timbre, tone + " tone", rolloff, 800, 700, .8)
    if low is not None:
        body = _label(low, (4, 8, 14, 30), ("thin", "light", "balanced", "chesty", "full"))
        if body != "balanced":
            add(timbre, body + " vocal body", low, 11, 10, .65)

    flat = _number(m, "flatness")
    par = _number(m, "harmonic_par")
    # Flatness alone cannot distinguish a breathy voice from background noise.
    if flat is not None and par is not None:
        if flat < .02 and par >= 10:
            add(timbre, "clear crisp voice", flat, .03, .02, .75)
        elif flat < .05 and par >= 8:
            add(timbre, "clean voice", flat, .03, .02, .55)
        elif .05 <= flat < .2 and 3 <= par < 20:
            add(timbre, "breathy texture", flat, .03, .05, .4)

    bands = m.get("bands") or {}
    mid = _number(bands, "mid")
    highmid = _number(bands, "highmid")
    if mid is not None and highmid is not None and flat is not None and flat < .05:
        # Describe spectral emphasis, not anatomical placement or nasality.
        if mid > 60 and highmid < 15:
            add(timbre, "rounded midrange emphasis", mid, 35, 20, .7)
        elif highmid > 35:
            add(timbre, "pronounced upper-mid edge", highmid, 15, 15, .7)

    phrase_count = _number(m, "phrase_count") or 0
    phrase_length = _number(m, "phrase_seconds_median")
    pause_count = _number(m, "pause_count") or 0
    pause_length = _number(m, "pause_seconds_median")
    pause_ratio = _number(m, "pause_ratio")
    variation = _number(m, "phrase_duration_cv")
    if duration >= 3:
        if phrase_count >= 3 and phrase_length is not None:
            if phrase_length < 1:
                add(style, "short clipped phrases", phrase_length, 1.8, .8, .8)
            elif phrase_length > 2.5:
                add(style, "long sustained phrases", phrase_length, 1.8, 1.2, .8)
        if pause_count >= 2 and pause_length is not None and pause_ratio is not None:
            if pause_length >= .7:
                add(style, "long pauses between phrases", pause_length, .3, .3, .85)
            elif pause_ratio >= .25:
                add(style, "frequent short pauses", pause_ratio, .15, .15, .8)
            elif pause_length <= .25:
                add(style, "brief pauses between phrases", pause_length, .5, .3, .8)
        if phrase_count >= 4 and variation is not None:
            if variation < .25:
                add(style, "evenly measured phrasing", variation, .5, .3, .75)
            elif variation > .75:
                add(style, "varied phrase lengths", variation, .5, .3, .75)

    level_span = _number(m, "active_level_span_db")
    if level_span is not None and duration >= 3:
        if level_span > 15:
            add(style, "strong volume contrasts", level_span, 9, 6, .6)
        elif level_span < 5:
            add(style, "steady vocal intensity", level_span, 9, 6, .6)

    span = _number(m, "f0_span_st")
    if span is not None and pitch_text and duration >= 1.5:
        intonation = _label(span, (4, 8, 13, 18),
                            ("flat", "restrained", "natural", "expressive", "highly animated"))
        add(style, intonation + " intonation", span, 10.5, 5, .7)

    def select(candidates):
        # Select distinctive traits, then retain a consistent reading order.
        best = sorted(candidates, key=lambda item: (-item[0], item[1]))[:3]
        return [item[2] for item in sorted(best, key=lambda item: item[1])]

    voice = ([pitch_text] if pitch_text else []) + select(timbre)
    delivery = select(style)
    # Do not fabricate extra traits to reach a word target on weak samples.
    if not voice and not delivery:
        return "Insufficient reliable voice characteristics; use a longer, clean single-speaker recording."
    text = "; ".join(filter(None, (", ".join(voice), ", ".join(delivery))))
    return text[0].upper() + text[1:] + "."
