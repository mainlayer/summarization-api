# Summarization API

A production-ready text summarization service with pay-per-call billing via [Mainlayer](https://mainlayer.fr).

## Features

- **Three summarization endpoints**: text, batch, URL
- **Multiple output styles**: paragraph, bullet points, TL;DR
- **Pay-as-you-go pricing**: $0.002–$0.003 per call
- **Batch processing**: Summarize up to 20 texts per request
- **URL fetching**: Automatically extract and summarize web content
- **Structured logging** and error handling
- **Async/await** for high concurrency

## Pricing

| Endpoint | Cost | Use Case |
|----------|------|----------|
| `/summarize` | $0.002 | Single text summarization |
| `/summarize/batch` | $0.0015 | Batch multiple texts (1–20) |
| `/summarize/url` | $0.003 | Fetch and summarize URLs |
| `/models` | FREE | List available models |
| `/health` | FREE | Health check |

## 5-Minute Quickstart

### 1. Install dependencies

```bash
pip install -e ".[dev]"
```

### 2. Set environment variables

```bash
export MAINLAYER_API_KEY=your_api_key
export MAINLAYER_RESOURCE_ID=your_resource_id
export MAINLAYER_DEV_MODE=true  # Skip billing during development
export LOG_LEVEL=INFO
```

### 3. Start the server

```bash
uvicorn src.main:app --reload --port 8000
```

Server runs at `http://localhost:8000`

### 4. Test a summarization request

**Paragraph style (default)**:
```bash
curl -X POST http://localhost:8000/summarize \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Artificial intelligence is transforming industries worldwide. From healthcare to finance, AI systems are improving efficiency, accuracy, and decision-making. However, there are concerns about bias, privacy, and job displacement. Responsible AI development requires collaboration between technologists, policymakers, and ethicists.",
    "max_length": 50,
    "style": "paragraph"
  }'
```

**Bullet points**:
```bash
curl -X POST http://localhost:8000/summarize \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Your long text here...",
    "max_length": 100,
    "style": "bullet"
  }'
```

**TL;DR**:
```bash
curl -X POST http://localhost:8000/summarize \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Your long text here...",
    "max_length": 30,
    "style": "tldr"
  }'
```

### 5. With production billing

Add the `X-Mainlayer-Token` header:
```bash
curl -X POST http://localhost:8000/summarize \
  -H "Content-Type: application/json" \
  -H "X-Mainlayer-Token: your_payment_token" \
  -d '{
    "text": "Your long text here...",
    "max_length": 100,
    "style": "paragraph"
  }'
```

## API Reference

### `POST /summarize`

Summarize a single text block.

**Request Body**:
```json
{
  "text": "string (required, min 10 chars)",
  "max_length": 150,
  "style": "paragraph | bullet | tldr"
}
```

**Response**:
```json
{
  "summary": "string",
  "word_count": 42,
  "compression_ratio": 0.35
}
```

**Cost**: $0.002

---

### `POST /summarize/batch`

Summarize multiple texts in one request (1–20 items).

**Request Body**:
```json
{
  "items": [
    {
      "text": "string",
      "max_length": 100,
      "style": "paragraph"
    }
  ]
}
```

**Response**:
```json
{
  "results": [
    {
      "index": 0,
      "summary": "string",
      "word_count": 42,
      "compression_ratio": 0.35
    }
  ],
  "total_items": 1
}
```

**Cost**: $0.0015 (flat rate for any batch size)

---

### `POST /summarize/url`

Fetch a URL and summarize its text content.

**Request Body**:
```json
{
  "url": "https://example.com/article",
  "max_length": 150,
  "style": "paragraph"
}
```

**Response**:
```json
{
  "summary": "string",
  "word_count": 42,
  "compression_ratio": 0.35
}
```

**Cost**: $0.003

---

### `GET /models`

List available summarization models (FREE).

**Response**:
```json
{
  "models": [
    {
      "id": "extractive-v1",
      "name": "Extractive Summarizer v1",
      "description": "...",
      "max_input_tokens": 4096,
      "supported_styles": ["bullet", "paragraph", "tldr"]
    }
  ],
  "default_model": "extractive-v1"
}
```

---

### `GET /health`

Health check endpoint (FREE).

**Response**:
```json
{
  "status": "ok"
}
```

---

## Summary Styles

### Paragraph (default)
Extracts key sentences and joins them into flowing prose.

**Input**: "Artificial intelligence is transforming industries. From healthcare to finance, AI systems are improving efficiency. However, there are concerns about bias and job displacement."

**Output**: "Artificial intelligence is transforming industries from healthcare to finance. However, there are concerns about bias and job displacement."

### Bullet
Each key sentence becomes a bullet point.

**Output**:
```
- Artificial intelligence is transforming industries.
- AI systems are improving efficiency.
- There are concerns about bias and job displacement.
```

### TL;DR
A single compact sentence prefixed with "TL;DR:".

**Output**: "TL;DR: AI is transforming industries but raises concerns about bias and job displacement."

---

## Status Codes

| Code | Meaning | Trigger |
|------|---------|---------|
| 200 | Success | Summarization succeeded |
| 402 | Payment Required | Missing or invalid Mainlayer token |
| 422 | Unprocessable Entity | Invalid input format or too short text |
| 500 | Server Error | Summarization engine failed |
| 503 | Service Unavailable | Billing service (Mainlayer) unavailable |

---

## Development

### Running tests

```bash
pytest tests/ -v
```

### Linting and formatting

```bash
black src/ tests/
mypy src/
```

### Docker deployment

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml .
RUN pip install -e .
COPY src/ src/
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0"]
```

---

## Production Checklist

- [ ] Replace in-memory quota tracking with Redis/PostgreSQL
- [ ] Add Prometheus metrics (requests, latency, tier distribution)
- [ ] Enable HTTPS and CORS
- [ ] Configure centralized logging (ELK, Datadog, etc.)
- [ ] Set up monitoring and alerting
- [ ] Test billing integration with live Mainlayer account
- [ ] Set up rate limiting for paid tier
- [ ] Use a production-grade ASGI server (e.g., Gunicorn)
- [ ] Configure horizontal scaling (Kubernetes, auto-scaling)

---

## Architecture

### Request Flow

1. Client sends text with payment token
2. API verifies payment via Mainlayer
3. Summarizer extracts key sentences using TF-based scoring
4. Summary formatted into requested style
5. Usage recorded for billing
6. Response returned with compression ratio

### Summarization Algorithm

The template uses **extractive summarization**:
1. Split text into sentences
2. Score sentences by word frequency (TF-IDF style)
3. Select highest-scoring sentences up to `max_length` words
4. Return in original document order
5. Format into requested style (paragraph, bullet, TL;DR)

For production, integrate a real summarization model:
- OpenAI API (GPT-4)
- Hugging Face Transformers (BART, T5, Pegasus)
- Local LLM (Llama, Mistral)

---

## Support

- Docs: https://docs.mainlayer.fr
- Issues: https://github.com/mainlayer/summarization-api/issues
