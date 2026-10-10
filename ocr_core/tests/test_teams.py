from conftest import TEST_TEAMS

from ocr_core.teams import TeamMatcher, normalize_name


def matcher():
    return TeamMatcher(TEST_TEAMS)


def test_normalize_strips_ellipsis_and_case():
    assert normalize_name("Gyeongbuk Ascen...") == "GYEONGBUKASCEN"
    assert normalize_name(" nrg ") == "NRG"


def test_code_exact():
    assert matcher().match("GIN") == ("GIN", 1.0)


def test_truncated_panel_name():
    team, score = matcher().match("Gyeongbuk Ascen...")
    assert team == "GBA" and score >= 0.9


def test_fuzzy_ocr_noise():
    team, _ = matcher().match("Jeju Sundlal")
    assert team == "JSD"


def test_unknown():
    team, _ = matcher().match("ZZZZZZZZ")
    assert team is None
    assert matcher().match("") == (None, 0.0)
