"""
Load case name resolution (A3).

The old implementation scanned a set, so which candidate won depended on
string hash randomisation — results could differ between runs of the same
data. It also matched substrings anywhere, so 'TT_1' silently resolved to
'TT_10'.
"""

import random

import pytest

from shell_kit.combination import (
    resolve_load_case,
    validate_combinations,
    format_resolution_warnings,
)


def _combo(name, lcs):
    return {'name': name, 'lc_factors': [(lc, 1.0) for lc in lcs]}


# =============================================================================
# Tier ordering
# =============================================================================

def test_exact_match_wins():
    available = sorted(['TT_1', 'TT_10', 'TT_1(RS)'])
    resolved, tier, _ = resolve_load_case('TT_1', available)
    assert resolved == 'TT_1'
    assert tier == 1


def test_parenthetical_suffix_stripped():
    """The real-world case: Midas exports 'EQ_X_POS(RS)', combos say 'EQ_X_POS'."""
    available = sorted(['EQ_X_POS(RS)', 'EQ_Y_POS(RS)', 'MS'])
    resolved, tier, candidates = resolve_load_case('EQ_X_POS', available)
    assert resolved == 'EQ_X_POS(RS)'
    assert tier == 2
    assert candidates == ['EQ_X_POS(RS)']


def test_suffix_tier_beats_prefix_tier():
    """'TT_1(RS)' is a far better match for 'TT_1' than 'TT_10' is."""
    available = sorted(['TT_10', 'TT_1(RS)'])
    resolved, tier, _ = resolve_load_case('TT_1', available)
    assert resolved == 'TT_1(RS)'
    assert tier == 2


def test_unresolvable_returns_none():
    resolved, tier, candidates = resolve_load_case('NOPE', sorted(['MS', 'MA']))
    assert resolved is None
    assert tier == 0
    assert candidates == []


# =============================================================================
# Determinism — the core of the bug
# =============================================================================

def test_resolution_is_deterministic_across_input_orderings():
    names = ['TT_10', 'TT_11', 'TT_12', 'TT_13', 'TT_1X']
    baseline, _, _ = resolve_load_case('TT_1', sorted(names))

    rng = random.Random(1234)
    for _ in range(50):
        shuffled = names[:]
        rng.shuffle(shuffled)
        resolved, _, _ = resolve_load_case('TT_1', sorted(shuffled))
        assert resolved == baseline


def test_validate_accepts_any_iterable_not_just_set():
    """Callers pass a list; a set would reintroduce ordering nondeterminism."""
    combos = [_combo('K1', ['EQ_X_POS'])]
    missing, matched, uncertain = validate_combinations(
        combos, ['EQ_X_POS(RS)', 'MS'],
    )
    assert missing == []
    assert matched == {'EQ_X_POS': 'EQ_X_POS(RS)'}
    assert len(uncertain) == 1


# =============================================================================
# Ambiguity reporting
# =============================================================================

def test_ambiguous_match_is_reported():
    combos = [_combo('K1', ['TT_1'])]
    _, matched, uncertain = validate_combinations(combos, ['TT_10', 'TT_11'])

    assert matched['TT_1'] == 'TT_10'          # deterministic pick
    lc, resolved, tier, candidates = uncertain[0]
    assert len(candidates) == 2                 # but flagged as ambiguous

    lines = format_resolution_warnings(uncertain)
    assert 'AMBIGUOUS' in lines[0]
    assert 'TT_11' in lines[0]


def test_exact_matches_produce_no_warnings():
    combos = [_combo('K1', ['MS', 'MA'])]
    missing, matched, uncertain = validate_combinations(combos, ['MS', 'MA'])
    assert missing == []
    assert matched == {}
    assert format_resolution_warnings(uncertain) == []


def test_missing_load_case_is_reported_not_guessed():
    combos = [_combo('K1', ['GEMPA'])]
    missing, matched, _ = validate_combinations(combos, ['MS', 'MA'])
    assert missing == [('K1', 'GEMPA')]
    assert 'GEMPA' not in matched


def test_each_name_reported_once_even_across_many_combos():
    combos = [_combo(f'K{i}', ['EQ_X_POS']) for i in range(5)]
    _, _, uncertain = validate_combinations(combos, ['EQ_X_POS(RS)'])
    assert len(uncertain) == 1
