"""
Mock summarization engine.

Produces deterministic, realistic-looking summaries by extracting key
sentences, trimming to max_length words, and reformatting into the
requested style.  No external model calls are made — this is intentional
for a template / demo service.
"""
import re
import textwrap
from src.models import SummaryStyle


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _word_count(text: str) -> int:
    return len(text.split())


def _sentence_split(text: str) -> list[str]:
    """Split text into sentences using a simple regex."""
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    return [s.strip() for s in sentences if s.strip()]


def _score_sentence(sentence: str, word_freq: dict[str, int]) -> float:
    """Score a sentence by the frequency of its words (TF-style heuristic)."""
    words = re.findall(r"\b\w+\b", sentence.lower())
    if not words:
        return 0.0
    return sum(word_freq.get(w, 0) for w in words) / len(words)


def _word_frequencies(text: str) -> dict[str, int]:
    """Return word frequencies, ignoring common stop words."""
    stop_words = {
        "the", "a", "an", "and", "or", "but", "in", "on", "at", "to",
        "for", "of", "with", "by", "from", "is", "are", "was", "were",
        "be", "been", "being", "have", "has", "had", "do", "does", "did",
        "will", "would", "could", "should", "may", "might", "must", "can",
        "this", "that", "these", "those", "it", "its", "i", "you", "he",
        "she", "we", "they", "not", "no", "so", "as", "if", "up", "out",
        "about", "into", "than", "then", "also", "more", "such", "how",
    }
    words = re.findall(r"\b\w+\b", text.lower())
    freq: dict[str, int] = {}
    for w in words:
        if w not in stop_words and len(w) > 2:
            freq[w] = freq.get(w, 0) + 1
    return freq


def _extract_key_sentences(text: str, max_words: int) -> list[str]:
    """Return the highest-scoring sentences that fit within max_words."""
    sentences = _sentence_split(text)
    if not sentences:
        return []

    freq = _word_frequencies(text)
    scored = sorted(
        enumerate(sentences),
        key=lambda t: _score_sentence(t[1], freq),
        reverse=True,
    )

    selected_indices: list[int] = []
    running_words = 0
    for idx, sentence in scored:
        wc = _word_count(sentence)
        if running_words + wc > max_words:
            # Try a shorter sentence first
            continue
        selected_indices.append(idx)
        running_words += wc
        if running_words >= max_words * 0.85:
            break

    # If nothing fit, force at least the first (highest-scored) sentence,
    # truncated to max_words.
    if not selected_indices:
        top_sentence = scored[0][1]
        truncated = " ".join(top_sentence.split()[:max_words])
        return [truncated]

    # Return in original document order
    selected_indices.sort()
    return [sentences[i] for i in selected_indices]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def summarize(text: str, max_length: int, style: SummaryStyle) -> str:
    """
    Summarize *text* to at most *max_length* words in the given *style*.

    Styles
    ------
    paragraph  — flowing prose, sentences joined together.
    bullet     — each key sentence becomes a bullet point.
    tldr       — a single compact sentence prefixed with "TL;DR:".
    """
    original_words = _word_count(text)

    if style == SummaryStyle.tldr:
        # For TL;DR we want just 1–2 key sentences, very short.
        effective_max = min(max_length, 40)
        key_sentences = _extract_key_sentences(text, effective_max)
        combined = " ".join(key_sentences)
        words = combined.split()[:effective_max]
        summary = "TL;DR: " + " ".join(words)
        if not summary.endswith((".", "!", "?")):
            summary = summary.rstrip(",;:") + "."
        return summary

    if style == SummaryStyle.bullet:
        key_sentences = _extract_key_sentences(text, max_length)
        bullet_lines = [f"- {s}" for s in key_sentences]
        return "\n".join(bullet_lines)

    # Default: paragraph
    key_sentences = _extract_key_sentences(text, max_length)
    summary = " ".join(key_sentences)
    # Hard-cap word count
    words = summary.split()[:max_length]
    summary = " ".join(words)
    if summary and not summary.endswith((".", "!", "?")):
        summary = summary.rstrip(",;:") + "."
    return summary


def compute_compression_ratio(original_text: str, summary: str) -> float:
    """Return summary_words / original_words, clamped to [0, 1]."""
    original_wc = _word_count(original_text)
    summary_wc = _word_count(summary)
    if original_wc == 0:
        return 0.0
    ratio = summary_wc / original_wc
    return round(min(ratio, 1.0), 4)
