"""
Tests for the summarization API.

Run with:
    pytest tests/test_api.py -v

All tests run with MAINLAYER_DEV_MODE=true so no real billing calls are made.
"""
import os
import pytest
from fastapi.testclient import TestClient

# Force dev mode before importing the app
os.environ["MAINLAYER_DEV_MODE"] = "true"

from src.main import app  # noqa: E402

client = TestClient(app)

LONG_TEXT = (
    "Artificial intelligence is transforming industries at an unprecedented pace. "
    "Machine learning models can now perform tasks that once required human expertise, "
    "from diagnosing medical conditions to composing music and generating code. "
    "Natural language processing has enabled computers to understand and generate "
    "human language with remarkable fluency. Deep learning, a subset of machine "
    "learning, uses neural networks with many layers to learn complex patterns in data. "
    "The rise of large language models has democratised access to powerful AI capabilities. "
    "Businesses are integrating AI into their workflows to automate repetitive tasks, "
    "personalise customer experiences, and gain insights from vast datasets. "
    "Despite impressive progress, significant challenges remain around bias, "
    "interpretability, energy consumption, and the societal impact of automation."
)

SHORT_TEXT = "The quick brown fox jumps over the lazy dog."


# ---------------------------------------------------------------------------
# Health and meta
# ---------------------------------------------------------------------------

class TestHealth:
    def test_health_returns_200(self):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


class TestModels:
    def test_list_models_returns_200(self):
        response = client.get("/models")
        assert response.status_code == 200

    def test_list_models_has_expected_fields(self):
        data = client.get("/models").json()
        assert "models" in data
        assert "default_model" in data
        assert isinstance(data["models"], list)
        assert len(data["models"]) > 0

    def test_each_model_has_required_fields(self):
        models = client.get("/models").json()["models"]
        for model in models:
            assert "id" in model
            assert "name" in model
            assert "description" in model
            assert "max_input_tokens" in model
            assert "supported_styles" in model


# ---------------------------------------------------------------------------
# POST /summarize
# ---------------------------------------------------------------------------

class TestSummarize:
    def test_basic_summarize_paragraph(self):
        response = client.post(
            "/summarize",
            json={"text": LONG_TEXT, "max_length": 80, "style": "paragraph"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "summary" in data
        assert "word_count" in data
        assert "compression_ratio" in data
        assert isinstance(data["summary"], str)
        assert len(data["summary"]) > 0

    def test_bullet_style_has_bullets(self):
        response = client.post(
            "/summarize",
            json={"text": LONG_TEXT, "max_length": 100, "style": "bullet"},
        )
        assert response.status_code == 200
        summary = response.json()["summary"]
        assert "-" in summary

    def test_tldr_style_starts_with_prefix(self):
        response = client.post(
            "/summarize",
            json={"text": LONG_TEXT, "max_length": 50, "style": "tldr"},
        )
        assert response.status_code == 200
        summary = response.json()["summary"]
        assert summary.startswith("TL;DR:")

    def test_word_count_matches_summary(self):
        response = client.post(
            "/summarize",
            json={"text": LONG_TEXT, "max_length": 60, "style": "paragraph"},
        )
        assert response.status_code == 200
        data = response.json()
        reported_wc = data["word_count"]
        actual_wc = len(data["summary"].split())
        assert reported_wc == actual_wc

    def test_compression_ratio_between_0_and_1(self):
        response = client.post(
            "/summarize",
            json={"text": LONG_TEXT, "max_length": 50, "style": "paragraph"},
        )
        assert response.status_code == 200
        ratio = response.json()["compression_ratio"]
        assert 0.0 <= ratio <= 1.0

    def test_default_style_is_paragraph(self):
        response = client.post(
            "/summarize",
            json={"text": LONG_TEXT, "max_length": 80},
        )
        assert response.status_code == 200

    def test_short_text_summarizes(self):
        response = client.post(
            "/summarize",
            json={"text": SHORT_TEXT, "max_length": 20, "style": "paragraph"},
        )
        assert response.status_code == 200
        assert len(response.json()["summary"]) > 0

    def test_invalid_style_returns_422(self):
        response = client.post(
            "/summarize",
            json={"text": LONG_TEXT, "max_length": 80, "style": "haiku"},
        )
        assert response.status_code == 422

    def test_empty_text_returns_422(self):
        response = client.post(
            "/summarize",
            json={"text": "", "max_length": 80},
        )
        assert response.status_code == 422

    def test_blank_text_returns_422(self):
        response = client.post(
            "/summarize",
            json={"text": "   ", "max_length": 80},
        )
        assert response.status_code == 422

    def test_max_length_too_small_returns_422(self):
        response = client.post(
            "/summarize",
            json={"text": LONG_TEXT, "max_length": 5},
        )
        assert response.status_code == 422

    def test_max_length_too_large_returns_422(self):
        response = client.post(
            "/summarize",
            json={"text": LONG_TEXT, "max_length": 9999},
        )
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# POST /summarize/batch
# ---------------------------------------------------------------------------

class TestBatchSummarize:
    def _make_item(self, text: str = LONG_TEXT, style: str = "paragraph"):
        return {"text": text, "max_length": 60, "style": style}

    def test_batch_single_item(self):
        response = client.post(
            "/summarize/batch",
            json={"items": [self._make_item()]},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total_items"] == 1
        assert len(data["results"]) == 1

    def test_batch_multiple_items(self):
        items = [
            self._make_item(LONG_TEXT, "paragraph"),
            self._make_item(SHORT_TEXT, "bullet"),
            self._make_item(LONG_TEXT, "tldr"),
        ]
        response = client.post("/summarize/batch", json={"items": items})
        assert response.status_code == 200
        data = response.json()
        assert data["total_items"] == 3
        assert len(data["results"]) == 3

    def test_batch_result_indices_match(self):
        items = [self._make_item(), self._make_item(), self._make_item()]
        data = client.post("/summarize/batch", json={"items": items}).json()
        for i, result in enumerate(data["results"]):
            assert result["index"] == i

    def test_batch_empty_items_returns_422(self):
        response = client.post("/summarize/batch", json={"items": []})
        assert response.status_code == 422

    def test_batch_too_many_items_returns_422(self):
        items = [self._make_item() for _ in range(21)]
        response = client.post("/summarize/batch", json={"items": items})
        assert response.status_code == 422

    def test_batch_result_has_required_fields(self):
        data = client.post(
            "/summarize/batch",
            json={"items": [self._make_item()]},
        ).json()
        result = data["results"][0]
        assert "index" in result
        assert "summary" in result
        assert "word_count" in result
        assert "compression_ratio" in result


# ---------------------------------------------------------------------------
# POST /summarize/url
# ---------------------------------------------------------------------------

class TestSummarizeURL:
    def test_invalid_url_scheme_returns_422(self):
        response = client.post(
            "/summarize/url",
            json={"url": "ftp://example.com/page", "max_length": 80},
        )
        assert response.status_code == 422

    def test_missing_url_returns_422(self):
        response = client.post(
            "/summarize/url",
            json={"max_length": 80},
        )
        assert response.status_code == 422

    def test_non_http_url_returns_422(self):
        response = client.post(
            "/summarize/url",
            json={"url": "not-a-url", "max_length": 80},
        )
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Billing gate — verify payment is checked when dev mode is OFF
# ---------------------------------------------------------------------------

class TestBillingGate:
    """These tests patch DEV_MODE off to verify the 402 logic works."""

    def test_missing_token_returns_402_when_billing_enabled(self, monkeypatch):
        import src.mainlayer as ml
        monkeypatch.setattr(ml, "DEV_MODE", False)
        monkeypatch.setattr(ml, "MAINLAYER_API_KEY", "test-key")

        # We can't easily hit the live API in tests, but we can at least
        # confirm that with no token and DEV_MODE=False we'd get 402.
        # Since _call_mainlayer would fail without a real server, we mock it.
        import unittest.mock as mock

        async def fake_call(method, path, payload):
            return {"valid": False, "message": "No token provided"}

        with mock.patch.object(ml, "_call_mainlayer", side_effect=fake_call):
            response = client.post(
                "/summarize",
                json={"text": LONG_TEXT, "max_length": 80},
                # No X-Mainlayer-Token header
            )
        assert response.status_code == 402

    def test_dev_mode_skips_billing(self, monkeypatch):
        import src.mainlayer as ml
        monkeypatch.setattr(ml, "DEV_MODE", True)

        response = client.post(
            "/summarize",
            json={"text": LONG_TEXT, "max_length": 80},
        )
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# Summarizer unit tests
# ---------------------------------------------------------------------------

class TestSummarizerUnit:
    def test_paragraph_output_is_string(self):
        from src.summarizer import summarize
        from src.models import SummaryStyle
        result = summarize(LONG_TEXT, 80, SummaryStyle.paragraph)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_bullet_output_contains_dash(self):
        from src.summarizer import summarize
        from src.models import SummaryStyle
        result = summarize(LONG_TEXT, 100, SummaryStyle.bullet)
        assert "-" in result

    def test_tldr_output_starts_correctly(self):
        from src.summarizer import summarize
        from src.models import SummaryStyle
        result = summarize(LONG_TEXT, 50, SummaryStyle.tldr)
        assert result.startswith("TL;DR:")

    def test_compression_ratio_is_positive(self):
        from src.summarizer import compute_compression_ratio
        ratio = compute_compression_ratio(LONG_TEXT, "Short summary here.")
        assert ratio > 0.0
        assert ratio <= 1.0

    def test_compression_ratio_empty_original(self):
        from src.summarizer import compute_compression_ratio
        ratio = compute_compression_ratio("", "Summary.")
        assert ratio == 0.0
