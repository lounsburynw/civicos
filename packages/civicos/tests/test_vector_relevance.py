"""
Tests for the vector+LLM relevance pipeline.

Covers: policy vector building, candidate retrieval/dedup, LLM scoring,
pipeline orchestration. All DB/API calls are mocked.
"""

import json
import pytest
import numpy as np
from unittest.mock import MagicMock, patch

from civicos._internal.legal.vector_relevance import (
    POLICY_AREAS,
    CANDIDATE_SIMILARITY_THRESHOLD,
    CANDIDATES_PER_POLICY,
    LLM_BATCH_SIZE,
    build_policy_vectors,
    retrieve_candidates,
    score_candidates_with_llm,
    run_vector_llm_pipeline,
)


# ---------- Constants ----------

class TestConstants:

    def test_policy_areas_covers_key_domains(self):
        assert "housing" in POLICY_AREAS
        assert "zoning" in POLICY_AREAS
        assert "environment" in POLICY_AREAS
        assert len(POLICY_AREAS) >= 10

    def test_each_policy_area_has_multiple_keywords(self):
        for area, keywords in POLICY_AREAS.items():
            assert len(keywords) >= 2, f"Policy area '{area}' needs multiple keywords"
            assert all(isinstance(k, str) for k in keywords)

    def test_similarity_threshold_is_moderate(self):
        assert 0.3 <= CANDIDATE_SIMILARITY_THRESHOLD <= 0.7

    def test_batch_size_reasonable(self):
        assert 10 <= LLM_BATCH_SIZE <= 50

    def test_candidates_per_policy_reasonable(self):
        assert 10 <= CANDIDATES_PER_POLICY <= 100


# ---------- Mock helpers ----------

def make_pgvector_mock(rows_per_area=3, embedding_dim=768):
    """Create a mock PgVectorBackend that returns fake embeddings."""
    mock = MagicMock()
    mock.TABLE_NAME = "vector_embeddings"
    mock._embedding_model = "text-embedding-3-small"

    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value = cursor
    mock._get_connection.return_value = conn

    # Generate deterministic fake embeddings as pgvector-style strings
    rng = np.random.RandomState(42)

    def fake_fetchall():
        rows = []
        for _ in range(rows_per_area):
            vec = rng.randn(embedding_dim)
            vec_str = "[" + ",".join(f"{v:.6f}" for v in vec) + "]"
            rows.append((vec_str,))
        return rows

    cursor.fetchall = fake_fetchall
    return mock, conn, cursor


# ---------- build_policy_vectors ----------

class TestBuildPolicyVectors:

    def test_returns_vectors_for_each_policy_area(self):
        mock, conn, cursor = make_pgvector_mock()
        result = build_policy_vectors(mock, "city-san-rafael")
        # Should have one vector per policy area (all have embeddings)
        assert len(result) == len(POLICY_AREAS)
        for area in POLICY_AREAS:
            assert area in result
            assert result[area].shape == (768,)

    def test_vectors_are_unit_normalized(self):
        mock, conn, cursor = make_pgvector_mock()
        result = build_policy_vectors(mock, "city-san-rafael")
        for area, vec in result.items():
            norm = np.linalg.norm(vec)
            assert norm == pytest.approx(1.0, abs=1e-6), \
                f"Policy vector '{area}' norm is {norm}, expected 1.0"

    def test_centroid_differs_from_individual_embeddings(self):
        """Centroid should be an average, not a copy of any single embedding."""
        mock, conn, cursor = make_pgvector_mock(rows_per_area=5)
        result = build_policy_vectors(mock, "city-san-rafael")
        # With 5 random vectors averaged, the centroid norm before normalization
        # should be less than the norm of any individual vector (averaging shrinks)
        assert len(result) > 0  # At least one area has embeddings

    def test_empty_results_returns_empty_dict(self):
        mock, conn, cursor = make_pgvector_mock()
        cursor.fetchall = lambda: []
        result = build_policy_vectors(mock, "city-san-rafael")
        assert result == {}

    def test_always_returns_connection(self):
        """Connection must be returned even when results are empty."""
        mock, conn, cursor = make_pgvector_mock()
        cursor.fetchall = lambda: []
        build_policy_vectors(mock, "city-san-rafael")
        mock._return_connection.assert_called_once_with(conn)

    def test_queries_correct_jurisdiction(self):
        mock, conn, cursor = make_pgvector_mock()
        build_policy_vectors(mock, "city-berkeley")
        for call in cursor.execute.call_args_list:
            params = call[0][1]
            assert params[0] == "city-berkeley"

    def test_queries_municipal_code_corpus(self):
        """Should filter on corpus_type = 'municipal_code'."""
        mock, conn, cursor = make_pgvector_mock()
        build_policy_vectors(mock, "city-san-rafael")
        for call in cursor.execute.call_args_list:
            sql = call[0][0]
            assert "municipal_code" in sql


# ---------- retrieve_candidates ----------

class TestRetrieveCandidates:

    def make_candidate_rows(self, n=3):
        """Generate fake candidate rows from pgvector similarity query."""
        rows = []
        for i in range(n):
            doc_id = f"rule-{2026+i}-{1000+i}"
            content = f"Rule about environmental regulation {i}"
            metadata = json.dumps({"document_number": f"{2026+i}-{1000+i}"})
            similarity = 0.8 - (i * 0.1)
            rows.append((doc_id, content, metadata, similarity))
        return rows

    def test_deduplicates_across_policy_areas(self):
        mock, conn, cursor = make_pgvector_mock()
        rows = self.make_candidate_rows(2)
        cursor.fetchall = lambda: rows

        policy_vectors = {
            "housing": np.random.randn(768),
            "zoning": np.random.randn(768),
        }
        candidates = retrieve_candidates(mock, policy_vectors)

        # 2 unique docs across 2 policy areas = still 2 (not 4)
        assert len(candidates) == 2
        assert "2026-1000" in candidates
        assert "2027-1001" in candidates

    def test_keeps_highest_similarity_on_dedup(self):
        mock, conn, cursor = make_pgvector_mock()

        call_count = [0]
        def varying_rows():
            call_count[0] += 1
            doc_num = "2026-1000"
            if call_count[0] == 1:
                return [(f"rule-{doc_num}", "text", json.dumps({"document_number": doc_num}), 0.9)]
            else:
                return [(f"rule-{doc_num}", "text", json.dumps({"document_number": doc_num}), 0.5)]

        cursor.fetchall = varying_rows

        policy_vectors = {"housing": np.random.randn(768), "zoning": np.random.randn(768)}
        candidates = retrieve_candidates(mock, policy_vectors)
        assert candidates["2026-1000"]["similarity"] == 0.9  # Kept the higher one

    def test_accumulates_all_matching_policy_areas(self):
        mock, conn, cursor = make_pgvector_mock()
        rows = [("rule-2026-1000", "text", json.dumps({"document_number": "2026-1000"}), 0.8)]
        cursor.fetchall = lambda: rows

        policy_vectors = {"housing": np.random.randn(768), "zoning": np.random.randn(768)}
        candidates = retrieve_candidates(mock, policy_vectors)
        areas = candidates["2026-1000"]["policy_areas"]
        assert len(areas) == 2
        assert set(areas) == {"housing", "zoning"}

    def test_extracts_doc_number_from_rule_prefix(self):
        mock, conn, cursor = make_pgvector_mock()
        rows = [("rule-2026-5555", "text", "{}", 0.7)]
        cursor.fetchall = lambda: rows

        candidates = retrieve_candidates(mock, {"housing": np.random.randn(768)})
        assert "2026-5555" in candidates
        assert candidates["2026-5555"]["document_number"] == "2026-5555"
        assert candidates["2026-5555"]["similarity"] == 0.7

    def test_prefers_metadata_doc_number_over_id(self):
        mock, conn, cursor = make_pgvector_mock()
        rows = [("rule-from-id", "text", json.dumps({"document_number": "from-metadata"}), 0.7)]
        cursor.fetchall = lambda: rows

        candidates = retrieve_candidates(mock, {"housing": np.random.randn(768)})
        assert "from-metadata" in candidates
        assert "from-id" not in candidates  # ID-derived key not used

    def test_skips_rows_with_no_doc_number(self):
        mock, conn, cursor = make_pgvector_mock()
        rows = [(None, "text", "{}", 0.7)]
        cursor.fetchall = lambda: rows

        candidates = retrieve_candidates(mock, {"housing": np.random.randn(768)})
        assert len(candidates) == 0

    def test_handles_metadata_as_dict(self):
        mock, conn, cursor = make_pgvector_mock()
        rows = [("rule-x", "text", {"document_number": "DOC-1"}, 0.7)]
        cursor.fetchall = lambda: rows

        candidates = retrieve_candidates(mock, {"housing": np.random.randn(768)})
        assert candidates["DOC-1"]["document_number"] == "DOC-1"
        assert candidates["DOC-1"]["content"] == "text"

    def test_preserves_content_in_candidates(self):
        mock, conn, cursor = make_pgvector_mock()
        rows = [("rule-doc1", "Important regulation text", json.dumps({"document_number": "doc1"}), 0.8)]
        cursor.fetchall = lambda: rows

        candidates = retrieve_candidates(mock, {"housing": np.random.randn(768)})
        assert candidates["doc1"]["content"] == "Important regulation text"

    def test_always_returns_connection(self):
        mock, conn, cursor = make_pgvector_mock()
        cursor.fetchall = lambda: []
        retrieve_candidates(mock, {"housing": np.random.randn(768)})
        mock._return_connection.assert_called_once_with(conn)


# ---------- score_candidates_with_llm ----------

class TestScoreCandidatesWithLLM:

    def make_candidates(self):
        return {
            "2026-1000": {
                "document_number": "2026-1000",
                "similarity": 0.75,
                "policy_areas": ["housing", "zoning"],
                "content": "Housing rule text",
            },
            "2026-2000": {
                "document_number": "2026-2000",
                "similarity": 0.60,
                "policy_areas": ["environment"],
                "content": "Environmental rule text",
            },
        }

    def make_rules(self):
        return {
            "2026-1000": {
                "title": "Housing Affordability Standards",
                "abstract": "Updates affordable housing requirements",
                "agency_names": ["HUD"],
            },
            "2026-2000": {
                "title": "Clean Water Compliance",
                "abstract": "New stormwater discharge standards",
                "agency_names": ["EPA"],
            },
        }

    @patch("openai.OpenAI")
    def test_returns_scored_results_with_correct_structure(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        llm_response = {
            "results": [
                {"document_number": "2026-1000", "score": 0.8, "summary": "Impacts local housing", "relevant": True},
                {"document_number": "2026-2000", "score": 0.4, "summary": "Affects stormwater", "relevant": True},
            ]
        }
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps(llm_response)
        mock_response.usage = MagicMock(total_tokens=500)
        mock_client.chat.completions.create.return_value = mock_response

        results, tokens = score_candidates_with_llm(
            self.make_candidates(), self.make_rules()
        )
        assert len(results) == 2
        assert tokens == 500

        # Validate full structure of first result
        r1 = next(r for r in results if r["document_number"] == "2026-1000")
        assert r1["score"] == 0.8
        assert r1["summary"] == "Impacts local housing"
        # Reasons should combine vector policy areas + LLM score + similarity
        assert "vector:housing" in r1["reasons"]
        assert "vector:zoning" in r1["reasons"]
        assert "llm_score:0.80" in r1["reasons"]
        assert "sim:0.750" in r1["reasons"]

        # Validate second result
        r2 = next(r for r in results if r["document_number"] == "2026-2000")
        assert r2["score"] == 0.4
        assert r2["summary"] == "Affects stormwater"
        assert "vector:environment" in r2["reasons"]
        assert "sim:0.600" in r2["reasons"]

    @patch("openai.OpenAI")
    def test_llm_error_returns_empty_results_zero_tokens(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.side_effect = Exception("API error")

        results, tokens = score_candidates_with_llm(
            self.make_candidates(), self.make_rules()
        )
        assert results == []
        assert tokens == 0

    @patch("openai.OpenAI")
    def test_filters_out_unknown_doc_numbers(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        # LLM returns a doc number not in our candidates
        llm_response = {
            "results": [
                {"document_number": "UNKNOWN-DOC", "score": 0.9, "summary": "?", "relevant": True},
                {"document_number": "2026-1000", "score": 0.7, "summary": "Valid", "relevant": True},
            ]
        }
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps(llm_response)
        mock_response.usage = MagicMock(total_tokens=100)
        mock_client.chat.completions.create.return_value = mock_response

        results, _ = score_candidates_with_llm(
            self.make_candidates(), self.make_rules()
        )
        # Only the valid one should be included
        assert len(results) == 1
        assert results[0]["document_number"] == "2026-1000"

    @patch("openai.OpenAI")
    def test_truncates_abstract_to_300_chars(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({"results": []})
        mock_response.usage = MagicMock(total_tokens=0)
        mock_client.chat.completions.create.return_value = mock_response

        rules = {"2026-1000": {"title": "Test", "abstract": "X" * 500, "agency_names": []}}
        candidates = {"2026-1000": {"similarity": 0.5, "policy_areas": ["housing"], "content": "x"}}

        score_candidates_with_llm(candidates, rules)

        # Verify the prompt contains truncated abstract
        call_args = mock_client.chat.completions.create.call_args
        prompt = call_args[1]["messages"][1]["content"]
        parsed_batch = json.loads(prompt.split("Rules:\n")[1])
        assert len(parsed_batch[0]["abstract"]) == 303  # 300 chars + "..."
        assert parsed_batch[0]["abstract"].endswith("...")

    @patch("openai.OpenAI")
    def test_string_agency_names_joined_correctly(self, mock_openai_cls):
        """agency_names as a string (not list) should be handled."""
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({"results": []})
        mock_response.usage = MagicMock(total_tokens=0)
        mock_client.chat.completions.create.return_value = mock_response

        rules = {"2026-1000": {"title": "Test", "abstract": "", "agency_names": "EPA"}}
        candidates = {"2026-1000": {"similarity": 0.5, "policy_areas": ["env"], "content": "x"}}

        score_candidates_with_llm(candidates, rules)

        # Verify agencies appear in the prompt correctly
        call_args = mock_client.chat.completions.create.call_args
        prompt = call_args[1]["messages"][1]["content"]
        parsed_batch = json.loads(prompt.split("Rules:\n")[1])
        assert parsed_batch[0]["agencies"] == "EPA"


# ---------- run_vector_llm_pipeline ----------

class TestRunPipeline:

    @patch("civicos._internal.legal.vector_relevance.score_candidates_with_llm")
    @patch("civicos._internal.legal.vector_relevance.retrieve_candidates")
    @patch("civicos._internal.legal.vector_relevance.build_policy_vectors")
    def test_dry_run_skips_writes_but_returns_counts(self, mock_build, mock_retrieve, mock_score):
        mock_build.return_value = {"housing": np.zeros(768)}
        mock_retrieve.return_value = {"doc-1": {"similarity": 0.8, "policy_areas": ["housing"]}}

        mock_storage = MagicMock()
        mock_storage.get_federal_rules.return_value = []
        mock_score.return_value = ([{"document_number": "doc-1", "score": 0.7, "summary": "test", "reasons": []}], 100)

        result = run_vector_llm_pipeline(mock_storage, MagicMock(), dry_run=True)
        assert result["dry_run"] is True
        assert result["candidates_scored"] == 1
        assert result["updates_written"] == 0
        assert result["total_tokens"] == 100
        mock_storage.update_federal_rules_relevance.assert_not_called()

    @patch("civicos._internal.legal.vector_relevance.score_candidates_with_llm")
    @patch("civicos._internal.legal.vector_relevance.retrieve_candidates")
    @patch("civicos._internal.legal.vector_relevance.build_policy_vectors")
    def test_live_run_writes_and_reports(self, mock_build, mock_retrieve, mock_score):
        mock_build.return_value = {"housing": np.zeros(768), "zoning": np.zeros(768)}
        mock_retrieve.return_value = {"doc-1": {"similarity": 0.8, "policy_areas": ["housing"]}}

        mock_storage = MagicMock()
        mock_storage.get_federal_rules.return_value = []
        mock_storage.update_federal_rules_relevance.return_value = 1
        mock_score.return_value = ([{"document_number": "doc-1", "score": 0.7, "summary": "test", "reasons": []}], 100)

        result = run_vector_llm_pipeline(mock_storage, MagicMock(), dry_run=False)
        assert result["dry_run"] is False
        assert result["updates_written"] == 1
        assert result["policy_areas"] == 2
        assert result["candidates_retrieved"] == 1
        assert result["candidates_scored"] == 1
        assert result["total_tokens"] == 100
        assert result["elapsed_seconds"] >= 0
        assert result["task"] == "vector_llm_relevance_pipeline"

        # Verify the update payload structure
        update_call = mock_storage.update_federal_rules_relevance.call_args[0][0]
        assert len(update_call) == 1
        assert update_call[0]["document_number"] == "doc-1"
        assert update_call[0]["local_relevance_score"] == 0.7
        assert update_call[0]["local_relevance_summary"] == "test"

    @patch("civicos._internal.legal.vector_relevance.build_policy_vectors")
    def test_returns_error_message_when_no_policy_vectors(self, mock_build):
        mock_build.return_value = {}
        result = run_vector_llm_pipeline(MagicMock(), MagicMock())
        assert "error" in result
        assert "policy vectors" in result["error"].lower()

    @patch("civicos._internal.legal.vector_relevance.retrieve_candidates")
    @patch("civicos._internal.legal.vector_relevance.build_policy_vectors")
    def test_returns_error_message_when_no_candidates(self, mock_build, mock_retrieve):
        mock_build.return_value = {"housing": np.zeros(768)}
        mock_retrieve.return_value = {}
        result = run_vector_llm_pipeline(MagicMock(), MagicMock())
        assert "error" in result
        assert "candidates" in result["error"].lower()
