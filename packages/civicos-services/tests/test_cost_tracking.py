"""
Tests for cost_tracking.py — cost calculation, metadata construction, storage
dispatch, and graceful degradation for all instrumented services.

Mocks: storage backend (DB), os.getenv (for _get_storage init).
Real: calculate_cost/get_model_info from model_registry, all cost math.

To run:
    pytest packages/civicos-services/tests/test_cost_tracking.py -q --override-ini="addopts="
"""

from unittest.mock import MagicMock, patch, call
import pytest

import civicos_services.core.cost_tracking as ct
from civicos_services.core.cost_tracking import (
    log_llm_cost,
    log_completion_cost,
    log_modal_cost,
    log_assemblyai_cost,
    log_r2_cost,
    log_supabase_cost,
    reconcile_costs,
    MODAL_CPU_RATE,
    MODAL_GPU_RATES,
    ASSEMBLYAI_RATE_PER_HOUR,
    ASSEMBLYAI_DIARIZATION_PER_HOUR,
    R2_CLASS_A_PER_OP,
    R2_CLASS_B_PER_OP,
    SUPABASE_PRO_BASE,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_module_state():
    """Reset module-level singleton state between tests."""
    ct._cost_storage = None
    ct._storage_initialized = False
    ct._blob_hook_registered = False
    yield
    ct._cost_storage = None
    ct._storage_initialized = False
    ct._blob_hook_registered = False


@pytest.fixture
def mock_storage():
    """A mock storage backend with store_operating_cost returning a cost ID."""
    storage = MagicMock()
    storage.store_operating_cost.return_value = 42
    return storage


@pytest.fixture
def patch_storage(mock_storage):
    """Patch _get_storage to return mock_storage."""
    with patch.object(ct, "_get_storage", return_value=mock_storage):
        yield mock_storage


# ---------------------------------------------------------------------------
# _get_storage — lazy initialization
# ---------------------------------------------------------------------------


class TestGetStorage:
    def test_returns_none_when_database_url_not_set(self):
        with patch.dict("os.environ", {}, clear=True):
            result = ct._get_storage()
        assert result is None

    def test_caches_none_result_on_subsequent_calls(self):
        with patch.dict("os.environ", {}, clear=True):
            first = ct._get_storage()
            second = ct._get_storage()
        assert first is None
        assert second is None
        assert ct._storage_initialized is True

    def test_returns_none_on_civicos_init_error(self):
        with patch.dict("os.environ", {"DATABASE_URL": "postgres://test"}, clear=False):
            with patch("civicos.CivicOS", side_effect=RuntimeError("DB down")):
                with patch("dotenv.load_dotenv"):
                    result = ct._get_storage()
        assert result is None
        assert ct._storage_initialized is True


# ---------------------------------------------------------------------------
# _register_blob_cost_hook
# ---------------------------------------------------------------------------


class TestRegisterBlobCostHook:
    def test_only_registers_once(self):
        with patch("civicos.storage.blob.set_blob_cost_hook") as mock_hook:
            ct._register_blob_cost_hook()
            ct._register_blob_cost_hook()
        mock_hook.assert_called_once_with(ct.log_r2_cost)

    def test_swallows_import_error(self):
        with patch(
            "civicos.storage.blob.set_blob_cost_hook",
            side_effect=ImportError("no blob module"),
        ):
            ct._register_blob_cost_hook()
        assert ct._blob_hook_registered is True


# ---------------------------------------------------------------------------
# log_llm_cost
# ---------------------------------------------------------------------------


class TestLogLlmCost:
    def test_returns_none_for_empty_usage(self, patch_storage):
        assert log_llm_cost(model="gpt-4o-mini", usage={}) is None

    def test_returns_none_for_none_usage(self, patch_storage):
        assert log_llm_cost(model="gpt-4o-mini", usage=None) is None

    def test_returns_none_when_no_storage(self):
        with patch.object(ct, "_get_storage", return_value=None):
            result = log_llm_cost(model="gpt-4o-mini", usage={"total_tokens": 1000})
        assert result is None

    def test_calculates_correct_cost_for_gpt4o_mini(self, patch_storage):
        # gpt-4o-mini: $0.60 per 1M tokens → 10,000 tokens = $0.006
        usage = {"total_tokens": 10_000}
        log_llm_cost(model="gpt-4o-mini", usage=usage)

        stored = patch_storage.store_operating_cost.call_args
        assert stored[1]["amount_usd"] == pytest.approx(0.006, abs=1e-8)

    def test_calculates_cost_from_prompt_plus_completion_tokens(self, patch_storage):
        # gpt-4o-mini: $0.60/1M → 600 + 400 = 1000 tokens = $0.0006
        usage = {"prompt_tokens": 600, "completion_tokens": 400}
        log_llm_cost(model="gpt-4o-mini", usage=usage)

        stored = patch_storage.store_operating_cost.call_args
        assert stored[1]["amount_usd"] == pytest.approx(0.0006, abs=1e-8)

    def test_auto_detects_openai_provider(self, patch_storage):
        log_llm_cost(model="gpt-4o-mini", usage={"total_tokens": 100})

        stored = patch_storage.store_operating_cost.call_args
        assert stored[1]["service"] == "openai"

    def test_auto_detects_google_provider(self, patch_storage):
        log_llm_cost(model="models/gemini-2.0-flash", usage={"total_tokens": 100})

        stored = patch_storage.store_operating_cost.call_args
        assert stored[1]["service"] == "google"

    def test_explicit_provider_overrides_auto_detected(self, patch_storage):
        log_llm_cost(
            model="gpt-4o-mini",
            usage={"total_tokens": 100},
            provider="custom_provider",
        )
        stored = patch_storage.store_operating_cost.call_args
        assert stored[1]["service"] == "custom_provider"

    def test_unknown_model_gets_unknown_provider(self, patch_storage):
        log_llm_cost(model="nonexistent-model-xyz", usage={"total_tokens": 100})

        stored = patch_storage.store_operating_cost.call_args
        assert stored[1]["service"] == "unknown"

    def test_stores_category_as_llm(self, patch_storage):
        log_llm_cost(model="gpt-4o-mini", usage={"total_tokens": 100})

        stored = patch_storage.store_operating_cost.call_args
        assert stored[1]["category"] == "llm"

    def test_metadata_includes_token_counts(self, patch_storage):
        usage = {"prompt_tokens": 500, "completion_tokens": 200, "total_tokens": 700}
        log_llm_cost(model="gpt-4o-mini", usage=usage)

        metadata = patch_storage.store_operating_cost.call_args[1]["metadata"]
        assert metadata["prompt_tokens"] == 500
        assert metadata["completion_tokens"] == 200
        assert metadata["total_tokens"] == 700
        assert metadata["model"] == "gpt-4o-mini"

    def test_metadata_includes_task_when_provided(self, patch_storage):
        log_llm_cost(
            model="gpt-4o-mini",
            usage={"total_tokens": 100},
            task="navigation",
        )
        metadata = patch_storage.store_operating_cost.call_args[1]["metadata"]
        assert metadata["task"] == "navigation"

    def test_metadata_excludes_task_when_not_provided(self, patch_storage):
        log_llm_cost(model="gpt-4o-mini", usage={"total_tokens": 100})

        metadata = patch_storage.store_operating_cost.call_args[1]["metadata"]
        assert "task" not in metadata

    def test_extra_metadata_merged(self, patch_storage):
        log_llm_cost(
            model="gpt-4o-mini",
            usage={"total_tokens": 100},
            metadata={"request_id": "abc-123"},
        )
        metadata = patch_storage.store_operating_cost.call_args[1]["metadata"]
        assert metadata["request_id"] == "abc-123"
        assert metadata["model"] == "gpt-4o-mini"  # base fields preserved

    def test_jurisdiction_id_passed_through(self, patch_storage):
        log_llm_cost(
            model="gpt-4o-mini",
            usage={"total_tokens": 100},
            jurisdiction_id="city-san-rafael",
        )
        stored = patch_storage.store_operating_cost.call_args
        assert stored[1]["jurisdiction_id"] == "city-san-rafael"

    def test_returns_cost_id_from_storage(self, patch_storage):
        patch_storage.store_operating_cost.return_value = 99
        result = log_llm_cost(model="gpt-4o-mini", usage={"total_tokens": 100})
        assert result == 99

    def test_returns_none_on_storage_exception(self, patch_storage):
        patch_storage.store_operating_cost.side_effect = RuntimeError("DB error")
        result = log_llm_cost(model="gpt-4o-mini", usage={"total_tokens": 100})
        assert result is None

    def test_zero_cost_model_still_stored(self, patch_storage):
        # google/gemini-2.0-flash-exp:free has cost_per_1m_tokens = 0.0
        log_llm_cost(
            model="google/gemini-2.0-flash-exp:free",
            usage={"total_tokens": 10_000},
        )
        stored = patch_storage.store_operating_cost.call_args
        assert stored[1]["amount_usd"] == 0.0
        patch_storage.store_operating_cost.assert_called_once()

    def test_metadata_has_timestamp(self, patch_storage):
        log_llm_cost(model="gpt-4o-mini", usage={"total_tokens": 100})

        metadata = patch_storage.store_operating_cost.call_args[1]["metadata"]
        assert "timestamp" in metadata
        assert "T" in metadata["timestamp"]  # ISO format


# ---------------------------------------------------------------------------
# log_completion_cost
# ---------------------------------------------------------------------------


class TestLogCompletionCost:
    def test_returns_none_for_none_response(self, patch_storage):
        assert log_completion_cost(response=None, model="gpt-4o-mini") is None

    def test_returns_none_for_response_without_usage_attr(self, patch_storage):
        response = MagicMock(spec=[])  # empty spec → no .usage
        assert log_completion_cost(response=response, model="gpt-4o-mini") is None

    def test_returns_none_for_response_with_none_usage(self, patch_storage):
        response = MagicMock()
        response.usage = None
        assert log_completion_cost(response=response, model="gpt-4o-mini") is None

    def test_extracts_usage_and_delegates(self, patch_storage):
        response = MagicMock()
        response.usage = {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
        response.provider_name = "openai"

        log_completion_cost(response=response, model="gpt-4o-mini", task="query")

        stored = patch_storage.store_operating_cost.call_args
        # gpt-4o-mini: 150 tokens * $0.60/1M = $0.00009
        assert stored[1]["amount_usd"] == pytest.approx(0.00009, abs=1e-8)
        assert stored[1]["service"] == "openai"
        metadata = stored[1]["metadata"]
        assert metadata["task"] == "query"

    def test_extracts_provider_name_from_response(self, patch_storage):
        response = MagicMock()
        response.usage = {"total_tokens": 100}
        response.provider_name = "custom_llm"

        log_completion_cost(response=response, model="gpt-4o-mini")

        stored = patch_storage.store_operating_cost.call_args
        assert stored[1]["service"] == "custom_llm"

    def test_passes_jurisdiction_id(self, patch_storage):
        response = MagicMock()
        response.usage = {"total_tokens": 100}
        response.provider_name = "openai"

        log_completion_cost(
            response=response,
            model="gpt-4o-mini",
            jurisdiction_id="city-mill-valley",
        )
        stored = patch_storage.store_operating_cost.call_args
        assert stored[1]["jurisdiction_id"] == "city-mill-valley"


# ---------------------------------------------------------------------------
# log_modal_cost
# ---------------------------------------------------------------------------


class TestLogModalCost:
    def test_cpu_only_cost_calculation(self, patch_storage):
        # 10 seconds * 2 GB = 20 GB-seconds * MODAL_CPU_RATE
        expected_cost = 20.0 * MODAL_CPU_RATE

        log_modal_cost(
            function_name="test_fn",
            elapsed_seconds=10.0,
            memory_gb=2.0,
        )

        stored = patch_storage.store_operating_cost.call_args
        assert stored[1]["amount_usd"] == pytest.approx(expected_cost, abs=1e-8)
        assert stored[1]["service"] == "modal"
        assert stored[1]["category"] == "compute"

    def test_cpu_plus_t4_gpu_cost(self, patch_storage):
        elapsed = 60.0
        memory = 4.0
        cpu_cost = memory * elapsed * MODAL_CPU_RATE
        gpu_cost = elapsed * MODAL_GPU_RATES["T4"]
        expected = cpu_cost + gpu_cost

        log_modal_cost(
            function_name="index_corpus",
            elapsed_seconds=elapsed,
            memory_gb=memory,
            gpu="T4",
        )

        stored = patch_storage.store_operating_cost.call_args
        assert stored[1]["amount_usd"] == pytest.approx(expected, abs=1e-8)

    def test_a100_gpu_cost_is_higher_than_t4(self, patch_storage):
        elapsed = 60.0
        memory = 4.0

        log_modal_cost("fn", elapsed, memory, gpu="T4")
        t4_cost = patch_storage.store_operating_cost.call_args[1]["amount_usd"]

        log_modal_cost("fn", elapsed, memory, gpu="A100")
        a100_cost = patch_storage.store_operating_cost.call_args[1]["amount_usd"]

        assert a100_cost > t4_cost

    def test_unknown_gpu_gets_zero_gpu_cost(self, patch_storage):
        elapsed = 10.0
        memory = 2.0
        cpu_only_cost = memory * elapsed * MODAL_CPU_RATE

        log_modal_cost("fn", elapsed, memory, gpu="UNKNOWN_GPU")

        stored = patch_storage.store_operating_cost.call_args
        # Only CPU cost, no GPU cost added
        assert stored[1]["amount_usd"] == pytest.approx(cpu_only_cost, abs=1e-8)

    def test_metadata_includes_function_and_timing(self, patch_storage):
        log_modal_cost("embed_chunks", elapsed_seconds=45.67, memory_gb=8.0)

        metadata = patch_storage.store_operating_cost.call_args[1]["metadata"]
        assert metadata["function"] == "embed_chunks"
        assert metadata["elapsed_seconds"] == 45.67
        assert metadata["memory_gb"] == 8.0
        assert metadata["gb_seconds"] == pytest.approx(45.67 * 8.0, abs=0.01)

    def test_gpu_metadata_present_when_gpu_specified(self, patch_storage):
        log_modal_cost("fn", 10.0, 2.0, gpu="T4")

        metadata = patch_storage.store_operating_cost.call_args[1]["metadata"]
        assert metadata["gpu"] == "T4"
        assert metadata["gpu_cost_usd"] == pytest.approx(
            10.0 * MODAL_GPU_RATES["T4"], abs=1e-6
        )

    def test_gpu_metadata_absent_when_no_gpu(self, patch_storage):
        log_modal_cost("fn", 10.0, 2.0)

        metadata = patch_storage.store_operating_cost.call_args[1]["metadata"]
        assert "gpu" not in metadata
        assert "gpu_cost_usd" not in metadata

    def test_extra_metadata_merged(self, patch_storage):
        log_modal_cost("fn", 10.0, 2.0, metadata={"corpus": "chunks", "documents": 500})

        metadata = patch_storage.store_operating_cost.call_args[1]["metadata"]
        assert metadata["corpus"] == "chunks"
        assert metadata["documents"] == 500
        assert metadata["function"] == "fn"  # base fields preserved

    def test_jurisdiction_id_passed_through(self, patch_storage):
        log_modal_cost("fn", 10.0, 2.0, jurisdiction_id="city-san-rafael")

        stored = patch_storage.store_operating_cost.call_args
        assert stored[1]["jurisdiction_id"] == "city-san-rafael"

    def test_returns_none_when_no_storage(self):
        with patch.object(ct, "_get_storage", return_value=None):
            result = log_modal_cost("fn", 10.0, 2.0)
        assert result is None

    def test_returns_none_on_exception(self, patch_storage):
        patch_storage.store_operating_cost.side_effect = RuntimeError("fail")
        result = log_modal_cost("fn", 10.0, 2.0)
        assert result is None


# ---------------------------------------------------------------------------
# log_assemblyai_cost
# ---------------------------------------------------------------------------


class TestLogAssemblyaiCost:
    def test_cost_with_diarization(self, patch_storage):
        # 120 minutes = 2 hours
        # base: 2 * $0.21 = $0.42
        # diarization: 2 * $0.02 = $0.04
        # total: $0.46
        log_assemblyai_cost(audio_minutes=120.0, with_diarization=True)

        stored = patch_storage.store_operating_cost.call_args
        expected = 2.0 * ASSEMBLYAI_RATE_PER_HOUR + 2.0 * ASSEMBLYAI_DIARIZATION_PER_HOUR
        assert stored[1]["amount_usd"] == pytest.approx(expected, abs=1e-8)
        assert stored[1]["service"] == "assemblyai"
        assert stored[1]["category"] == "api"

    def test_cost_without_diarization(self, patch_storage):
        # 60 minutes = 1 hour, base only: $0.21
        log_assemblyai_cost(audio_minutes=60.0, with_diarization=False)

        stored = patch_storage.store_operating_cost.call_args
        expected = 1.0 * ASSEMBLYAI_RATE_PER_HOUR
        assert stored[1]["amount_usd"] == pytest.approx(expected, abs=1e-8)

    def test_zero_minutes_yields_zero_cost(self, patch_storage):
        log_assemblyai_cost(audio_minutes=0.0)

        stored = patch_storage.store_operating_cost.call_args
        assert stored[1]["amount_usd"] == 0.0

    def test_metadata_includes_audio_details(self, patch_storage):
        log_assemblyai_cost(
            audio_minutes=90.0,
            transcripts_processed=3,
            with_diarization=True,
        )

        metadata = patch_storage.store_operating_cost.call_args[1]["metadata"]
        assert metadata["audio_minutes"] == 90.0
        assert metadata["audio_hours"] == 1.5
        assert metadata["transcripts_processed"] == 3
        assert metadata["with_diarization"] is True
        assert metadata["base_cost_usd"] == pytest.approx(
            1.5 * ASSEMBLYAI_RATE_PER_HOUR, abs=1e-6
        )
        assert metadata["diarization_cost_usd"] == pytest.approx(
            1.5 * ASSEMBLYAI_DIARIZATION_PER_HOUR, abs=1e-6
        )

    def test_jurisdiction_id_passed_through(self, patch_storage):
        log_assemblyai_cost(audio_minutes=30.0, jurisdiction_id="city-fairfax")

        stored = patch_storage.store_operating_cost.call_args
        assert stored[1]["jurisdiction_id"] == "city-fairfax"

    def test_extra_metadata_merged(self, patch_storage):
        log_assemblyai_cost(
            audio_minutes=30.0,
            metadata={"meeting_id": "mtg-001"},
        )
        metadata = patch_storage.store_operating_cost.call_args[1]["metadata"]
        assert metadata["meeting_id"] == "mtg-001"

    def test_returns_none_when_no_storage(self):
        with patch.object(ct, "_get_storage", return_value=None):
            result = log_assemblyai_cost(audio_minutes=60.0)
        assert result is None

    def test_returns_none_on_exception(self, patch_storage):
        patch_storage.store_operating_cost.side_effect = RuntimeError("fail")
        result = log_assemblyai_cost(audio_minutes=60.0)
        assert result is None


# ---------------------------------------------------------------------------
# log_r2_cost
# ---------------------------------------------------------------------------


class TestLogR2Cost:
    def test_upload_uses_class_a_rate(self, patch_storage):
        log_r2_cost(operation="upload", bytes_transferred=1024)

        stored = patch_storage.store_operating_cost.call_args
        assert stored[1]["amount_usd"] == pytest.approx(R2_CLASS_A_PER_OP, abs=1e-12)
        assert stored[1]["service"] == "cloudflare_r2"
        assert stored[1]["category"] == "storage"

    def test_download_uses_class_b_rate(self, patch_storage):
        log_r2_cost(operation="download", bytes_transferred=2048)

        stored = patch_storage.store_operating_cost.call_args
        assert stored[1]["amount_usd"] == pytest.approx(R2_CLASS_B_PER_OP, abs=1e-12)

    def test_class_a_more_expensive_than_class_b(self):
        assert R2_CLASS_A_PER_OP > R2_CLASS_B_PER_OP

    def test_unknown_operation_yields_zero_cost(self, patch_storage):
        log_r2_cost(operation="list")

        stored = patch_storage.store_operating_cost.call_args
        assert stored[1]["amount_usd"] == 0.0

    def test_metadata_includes_operation_and_bytes(self, patch_storage):
        log_r2_cost(operation="upload", bytes_transferred=4096)

        metadata = patch_storage.store_operating_cost.call_args[1]["metadata"]
        assert metadata["operation"] == "upload"
        assert metadata["bytes_transferred"] == 4096

    def test_extra_metadata_merged(self, patch_storage):
        log_r2_cost(
            operation="upload",
            metadata={"key": "audio/meeting-001.mp3", "content_type": "audio/mpeg"},
        )
        metadata = patch_storage.store_operating_cost.call_args[1]["metadata"]
        assert metadata["key"] == "audio/meeting-001.mp3"
        assert metadata["content_type"] == "audio/mpeg"

    def test_jurisdiction_id_passed_through(self, patch_storage):
        log_r2_cost(operation="upload", jurisdiction_id="city-ross")

        stored = patch_storage.store_operating_cost.call_args
        assert stored[1]["jurisdiction_id"] == "city-ross"

    def test_returns_none_when_no_storage(self):
        with patch.object(ct, "_get_storage", return_value=None):
            result = log_r2_cost(operation="upload")
        assert result is None

    def test_returns_none_on_exception(self, patch_storage):
        patch_storage.store_operating_cost.side_effect = RuntimeError("fail")
        result = log_r2_cost(operation="upload")
        assert result is None


# ---------------------------------------------------------------------------
# log_supabase_cost
# ---------------------------------------------------------------------------


class TestLogSupabaseCost:
    def test_default_amount_is_pro_base(self, patch_storage):
        log_supabase_cost()

        stored = patch_storage.store_operating_cost.call_args
        assert stored[1]["amount_usd"] == SUPABASE_PRO_BASE
        assert stored[1]["amount_usd"] == 25.0

    def test_custom_amount_overrides_default(self, patch_storage):
        log_supabase_cost(amount_usd=32.50)

        stored = patch_storage.store_operating_cost.call_args
        assert stored[1]["amount_usd"] == 32.50

    def test_explicit_none_amount_uses_default(self, patch_storage):
        log_supabase_cost(amount_usd=None)

        stored = patch_storage.store_operating_cost.call_args
        assert stored[1]["amount_usd"] == 25.0

    def test_zero_amount_stored_as_zero(self, patch_storage):
        log_supabase_cost(amount_usd=0.0)

        stored = patch_storage.store_operating_cost.call_args
        assert stored[1]["amount_usd"] == 0.0

    def test_main_project_service_name_is_supabase(self, patch_storage):
        log_supabase_cost(project="main")

        stored = patch_storage.store_operating_cost.call_args
        assert stored[1]["service"] == "supabase"

    def test_relay_project_service_name_includes_suffix(self, patch_storage):
        log_supabase_cost(project="relay")

        stored = patch_storage.store_operating_cost.call_args
        assert stored[1]["service"] == "supabase_relay"

    def test_default_project_is_main(self, patch_storage):
        log_supabase_cost()

        stored = patch_storage.store_operating_cost.call_args
        assert stored[1]["service"] == "supabase"

    def test_stores_category_as_storage(self, patch_storage):
        log_supabase_cost()

        stored = patch_storage.store_operating_cost.call_args
        assert stored[1]["category"] == "storage"

    def test_metadata_includes_project_and_plan(self, patch_storage):
        log_supabase_cost(project="relay")

        metadata = patch_storage.store_operating_cost.call_args[1]["metadata"]
        assert metadata["project"] == "relay"
        assert metadata["plan"] == "pro"
        assert metadata["base_cost_usd"] == 25.0

    def test_extra_metadata_merged(self, patch_storage):
        log_supabase_cost(metadata={"compute_addon": 5.0})

        metadata = patch_storage.store_operating_cost.call_args[1]["metadata"]
        assert metadata["compute_addon"] == 5.0
        assert metadata["plan"] == "pro"  # base fields preserved

    def test_returns_none_when_no_storage(self):
        with patch.object(ct, "_get_storage", return_value=None):
            result = log_supabase_cost()
        assert result is None

    def test_returns_none_on_exception(self, patch_storage):
        patch_storage.store_operating_cost.side_effect = RuntimeError("fail")
        result = log_supabase_cost()
        assert result is None

    def test_no_jurisdiction_id_passed_by_default(self, patch_storage):
        log_supabase_cost()

        stored = patch_storage.store_operating_cost.call_args
        # jurisdiction_id not in kwargs (Supabase is not per-jurisdiction)
        assert "jurisdiction_id" not in stored[1]


# ---------------------------------------------------------------------------
# reconcile_costs
# ---------------------------------------------------------------------------


class TestReconcileCosts:
    def test_returns_error_when_no_storage(self):
        with patch.object(ct, "_get_storage", return_value=None):
            result = reconcile_costs()
        assert result == {"error": "No storage backend available"}

    def test_reports_all_expected_services(self, patch_storage):
        patch_storage.get_operating_cost_summary.return_value = {
            "total_usd": 5.0,
            "by_service": {"openai": 1.5, "supabase": 25.0},
        }

        result = reconcile_costs(period_days=30)

        assert result["period_days"] == 30
        assert result["total_logged_usd"] == 5.0
        assert "modal" in result["services"]
        assert "openai" in result["services"]
        assert "assemblyai" in result["services"]
        assert "supabase" in result["services"]
        assert "supabase_relay" in result["services"]
        assert "cloudflare_r2" in result["services"]
        assert "google" in result["services"]

    def test_marks_instrumented_services(self, patch_storage):
        patch_storage.get_operating_cost_summary.return_value = {
            "total_usd": 1.5,
            "by_service": {"openai": 1.5},
        }

        result = reconcile_costs()

        assert result["services"]["openai"]["instrumented"] is True
        assert result["services"]["openai"]["actual_usd"] == 1.5
        assert result["services"]["modal"]["instrumented"] is False
        assert result["services"]["modal"]["actual_usd"] == 0

    def test_identifies_uninstrumented_services(self, patch_storage):
        patch_storage.get_operating_cost_summary.return_value = {
            "total_usd": 26.5,
            "by_service": {"openai": 1.5, "supabase": 25.0},
        }

        result = reconcile_costs()

        uninstrumented = result["uninstrumented"]
        assert "modal" in uninstrumented
        assert "assemblyai" in uninstrumented
        assert "cloudflare_r2" in uninstrumented
        assert "openai" not in uninstrumented
        assert "supabase" not in uninstrumented

    def test_custom_period_days(self, patch_storage):
        patch_storage.get_operating_cost_summary.return_value = {
            "total_usd": 0,
            "by_service": {},
        }

        result = reconcile_costs(period_days=7)

        assert result["period_days"] == 7
        assert "since" in result

    def test_returns_error_on_exception(self, patch_storage):
        patch_storage.get_operating_cost_summary.side_effect = RuntimeError("DB down")

        result = reconcile_costs()

        assert "error" in result
        assert "DB down" in result["error"]

    def test_services_include_expected_monthly_estimates(self, patch_storage):
        patch_storage.get_operating_cost_summary.return_value = {
            "total_usd": 0,
            "by_service": {},
        }

        result = reconcile_costs()

        assert result["services"]["supabase"]["expected_monthly"] == "$25-50"
        assert result["services"]["modal"]["category"] == "compute"
        assert result["services"]["openai"]["category"] == "llm"
        assert result["services"]["cloudflare_r2"]["category"] == "storage"


# ---------------------------------------------------------------------------
# Pricing constants sanity checks
# ---------------------------------------------------------------------------


class TestPricingConstants:
    def test_modal_gpu_rates_ordered_by_cost(self):
        assert MODAL_GPU_RATES["T4"] < MODAL_GPU_RATES["A10G"]
        assert MODAL_GPU_RATES["A10G"] < MODAL_GPU_RATES["A100"]
        assert MODAL_GPU_RATES["A100"] < MODAL_GPU_RATES["H100"]

    def test_assemblyai_base_rate_higher_than_diarization(self):
        assert ASSEMBLYAI_RATE_PER_HOUR > ASSEMBLYAI_DIARIZATION_PER_HOUR

    def test_r2_class_a_writes_more_expensive_than_class_b_reads(self):
        assert R2_CLASS_A_PER_OP > R2_CLASS_B_PER_OP

    def test_supabase_pro_base_is_25(self):
        assert SUPABASE_PRO_BASE == 25.0

    def test_modal_cpu_rate_positive(self):
        assert MODAL_CPU_RATE > 0
