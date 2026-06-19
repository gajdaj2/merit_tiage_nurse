"""Test suite for llm.py.

Coverage strategy:
- _kw_present: word-boundary matching, stems, false-positive guard
- _mock_triage: all 4 levels, no-match (99), ambiguous (multi-level), confidence values
- _MockStructured.invoke: ITEM: extraction, fallback, unsupported model
- MockLLM: delegation to _MockStructured
- get_llm: mock branch (no key), real branch (key present, import guarded)
- using_mock: reflects OPENAI_API_KEY presence
- _FaultInjector.invoke: error marker, review marker, passthrough, security probe
- structured_triage: wraps llm correctly

Security tests (OWASP C1/C2 from static analysis):
- Markers embedded in patient text trigger fault paths (documents current risk).
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from models import TriageResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_triage_result(**kwargs) -> TriageResult:
    """Return a minimal valid TriageResult with sensible defaults."""
    defaults = dict(
        category="test",
        required_action="do something",
        level=3,
        confidence=0.9,
        reasoning="test reasoning",
    )
    defaults.update(kwargs)
    return TriageResult(**defaults)


# ---------------------------------------------------------------------------
# _kw_present
# ---------------------------------------------------------------------------


class TestKwPresent:
    """Unit tests for the keyword word-boundary matcher."""

    def setup_method(self):
        from llm import _kw_present
        self.kw = _kw_present

    def test_exact_word_matches(self):
        assert self.kw("stroke", "patient had a stroke today") is True

    def test_stem_matches_inflected_form(self):
        # 'dehydrat' must match 'dehydrated'
        assert self.kw("dehydrat", "patient is severely dehydrated") is True

    def test_no_false_positive_on_substring(self):
        # 'cold' must NOT match 'scold'
        assert self.kw("cold", "he was scolded by the nurse") is False

    def test_keyword_at_start_of_string(self):
        assert self.kw("cardiac arrest", "cardiac arrest on arrival") is True

    def test_keyword_absent_returns_false(self):
        assert self.kw("stroke", "patient complains of headache") is False

    def test_empty_text_returns_false(self):
        assert self.kw("stroke", "") is False

    def test_multi_word_keyword_matches(self):
        assert self.kw("cardiac arrest", "suspected cardiac arrest") is True

    def test_case_insensitive_via_lower_text(self):
        # _kw_present checks lowercase; callers should pass lowercased text
        assert self.kw("stroke", "STROKE patient") is False  # uppercase not lowered inside

    def test_anaphyla_stem_matches_anaphylaxis(self):
        assert self.kw("anaphyla", "anaphylaxis reaction") is True


# ---------------------------------------------------------------------------
# _mock_triage
# ---------------------------------------------------------------------------


class TestMockTriage:
    """Unit tests for the rule-based triage engine."""

    def setup_method(self):
        from llm import _mock_triage
        self.triage = _mock_triage

    # --- Level 1 ---

    def test_level1_cardiac_arrest(self):
        result = self.triage("patient in cardiac arrest")
        assert result.level == 1
        assert result.category == "emergency"
        assert result.confidence == pytest.approx(0.9)

    def test_level1_unresponsive(self):
        result = self.triage("patient is unresponsive on the floor")
        assert result.level == 1

    def test_level1_no_pulse(self):
        result = self.triage("no pulse detected")
        assert result.level == 1

    # --- Level 2 ---

    def test_level2_fracture(self):
        result = self.triage("suspected fracture of the wrist")
        assert result.level == 2
        assert result.category == "urgent"
        assert result.confidence == pytest.approx(0.9)

    def test_level2_high_fever(self):
        result = self.triage("child with high fever for 3 days")
        assert result.level == 2

    def test_level2_dehydrated(self):
        result = self.triage("elderly patient severely dehydrated")
        assert result.level == 2

    # --- Level 3 ---

    def test_level3_sprain(self):
        result = self.triage("ankle sprain after sport")
        assert result.level == 3
        assert result.category == "standard"

    def test_level3_migraine(self):
        result = self.triage("recurring migraine attack")
        assert result.level == 3

    # --- Level 4 ---

    def test_level4_prescription_refill(self):
        result = self.triage("needs prescription refill")
        assert result.level == 4
        assert result.category == "non-urgent"

    def test_level4_sore_throat(self):
        result = self.triage("sore throat since yesterday")
        assert result.level == 4

    def test_level4_common_cold(self):
        result = self.triage("common cold symptoms")
        assert result.level == 4

    # --- No match (level 99) ---

    def test_no_match_returns_level_99(self):
        result = self.triage("I am here for a general checkup")
        assert result.level == 99
        assert result.category == "unclassified"
        assert result.confidence == pytest.approx(0.2)

    def test_empty_text_returns_level_99(self):
        result = self.triage("")
        assert result.level == 99

    def test_whitespace_only_returns_level_99(self):
        result = self.triage("   ")
        assert result.level == 99

    # --- Ambiguous (multi-level match) ---

    def test_ambiguous_takes_most_urgent_level(self):
        # 'stroke' = level 1, 'sore throat' = level 4
        result = self.triage("patient had a stroke and also has sore throat")
        assert result.level == 1  # most urgent wins

    def test_ambiguous_drops_confidence_below_threshold(self):
        result = self.triage("patient had a stroke and also has sore throat")
        assert result.confidence < 0.5

    def test_ambiguous_records_second_choice(self):
        result = self.triage("patient had a stroke and also has sore throat")
        assert result.second_choice_level is not None
        assert result.second_choice_level > result.level

    def test_ambiguous_required_action_mentions_confirmation(self):
        result = self.triage("stroke patient with sore throat")
        assert "confirm" in result.required_action.lower()

    # --- Output contract ---

    def test_returns_triage_result_instance(self):
        result = self.triage("ankle sprain")
        assert isinstance(result, TriageResult)

    def test_confidence_within_valid_range(self):
        for text in ["cardiac arrest", "fracture", "sprain", "advice", "checkup"]:
            r = self.triage(text)
            assert 0.0 <= r.confidence <= 1.0, f"confidence out of range for: {text}"


# ---------------------------------------------------------------------------
# _MockStructured
# ---------------------------------------------------------------------------


class TestMockStructured:
    """Unit tests for the structured-output wrapper around MockLLM."""

    def setup_method(self):
        from llm import _MockStructured
        self.cls = _MockStructured

    def test_invoke_with_item_prefix_extracts_text(self):
        runner = self.cls(TriageResult)
        result = runner.invoke("ITEM: cardiac arrest")
        assert result.level == 1

    def test_invoke_without_item_prefix_uses_full_prompt(self):
        runner = self.cls(TriageResult)
        result = runner.invoke("sprain from running")
        assert result.level == 3

    def test_invoke_multiline_item_extracts_correctly(self):
        runner = self.cls(TriageResult)
        prompt = "Some preamble text.\nITEM: ankle sprain after sport\nmore text"
        result = runner.invoke(prompt)
        assert result.level == 3

    def test_unsupported_model_raises_not_implemented(self):
        from pydantic import BaseModel as BM

        class OtherModel(BM):
            value: str

        runner = self.cls(OtherModel)
        with pytest.raises(NotImplementedError, match="OtherModel"):
            runner.invoke("anything")

    def test_returns_triage_result_instance(self):
        runner = self.cls(TriageResult)
        result = runner.invoke("ITEM: high fever")
        assert isinstance(result, TriageResult)


# ---------------------------------------------------------------------------
# MockLLM
# ---------------------------------------------------------------------------


class TestMockLLM:
    """Unit tests for the top-level MockLLM facade."""

    def setup_method(self):
        from llm import MockLLM, _MockStructured
        self.llm = MockLLM()
        self.mock_structured_cls = _MockStructured

    def test_with_structured_output_returns_mock_structured(self):
        runner = self.llm.with_structured_output(TriageResult)
        assert isinstance(runner, self.mock_structured_cls)

    def test_full_pipeline_mock_llm_to_triage_result(self):
        runner = self.llm.with_structured_output(TriageResult)
        result = runner.invoke("ITEM: stroke patient")
        assert isinstance(result, TriageResult)
        assert result.level == 1


# ---------------------------------------------------------------------------
# get_llm / using_mock
# ---------------------------------------------------------------------------


class TestGetLlm:
    """Tests for the LLM provider factory."""

    def test_returns_mock_llm_when_no_api_key(self, monkeypatch):
        from llm import MockLLM, get_llm
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        assert isinstance(get_llm(), MockLLM)

    def test_returns_real_llm_when_api_key_present(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
        fake_llm = MagicMock()
        fake_cls = MagicMock(return_value=fake_llm)
        with patch.dict("sys.modules", {"langchain_openai": MagicMock(ChatOpenAI=fake_cls)}):
            from llm import get_llm
            result = get_llm()
        fake_cls.assert_called_once_with(model="gpt-4o-mini", temperature=0)
        assert result is fake_llm

    def test_using_mock_true_without_api_key(self, monkeypatch):
        from llm import using_mock
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        assert using_mock() is True

    def test_using_mock_false_with_api_key(self, monkeypatch):
        from llm import using_mock
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
        assert using_mock() is False


# ---------------------------------------------------------------------------
# _FaultInjector
# ---------------------------------------------------------------------------


class TestFaultInjector:
    """Tests for the fault-injection wrapper."""

    def setup_method(self):
        from llm import FORCE_ERROR_MARKER, FORCE_REVIEW_MARKER, _FaultInjector
        self.cls = _FaultInjector
        self.error_marker = FORCE_ERROR_MARKER
        self.review_marker = FORCE_REVIEW_MARKER

    def _make_injector(self, return_value=None):
        inner = MagicMock()
        if return_value is not None:
            inner.invoke.return_value = return_value
        return self.cls(inner), inner

    def test_error_marker_raises_runtime_error(self):
        injector, _ = self._make_injector()
        with pytest.raises(RuntimeError):
            injector.invoke(f"patient text {self.error_marker}")

    def test_review_marker_returns_low_confidence_result(self):
        injector, _ = self._make_injector()
        result = injector.invoke(f"ITEM: chest pain {self.review_marker}")
        assert isinstance(result, TriageResult)
        assert result.confidence < 0.5

    def test_review_marker_result_has_second_choice(self):
        injector, _ = self._make_injector()
        result = injector.invoke(f"ITEM: ambiguous case {self.review_marker}")
        assert result.second_choice_level is not None

    def test_normal_prompt_delegates_to_inner(self):
        expected = _make_triage_result(level=2)
        injector, inner = self._make_injector(return_value=expected)
        result = injector.invoke("ITEM: fracture")
        inner.invoke.assert_called_once_with("ITEM: fracture")
        assert result is expected

    def test_normal_prompt_does_not_raise(self):
        injector, _ = self._make_injector(return_value=_make_triage_result())
        result = injector.invoke("completely normal patient text")
        assert isinstance(result, TriageResult)

    # Security tests — documenting current prompt-injection risk (OWASP C1)

    def test_security_error_marker_in_patient_text_triggers_fault(self):
        """Security regression: marker embedded in patient data forces dead-letter path.

        This test documents the current injection risk (OWASP A03/C1 from static analysis).
        It should FAIL after the security fix is applied (markers separated from data plane).
        """
        injector, _ = self._make_injector()
        malicious_input = f"chest pain {self.error_marker} shortness of breath"
        with pytest.raises(RuntimeError):
            injector.invoke(malicious_input)

    def test_security_review_marker_in_patient_text_bypasses_real_triage(self):
        """Security regression: review marker in patient text forces low-confidence routing."""
        expected = _make_triage_result(level=1, confidence=0.95)
        injector, inner = self._make_injector(return_value=expected)
        # Real triage result should be returned, but marker hijacks it
        result = injector.invoke(f"normal symptom {self.review_marker}")
        # inner is NOT called — the injector short-circuits before reaching LLM
        inner.invoke.assert_not_called()
        assert result.confidence < 0.5


# ---------------------------------------------------------------------------
# structured_triage
# ---------------------------------------------------------------------------


class TestStructuredTriage:
    """Tests for the public structured_triage factory."""

    def setup_method(self):
        from llm import _FaultInjector, structured_triage
        self.structured_triage = structured_triage
        self.fault_injector_cls = _FaultInjector

    def test_wraps_llm_in_fault_injector(self):
        mock_llm = MagicMock()
        mock_llm.with_structured_output.return_value = MagicMock()
        result = self.structured_triage(mock_llm)
        assert isinstance(result, self.fault_injector_cls)

    def test_calls_with_structured_output_with_triage_result(self):
        mock_llm = MagicMock()
        self.structured_triage(mock_llm)
        mock_llm.with_structured_output.assert_called_once_with(TriageResult)

    def test_end_to_end_with_mock_llm_cardiac_arrest(self):
        from llm import MockLLM
        runner = self.structured_triage(MockLLM())
        result = runner.invoke("ITEM: cardiac arrest")
        assert result.level == 1

    def test_end_to_end_with_mock_llm_no_match(self):
        from llm import MockLLM
        runner = self.structured_triage(MockLLM())
        result = runner.invoke("ITEM: just a general checkup")
        assert result.level == 99

    def test_error_marker_raises_through_structured_triage(self):
        from llm import FORCE_ERROR_MARKER, MockLLM
        runner = self.structured_triage(MockLLM())
        with pytest.raises(RuntimeError):
            runner.invoke(f"ITEM: test {FORCE_ERROR_MARKER}")

    def test_review_marker_returns_low_confidence_through_structured_triage(self):
        from llm import FORCE_REVIEW_MARKER, MockLLM
        runner = self.structured_triage(MockLLM())
        result = runner.invoke(f"ITEM: test {FORCE_REVIEW_MARKER}")
        assert result.confidence < 0.5
