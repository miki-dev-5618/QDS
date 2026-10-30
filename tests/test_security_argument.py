"""F1: docs/SECURITY_ARGUMENT.md stays consistent with the thresholds the code actually implements."""
import pathlib
import re

import pytest

from src.quantum_engine.security import SecurityParameters, _n_required

ROOT = pathlib.Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "SECURITY_ARGUMENT.md"


@pytest.fixture(scope="module")
def doc():
    return DOC.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def p():
    return SecurityParameters()


def test_required_sections_exist(doc):
    for heading in ("## 1. Setting and assumptions", "## 2. Definitions", "## 3. Thresholds",
                    "## 4. Relation to published QDS work", "## 5. Empirical evidence (tests, not proofs)",
                    "## 6. What we do NOT prove"):
        assert heading in doc


def test_parameters_and_legacy_thresholds_match_code(doc, p):
    assert f"| 0.02 |" in doc and p.honest_qber == 0.02
    for value in (p.mu_honest, p.gap, p.s_a, p.s_v):
        assert f"{value:.4f}".rstrip("0") in doc
    assert f"= {p.s_a:.4f}" in doc and f"= {p.s_v:.4f}" in doc
    assert f"| {p.target_failure:.0e} |" in doc


def test_hoeffding_sample_sizes_match_code(doc, p):
    eps = p.target_failure
    fr = _n_required(p.s_a - p.mu_honest, eps)
    fa = _n_required(p.forger_min_mismatch - p.s_a, eps)
    rep = _n_required((p.s_v - p.s_a) / 2.0, eps, factor=2.0)
    assert f"**{fr}** (FR, direct), **{fa}** (FA, direct) and **{rep}** (repudiation)" in doc


def test_exact_rule_numbers_match_code(doc, p):
    assert f"**n = {p.n_required()}**" in doc
    for n in (16, 32, 64):
        r = p.elimination_rule(n, False)
        b = p.bounds(n, 0, False)["hoeffding_reference"]
        row = (f"| {n} | exact, direct | {r.a1}" + ("" if r.r1 == r.a1 else f" (INCONCLUSIVE up to {r.r1})") +
               f" | {r.false_reject:.2e} | {r.forgery_accept:.2e} | {b['false_reject']} | {b['forgery_accept']} |")
        assert row in doc, row
    legacy = SecurityParameters(threshold_policy="legacy").elimination_rule(64, True)
    assert f"| 64 | legacy, forwarded (s_v) | {legacy.a1} | {legacy.false_reject:.2e} | {legacy.forgery_accept:.2e} |" in doc
    assert f"exact probability {legacy.forgery_accept:.3f} under the legacy rule" in doc


def test_reserve_sizes_match_code(doc, p):
    r16, r32 = p.reserve_plan(16)["reserve_bits"], p.reserve_plan(32)["reserve_bits"]
    assert f"sizes it at {r16} and {r32} extra positions" in doc


def _flat(text):
    return " ".join(text.split())


def test_every_citation_is_marked_for_verification(doc):
    section = doc.split("## 4. Relation to published QDS work")[1].split("## 5.")[0]
    assert "must be verified against the papers before use" in _flat(section)
    assert section.count("(verify before use)") == 1   # the column header covering every row
    for arxiv in ("quant-ph/0105032", "1309.1375", "1311.5760", "1507.02975"):
        assert arxiv in section


def test_linked_files_exist(doc):
    for link in re.findall(r"\]\((\.\./[^)#]+)\)", doc):
        assert (DOC.parent / link).resolve().exists(), link


def test_limitations_are_stated(doc):
    limits = doc.split("## 6. What we do NOT prove")[1]
    for topic in ("collective or coherent attacks", "Hardware imperfections", "Side channels",
                  "Fisher independence under drift"):
        assert topic in limits
    assert "it is not a new proof and does not cover all attacks" in _flat(doc)
