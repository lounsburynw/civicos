"""
Tests for testimony_extraction_pipeline.py — production testimony extraction with retry/error handling.

Covers:
- Exception hierarchy (TestimonyExtractionError subclasses)
- Pipeline init with/without existing error log
- Error logging (_log_error writes structured entries)
- Error summary aggregation (get_error_summary)
- AssemblyAI upload with retry (_upload_to_assemblyai)
- AssemblyAI polling states (_poll_assemblyai_status)
- YouTube audio download with caching (_download_youtube_audio)
- YouTube transcript extraction (_extract_youtube_transcript)
- LLM speaker name extraction with filtering (_extract_speaker_name_llm)
- Full pipeline orchestration (extract_testimony)

To run:
    pytest packages/civicos-services/tests/test_testimony_extraction_pipeline.py -q --override-ini="addopts="
"""

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from civicos_services.processing.testimony_extraction_pipeline import (
    TestimonyExtractionError,
    YouTubeTranscriptError,
    AssemblyAIError,
    LLMExtractionError,
    TestimonyExtractionPipeline,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_error_log(tmp_path):
    """Return path to a non-existent error log in a temp dir."""
    return str(tmp_path / "test_errors.json")


@pytest.fixture
def pipeline(tmp_error_log):
    """Create a pipeline with a temp error log (no pre-existing errors)."""
    return TestimonyExtractionPipeline(error_log_path=tmp_error_log)


@pytest.fixture
def pipeline_with_errors(tmp_path):
    """Create a pipeline with pre-existing errors loaded from file."""
    log_path = tmp_path / "existing_errors.json"
    existing = [
        {
            "timestamp": "2026-01-01T00:00:00",
            "operation": "assemblyai",
            "error_type": "AssemblyAIError",
            "error_message": "Upload failed",
            "context": {"youtube_video_id": "abc123"},
        },
        {
            "timestamp": "2026-01-02T00:00:00",
            "operation": "youtube_transcript",
            "error_type": "YouTubeTranscriptError",
            "error_message": "IP blocked",
            "context": {"youtube_video_id": "def456"},
        },
    ]
    log_path.write_text(json.dumps(existing))
    return TestimonyExtractionPipeline(error_log_path=str(log_path))


# ---------------------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------------------


class TestExceptionHierarchy:
    def test_youtube_error_is_testimony_extraction_error(self):
        err = YouTubeTranscriptError("test")
        assert isinstance(err, TestimonyExtractionError)

    def test_assemblyai_error_is_testimony_extraction_error(self):
        err = AssemblyAIError("test")
        assert isinstance(err, TestimonyExtractionError)

    def test_llm_error_is_testimony_extraction_error(self):
        err = LLMExtractionError("test")
        assert isinstance(err, TestimonyExtractionError)

    def test_exception_preserves_message(self):
        msg = "Transcript processing error: audio too short"
        err = AssemblyAIError(msg)
        assert str(err) == msg

    def test_base_error_is_exception(self):
        err = TestimonyExtractionError("base")
        assert isinstance(err, Exception)


# ---------------------------------------------------------------------------
# Pipeline initialization
# ---------------------------------------------------------------------------


class TestPipelineInit:
    def test_init_no_existing_log_starts_with_empty_errors(self, pipeline):
        assert pipeline.errors == []

    def test_init_loads_existing_errors_from_file(self, pipeline_with_errors):
        assert len(pipeline_with_errors.errors) == 2
        assert pipeline_with_errors.errors[0]["operation"] == "assemblyai"
        assert pipeline_with_errors.errors[1]["error_type"] == "YouTubeTranscriptError"

    def test_init_sets_error_log_path(self, tmp_error_log):
        p = TestimonyExtractionPipeline(error_log_path=tmp_error_log)
        assert p.error_log_path == Path(tmp_error_log)

    def test_init_default_path(self):
        p = TestimonyExtractionPipeline.__new__(TestimonyExtractionPipeline)
        # Verify default in signature
        import inspect
        sig = inspect.signature(TestimonyExtractionPipeline.__init__)
        default = sig.parameters["error_log_path"].default
        assert default == "data/testimony_extraction_errors.json"


# ---------------------------------------------------------------------------
# Error logging
# ---------------------------------------------------------------------------


class TestLogError:
    def test_log_error_appends_structured_entry(self, pipeline):
        err = AssemblyAIError("Upload timeout")
        ctx = {"youtube_video_id": "xyz789", "meeting_date": "2026-03-15"}

        pipeline._log_error("assemblyai", err, ctx)

        assert len(pipeline.errors) == 1
        entry = pipeline.errors[0]
        assert entry["operation"] == "assemblyai"
        assert entry["error_type"] == "AssemblyAIError"
        assert entry["error_message"] == "Upload timeout"
        assert entry["context"]["youtube_video_id"] == "xyz789"
        assert "timestamp" in entry

    def test_log_error_persists_to_file(self, pipeline, tmp_error_log):
        err = YouTubeTranscriptError("IP blocked")
        pipeline._log_error("youtube_transcript", err, {"video_id": "abc"})

        saved = json.loads(Path(tmp_error_log).read_text())
        assert len(saved) == 1
        assert saved[0]["error_type"] == "YouTubeTranscriptError"

    def test_log_error_accumulates_multiple_errors(self, pipeline):
        pipeline._log_error("op1", ValueError("err1"), {})
        pipeline._log_error("op2", RuntimeError("err2"), {})
        pipeline._log_error("op3", AssemblyAIError("err3"), {})

        assert len(pipeline.errors) == 3
        assert pipeline.errors[0]["operation"] == "op1"
        assert pipeline.errors[2]["error_message"] == "err3"


# ---------------------------------------------------------------------------
# Error summary
# ---------------------------------------------------------------------------


class TestGetErrorSummary:
    def test_empty_errors_returns_zero_totals(self, pipeline):
        summary = pipeline.get_error_summary()
        assert summary["total_errors"] == 0
        assert summary["error_types"] == {}
        assert summary["recent_errors"] == []

    def test_counts_errors_by_type(self, pipeline_with_errors):
        summary = pipeline_with_errors.get_error_summary()
        assert summary["total_errors"] == 2
        assert summary["error_types"]["AssemblyAIError"] == 1
        assert summary["error_types"]["YouTubeTranscriptError"] == 1

    def test_recent_errors_returns_last_five(self, pipeline):
        for i in range(8):
            pipeline.errors.append({
                "timestamp": f"2026-01-0{i + 1}T00:00:00",
                "operation": f"op_{i}",
                "error_type": "TestError",
                "error_message": f"error {i}",
                "context": {},
            })

        summary = pipeline.get_error_summary()
        assert len(summary["recent_errors"]) == 5
        assert summary["recent_errors"][0]["operation"] == "op_3"
        assert summary["recent_errors"][-1]["operation"] == "op_7"
        assert summary["total_errors"] == 8

    def test_multiple_same_type_counted_correctly(self, pipeline):
        for _ in range(3):
            pipeline.errors.append({
                "error_type": "AssemblyAIError",
                "timestamp": "", "operation": "", "error_message": "", "context": {},
            })
        pipeline.errors.append({
            "error_type": "YouTubeTranscriptError",
            "timestamp": "", "operation": "", "error_message": "", "context": {},
        })

        summary = pipeline.get_error_summary()
        assert summary["error_types"]["AssemblyAIError"] == 3
        assert summary["error_types"]["YouTubeTranscriptError"] == 1


# ---------------------------------------------------------------------------
# AssemblyAI upload
# ---------------------------------------------------------------------------


class TestUploadToAssemblyAI:
    @patch("civicos_services.processing.testimony_extraction_pipeline.requests.post")
    def test_successful_upload_returns_transcript_id(self, mock_post, pipeline):
        mock_response = MagicMock()
        mock_response.json.return_value = {"id": "tx_abc123"}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        result = pipeline._upload_to_assemblyai(
            audio_url="https://example.com/audio.mp3",
            speaker_count=5,
            api_key="test-key",
        )

        assert result == "tx_abc123"
        # Verify correct payload was sent
        call_kwargs = mock_post.call_args
        assert call_kwargs.kwargs["json"]["speaker_labels"] is True
        assert call_kwargs.kwargs["json"]["speakers_expected"] == 5
        assert call_kwargs.kwargs["headers"]["authorization"] == "test-key"

    @patch("civicos_services.processing.testimony_extraction_pipeline.requests.post")
    def test_missing_transcript_id_raises_assemblyai_error(self, mock_post, pipeline):
        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "queued"}  # no 'id' field
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        with pytest.raises(AssemblyAIError, match="No transcript ID in response"):
            pipeline._upload_to_assemblyai("https://example.com/audio.mp3", 5, "key")

    @patch("civicos_services.processing.testimony_extraction_pipeline.requests.post")
    def test_http_error_raises_assemblyai_error(self, mock_post, pipeline):
        import requests
        mock_post.side_effect = requests.RequestException("Connection refused")

        # Internal try/except catches RequestException and raises AssemblyAIError,
        # which is not retryable, so it propagates immediately.
        with pytest.raises(AssemblyAIError, match="Upload failed"):
            pipeline._upload_to_assemblyai(
                "https://example.com/audio.mp3", 5, "key"
            )


# ---------------------------------------------------------------------------
# AssemblyAI polling
# ---------------------------------------------------------------------------


class TestPollAssemblyAIStatus:
    @patch("civicos_services.processing.testimony_extraction_pipeline.requests.get")
    @patch("civicos_services.processing.testimony_extraction_pipeline.time.sleep")
    def test_completed_status_returns_transcript_data(self, mock_sleep, mock_get, pipeline):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "completed",
            "text": "Good evening everyone.",
            "utterances": [{"speaker": "A", "text": "Good evening"}],
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        result = pipeline._poll_assemblyai_status("tx_abc", "test-key")

        assert result["status"] == "completed"
        assert result["text"] == "Good evening everyone."
        assert len(result["utterances"]) == 1

    @patch("civicos_services.processing.testimony_extraction_pipeline.requests.get")
    @patch("civicos_services.processing.testimony_extraction_pipeline.time.sleep")
    def test_error_status_raises_with_message(self, mock_sleep, mock_get, pipeline):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "error",
            "error": "Audio file too short",
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        with pytest.raises(AssemblyAIError, match="Audio file too short"):
            pipeline._poll_assemblyai_status("tx_abc", "test-key")

    @patch("civicos_services.processing.testimony_extraction_pipeline.requests.get")
    @patch("civicos_services.processing.testimony_extraction_pipeline.time.sleep")
    def test_processing_then_completed(self, mock_sleep, mock_get, pipeline):
        """Simulates poll returning 'processing' twice, then 'completed'."""
        processing_resp = MagicMock()
        processing_resp.json.return_value = {"status": "processing"}
        processing_resp.raise_for_status = MagicMock()

        completed_resp = MagicMock()
        completed_resp.json.return_value = {
            "status": "completed",
            "text": "Motion carries.",
        }
        completed_resp.raise_for_status = MagicMock()

        mock_get.side_effect = [processing_resp, processing_resp, completed_resp]

        result = pipeline._poll_assemblyai_status("tx_abc", "test-key")

        assert result["status"] == "completed"
        assert result["text"] == "Motion carries."
        assert mock_sleep.call_count == 2

    @patch("civicos_services.processing.testimony_extraction_pipeline.requests.get")
    @patch("civicos_services.processing.testimony_extraction_pipeline.time.sleep")
    def test_http_error_during_poll_raises(self, mock_sleep, mock_get, pipeline):
        import requests
        mock_get.side_effect = requests.RequestException("Network error")

        with pytest.raises(AssemblyAIError, match="Polling failed"):
            pipeline._poll_assemblyai_status("tx_abc", "test-key")


# ---------------------------------------------------------------------------
# YouTube audio download
# ---------------------------------------------------------------------------


class TestDownloadYoutubeAudio:
    @patch("civicos_services.processing.testimony_extraction_pipeline.Path.mkdir")
    def test_returns_existing_file_path_without_redownload(self, mock_mkdir, pipeline, tmp_path):
        audio_file = tmp_path / "vid123.mp3"
        audio_file.write_bytes(b"\x00" * 1024)  # 1KB dummy file

        result = pipeline._download_youtube_audio("vid123", output_dir=str(tmp_path))

        assert result == str(tmp_path / "vid123.mp3")

    def test_returns_none_when_ytdlp_import_fails(self, pipeline, tmp_path):
        with patch.dict("sys.modules", {"yt_dlp": None}):
            result = pipeline._download_youtube_audio("vid123", output_dir=str(tmp_path))
            assert result is None

    def test_returns_none_on_download_exception(self, pipeline, tmp_path):
        mock_yt_dlp = MagicMock()
        mock_ydl = MagicMock()
        mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl.__exit__ = MagicMock(return_value=False)
        mock_ydl.extract_info.side_effect = Exception("Video unavailable")
        mock_yt_dlp.YoutubeDL.return_value = mock_ydl

        with patch.dict("sys.modules", {"yt_dlp": mock_yt_dlp}):
            result = pipeline._download_youtube_audio("vid_bad", output_dir=str(tmp_path))
            assert result is None


# ---------------------------------------------------------------------------
# YouTube transcript extraction
# ---------------------------------------------------------------------------


class TestExtractYoutubeTranscript:
    def test_successful_extraction_concatenates_snippets(self, pipeline):
        snippet1 = MagicMock()
        snippet1.text = "Good evening."
        snippet2 = MagicMock()
        snippet2.text = "The meeting will come to order."
        snippet3 = MagicMock()
        snippet3.text = "First item on the agenda."

        mock_transcript = MagicMock()
        mock_transcript.snippets = [snippet1, snippet2, snippet3]

        mock_api_instance = MagicMock()
        mock_api_instance.fetch.return_value = mock_transcript

        mock_yt_module = MagicMock()
        mock_yt_module.YouTubeTranscriptApi.return_value = mock_api_instance

        with patch.dict("sys.modules", {"youtube_transcript_api": mock_yt_module}):
            result = pipeline._extract_youtube_transcript("vid123")

        assert result == "Good evening. The meeting will come to order. First item on the agenda."

    def test_extraction_failure_raises_youtube_error(self, pipeline):
        mock_api_instance = MagicMock()
        mock_api_instance.fetch.side_effect = Exception("No transcripts found")

        mock_yt_module = MagicMock()
        mock_yt_module.YouTubeTranscriptApi.return_value = mock_api_instance

        with patch.dict("sys.modules", {"youtube_transcript_api": mock_yt_module}):
            with pytest.raises(YouTubeTranscriptError, match="Transcript extraction failed"):
                pipeline._extract_youtube_transcript("vid_no_transcript")


# ---------------------------------------------------------------------------
# LLM speaker name extraction
# ---------------------------------------------------------------------------


class TestExtractSpeakerNameLLM:
    def test_returns_none_for_empty_utterances(self, pipeline):
        result = pipeline._extract_speaker_name_llm([], "A")
        assert result is None

    def test_returns_none_when_no_utterances_match_speaker(self, pipeline):
        utterances = [
            {"speaker": "B", "text": "I'm Bob Smith."},
            {"speaker": "C", "text": "I'm Carol Jones."},
        ]
        result = pipeline._extract_speaker_name_llm(utterances, "A")
        assert result is None

    def test_returns_name_from_llm_response(self, pipeline):
        utterances = [
            {"speaker": "A", "text": "My name is Maria Santos and I live on 4th Street."},
            {"speaker": "A", "text": "I'm here to talk about the housing plan."},
        ]

        mock_provider = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "Maria Santos"
        mock_provider.complete.return_value = mock_response

        mock_llm_module = MagicMock()
        mock_llm_module.get_model_for_task.return_value = mock_provider
        with patch.dict("sys.modules", {"llm_provider": mock_llm_module}):
            result = pipeline._extract_speaker_name_llm(utterances, "A")

        assert result == "Maria Santos"

    @pytest.mark.parametrize("llm_response", ["null", "None", "N/A", "unknown", "NULL", "UNKNOWN"])
    def test_returns_none_for_null_like_llm_responses(self, pipeline, llm_response):
        utterances = [{"speaker": "A", "text": "Some speech without intro."}]

        mock_provider = MagicMock()
        mock_response = MagicMock()
        mock_response.content = llm_response
        mock_provider.complete.return_value = mock_response

        mock_llm_module = MagicMock()
        mock_llm_module.get_model_for_task.return_value = mock_provider
        with patch.dict("sys.modules", {"llm_provider": mock_llm_module}):
            result = pipeline._extract_speaker_name_llm(utterances, "A")

        assert result is None

    def test_strips_whitespace_from_llm_response(self, pipeline):
        utterances = [{"speaker": "B", "text": "Hi, I'm John Doe from Terra Linda."}]

        mock_provider = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "  John Doe  \n"
        mock_provider.complete.return_value = mock_response

        mock_llm_module = MagicMock()
        mock_llm_module.get_model_for_task.return_value = mock_provider
        with patch.dict("sys.modules", {"llm_provider": mock_llm_module}):
            result = pipeline._extract_speaker_name_llm(utterances, "B")

        assert result == "John Doe"

    def test_uses_first_20_utterances_only(self, pipeline):
        utterances = [
            {"speaker": "A", "text": f"Utterance {i}"} for i in range(30)
        ]

        mock_provider = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "null"
        mock_provider.complete.return_value = mock_response

        mock_llm_module = MagicMock()
        mock_llm_module.get_model_for_task.return_value = mock_provider
        with patch.dict("sys.modules", {"llm_provider": mock_llm_module}):
            pipeline._extract_speaker_name_llm(utterances, "A")

        # Check the prompt sent to the LLM contains exactly 20 utterances
        call_args = mock_provider.complete.call_args[0][0]
        user_msg = call_args[1]["content"]
        # Count "- Utterance" lines in the prompt
        utterance_lines = [line for line in user_msg.split("\n") if line.startswith("- Utterance")]
        assert len(utterance_lines) == 20

    def test_returns_none_on_llm_exception_without_raising(self, pipeline):
        utterances = [{"speaker": "A", "text": "Hello, I'm someone."}]

        mock_llm_module = MagicMock()
        mock_llm_module.get_model_for_task.side_effect = Exception("API key expired")
        with patch.dict("sys.modules", {"llm_provider": mock_llm_module}):
            result = pipeline._extract_speaker_name_llm(utterances, "A")

        assert result is None


# ---------------------------------------------------------------------------
# Full pipeline orchestration (extract_testimony)
# ---------------------------------------------------------------------------


class TestExtractTestimony:
    def _make_mock_transcript_result(self):
        """Create a mock AssemblyAI SDK transcript result."""
        result = MagicMock()
        result.id = "tx_full_123"
        result.status = MagicMock()
        result.status.__eq__ = lambda self, other: False  # not error
        result.text = "Good evening. Motion carries."

        utt1 = MagicMock()
        utt1.speaker = "A"
        utt1.text = "Good evening."
        utt1.start = 0
        utt1.end = 2000
        utt1.confidence = 0.95

        utt2 = MagicMock()
        utt2.speaker = "B"
        utt2.text = "Motion carries."
        utt2.start = 2000
        utt2.end = 4000
        utt2.confidence = 0.90

        result.utterances = [utt1, utt2]
        result.error = None
        return result

    def test_successful_pipeline_returns_complete_result(self, pipeline):
        mock_transcript_result = self._make_mock_transcript_result()

        with patch.object(pipeline, "_extract_youtube_transcript", return_value="Full text"):
            with patch.object(pipeline, "_download_youtube_audio", return_value="/tmp/vid.mp3"):
                mock_aai = MagicMock()
                mock_transcriber = MagicMock()
                mock_transcriber.transcribe.return_value = mock_transcript_result
                mock_aai.Transcriber.return_value = mock_transcriber
                mock_aai.TranscriptionConfig.return_value = MagicMock()
                mock_aai.TranscriptStatus.error = "error_sentinel"

                with patch.dict("sys.modules", {"assemblyai": mock_aai}):
                    result = pipeline.extract_testimony(
                        youtube_video_id="vid_ok",
                        speaker_count=10,
                        jurisdiction_id="city-san-rafael",
                        meeting_date="2026-03-15",
                        assemblyai_api_key="test-key",
                    )

        assert result is not None
        assert result["youtube_video_id"] == "vid_ok"
        assert result["jurisdiction_id"] == "city-san-rafael"
        assert result["meeting_date"] == "2026-03-15"
        assert result["transcript_id"] == "tx_full_123"
        assert result["speaker_count_estimated"] == 10
        assert result["status"] == "success"
        assert result["assemblyai_data"]["text"] == "Good evening. Motion carries."
        assert len(result["assemblyai_data"]["utterances"]) == 2
        assert result["assemblyai_data"]["utterances"][0]["speaker"] == "A"
        assert result["assemblyai_data"]["utterances"][1]["confidence"] == 0.90

    def test_returns_none_on_audio_download_failure(self, pipeline):
        with patch.object(pipeline, "_extract_youtube_transcript", return_value="text"):
            with patch.object(pipeline, "_download_youtube_audio", return_value=None):
                result = pipeline.extract_testimony(
                    youtube_video_id="vid_fail",
                    speaker_count=5,
                    jurisdiction_id="city-test",
                    meeting_date="2026-01-01",
                    assemblyai_api_key="key",
                )

        assert result is None
        assert len(pipeline.errors) == 1
        assert pipeline.errors[0]["operation"] == "assemblyai"

    def test_continues_when_youtube_transcript_fails(self, pipeline):
        """Pipeline should not abort when YouTube transcript is unavailable."""
        mock_transcript_result = self._make_mock_transcript_result()

        with patch.object(
            pipeline,
            "_extract_youtube_transcript",
            side_effect=YouTubeTranscriptError("IP blocked"),
        ):
            with patch.object(pipeline, "_download_youtube_audio", return_value="/tmp/vid.mp3"):
                mock_aai = MagicMock()
                mock_transcriber = MagicMock()
                mock_transcriber.transcribe.return_value = mock_transcript_result
                mock_aai.Transcriber.return_value = mock_transcriber
                mock_aai.TranscriptionConfig.return_value = MagicMock()
                mock_aai.TranscriptStatus.error = "error_sentinel"

                with patch.dict("sys.modules", {"assemblyai": mock_aai}):
                    result = pipeline.extract_testimony(
                        youtube_video_id="vid_no_yt",
                        speaker_count=5,
                        jurisdiction_id="city-test",
                        meeting_date="2026-02-01",
                        assemblyai_api_key="key",
                    )

        # Pipeline should still succeed
        assert result is not None
        assert result["status"] == "success"
        assert result["transcript_id"] == "tx_full_123"
        # No errors logged (YouTube transcript is optional)
        assert len(pipeline.errors) == 0

    def test_returns_none_on_assemblyai_import_error(self, pipeline):
        with patch.object(pipeline, "_extract_youtube_transcript", return_value="text"):
            with patch.object(pipeline, "_download_youtube_audio", return_value="/tmp/vid.mp3"):
                with patch.dict("sys.modules", {"assemblyai": None}):
                    result = pipeline.extract_testimony(
                        youtube_video_id="vid_no_sdk",
                        speaker_count=5,
                        jurisdiction_id="city-test",
                        meeting_date="2026-01-01",
                        assemblyai_api_key="key",
                    )

        assert result is None
        assert len(pipeline.errors) == 1
        assert "assemblyai" in pipeline.errors[0]["operation"]

    def test_returns_none_on_unexpected_exception(self, pipeline):
        with patch.object(
            pipeline,
            "_extract_youtube_transcript",
            side_effect=RuntimeError("totally unexpected"),
        ):
            # The outer try/except should catch non-YouTubeTranscriptError
            # BUT the inner try catches YouTubeTranscriptError specifically,
            # so RuntimeError will propagate to the outer handler
            result = pipeline.extract_testimony(
                youtube_video_id="vid_crash",
                speaker_count=5,
                jurisdiction_id="city-test",
                meeting_date="2026-01-01",
                assemblyai_api_key="key",
            )

        assert result is None
        assert len(pipeline.errors) == 1
        assert pipeline.errors[0]["error_type"] == "RuntimeError"
        assert pipeline.errors[0]["operation"] == "unknown"

    def test_assemblyai_data_structure_with_no_utterances(self, pipeline):
        """When AssemblyAI returns no utterances, assemblyai_data should have empty list."""
        mock_result = MagicMock()
        mock_result.id = "tx_no_utt"
        mock_result.status = MagicMock()
        mock_result.status.__eq__ = lambda self, other: False
        mock_result.text = "Some text"
        mock_result.utterances = None
        mock_result.error = None

        with patch.object(pipeline, "_extract_youtube_transcript", return_value="text"):
            with patch.object(pipeline, "_download_youtube_audio", return_value="/tmp/vid.mp3"):
                mock_aai = MagicMock()
                mock_transcriber = MagicMock()
                mock_transcriber.transcribe.return_value = mock_result
                mock_aai.Transcriber.return_value = mock_transcriber
                mock_aai.TranscriptionConfig.return_value = MagicMock()
                mock_aai.TranscriptStatus.error = "error_sentinel"

                with patch.dict("sys.modules", {"assemblyai": mock_aai}):
                    result = pipeline.extract_testimony(
                        youtube_video_id="vid_quiet",
                        speaker_count=2,
                        jurisdiction_id="city-test",
                        meeting_date="2026-01-15",
                        assemblyai_api_key="key",
                    )

        assert result is not None
        assert result["assemblyai_data"]["utterances"] == []
        assert result["assemblyai_data"]["text"] == "Some text"
        assert result["assemblyai_data"]["id"] == "tx_no_utt"
        assert result["assemblyai_data"]["status"] == "completed"


# ---------------------------------------------------------------------------
# Polling timeout
# ---------------------------------------------------------------------------


class TestPollTimeout:
    @patch("civicos_services.processing.testimony_extraction_pipeline.requests.get")
    @patch("civicos_services.processing.testimony_extraction_pipeline.time.sleep")
    def test_timeout_after_max_polls(self, mock_sleep, mock_get, pipeline):
        """Pipeline should raise after 60 polls without completion."""
        processing_resp = MagicMock()
        processing_resp.json.return_value = {"status": "processing"}
        processing_resp.raise_for_status = MagicMock()
        mock_get.return_value = processing_resp

        with pytest.raises(AssemblyAIError, match="did not complete after"):
            pipeline._poll_assemblyai_status("tx_slow", "test-key")

        assert mock_sleep.call_count == 60
