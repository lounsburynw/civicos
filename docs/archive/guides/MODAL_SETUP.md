# Modal Setup Guide - YouTube Testimony Extraction

## Quick Start (5 minutes)

### 1. Install Modal

```bash
source civic-env/bin/activate
pip install modal
```

### 2. Authenticate with Modal

```bash
# Creates free account + API token
modal token new
```

This will:
- Create a free Modal account (no credit card required!)
- Open browser for authentication
- Save credentials locally

### 3. Set Up HuggingFace Secret

```bash
# Replace with your actual HF token
modal secret create huggingface HF_TOKEN=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
```

### 4. Test with Single Meeting

```bash
# Test on March 3, 2025 meeting (~12 min, ~$0.22 cost)
modal run scripts/modal_youtube_testimony.py::test_single
```

### 5. Run Full Batch (25 meetings)

First, create a file with all meeting URLs:

```bash
# Create URLs file
cat > data/san_rafael_meetings.txt << 'EOF'
https://www.cityofsanrafael.org/meetings/city-council-march-03-2025/
https://www.cityofsanrafael.org/meetings/city-council-march-17-2025/
# ... add more URLs
EOF
```

Then run batch processing:

```bash
# Process all meetings in parallel (~1 hour, ~$5.50 total)
modal run scripts/modal_youtube_testimony.py::run_batch --urls-file data/san_rafael_meetings.txt
```

---

## How It Works

### Architecture

```
Local Machine                    Modal Cloud (A10G GPUs)
─────────────                    ───────────────────────
modal CLI       ─────────────>   5x parallel workers
                                        │
                                        ├─> Meeting 1  (12 min)
                                        ├─> Meeting 2  (12 min)
                                        ├─> Meeting 3  (12 min)
                                        ├─> Meeting 4  (12 min)
                                        └─> Meeting 5  (12 min)
                                              │
                                              v
results.json    <─────────────   JSON results streamed back
```

### Cost Breakdown

| Item | Cost | Notes |
|------|------|-------|
| **Per meeting** | $0.22 | ~12 min × $1.10/hour (A10G GPU) |
| **1 meeting** | $0.22 | Test single meeting |
| **5 meetings** | $1.10 | Good for testing |
| **25 meetings** | $5.50 | Full San Rafael retrospective |
| **100 meetings** | $22.00 | Multi-city scale |

### Time Comparison

| Meetings | Local (Sequential) | Modal (5x Parallel) | Modal (25x Parallel) |
|----------|-------------------|---------------------|----------------------|
| 1        | 20-30 min         | 12 min              | 12 min               |
| 5        | 1.5-2.5 hours     | 12 min              | 12 min               |
| 25       | 7-10 hours        | **1 hour**          | **12 min**           |
| 100      | 30-40 hours       | 4 hours             | 48 min               |

---

## Modal Features We're Using

### 1. **Serverless GPUs**
- No infrastructure management
- Pay-per-second billing (not per hour!)
- Auto-scales to handle parallelism

### 2. **Container Images**
- Declarative dependency management
- Cached between runs (fast startup)
- Reproducible environments

### 3. **Secrets Management**
- Encrypted HuggingFace token storage
- Automatic injection into functions
- No tokens in code/logs

### 4. **Parallel Execution**
- `.map()` for automatic parallelization
- Automatic load balancing
- Retry on failures

### 5. **Cost Optimization**
- Only pay for actual GPU seconds used
- No idle time charges
- Automatic container shutdown

---

## Troubleshooting

### "Modal not authenticated"
```bash
modal token new
```

### "Secret not found: huggingface"
```bash
modal secret create huggingface HF_TOKEN=your_token_here
```

### "CUDA out of memory"
- Reduce `batch_size` in whisperx.load_model (line 171)
- Or switch to T4 GPU (cheaper but slower):
  ```python
  @app.function(gpu="T4", ...)  # $0.59/hour vs $1.10/hour
  ```

### Check costs in real-time
```bash
modal app logs civic-testimony-extraction
```

Or visit: https://modal.com/billing

---

## Advanced Usage

### Process specific meetings

```bash
# Direct URLs (no file needed)
modal run scripts/modal_youtube_testimony.py::run_batch \
  --urls \
  "https://www.cityofsanrafael.org/meetings/city-council-march-03-2025/" \
  "https://www.cityofsanrafael.org/meetings/city-council-march-17-2025/"
```

### Increase parallelism

Edit `scripts/modal_youtube_testimony.py` line 261:

```python
def process_batch(meeting_urls: List[str], max_parallel: int = 10):  # Changed from 5 to 10
```

Higher parallelism = faster results, same total cost (just more GPUs running simultaneously).

---

## Next Steps

1. **Test locally first** - Make sure `extract_youtube_testimony_poc.py` works on your machine
2. **Test Modal with 1 meeting** - Verify cloud setup works
3. **Run small batch (5 meetings)** - Validate parallel processing
4. **Run full batch (25 meetings)** - Complete retrospective analysis

## Free Tier

Modal offers a generous free tier:
- $30/month in free credits
- Enough for ~130 meetings per month
- Perfect for testing and small-scale usage

For production (26 cities × 25 meetings = 650/month), you'd need ~$143/month in credits.
