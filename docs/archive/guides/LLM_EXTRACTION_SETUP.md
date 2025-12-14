# LLM Testimony Extraction - Setup Guide

## What Was Added

The Modal script now includes **optional LLM post-processing** to extract structured testimony data.

### Without LLM (Raw Diarization):
```json
{
  "video_id": "abc123",
  "speakers_count": 8,
  "utterances": [
    {"speaker": "SPEAKER_0", "text": "I support this proposal...", "start": 1500, "end": 3000},
    {"speaker": "SPEAKER_1", "text": "As a member of...", "start": 3500, "end": 5000}
  ]
}
```

### With LLM (Structured Testimony):
```json
{
  "video_id": "abc123",
  "speakers_count": 8,
  "llm_processed": true,
  "testimony_records": [
    {
      "speaker_label": "SPEAKER_0",
      "speaker_name": "Jane Smith",
      "organization": "Marin Conservation League",
      "position": "support",
      "topic": "wildfire prevention funding",
      "key_quote": "I strongly support the allocation of $1.1M...",
      "confidence": "high"
    }
  ],
  "utterances": [...]  // Raw transcript still included
}
```

---

## Setup (One-Time)

### 1. Create OpenAI API Secret

```bash
# Get your OpenAI API key from: https://platform.openai.com/api-keys
modal secret create openai-secret OPENAI_API_KEY=sk-your-actual-key-here
```

### 2. That's It!

The OpenAI library is already included in the Modal image definition.

---

## Usage

### Test Single Meeting (With LLM)

```bash
modal run scripts/modal_youtube_testimony.py::test_single
```

**Time**: ~13 minutes
**Cost**: ~$0.24 ($0.22 GPU + $0.02 LLM)

### Test Single Meeting (Without LLM)

```bash
modal run scripts/modal_youtube_testimony.py::test_single --enable-llm=false
```

**Time**: ~12 minutes
**Cost**: ~$0.22 (GPU only)

### Batch Processing (25 meetings)

```bash
# With LLM extraction (recommended)
modal run scripts/modal_youtube_testimony.py::run_batch \
  --urls-file data/san_rafael_meetings.txt

# Without LLM (faster, cheaper)
modal run scripts/modal_youtube_testimony.py::run_batch \
  --urls-file data/san_rafael_meetings.txt \
  --enable-llm=false
```

---

## Cost Breakdown (Per Meeting)

| Component | Time | Cost | Model |
|-----------|------|------|-------|
| GPU (diarization) | ~12 min | $0.22 | A10G GPU |
| LLM (extraction) | ~30 sec | $0.01-0.02 | gpt-4o-mini |
| **Total with LLM** | **~13 min** | **~$0.24** | Combined |

### For 25 Meetings:
- **Time**: 1 hour (5x parallel)
- **Cost**: 25 × $0.24 = **$6.00**

---

## What the LLM Extracts

For each speaker in the transcript:

1. **Speaker Name** - Extracted if mentioned ("I'm Jane Smith...")
2. **Organization** - Found if stated ("representing Marin Conservation League...")
3. **Position** - Inferred from content:
   - `support` - Clearly in favor
   - `oppose` - Clearly against
   - `neutral` - Presenting information
   - `unclear` - Can't determine
4. **Topic** - Main subject discussed
5. **Key Quote** - Most impactful statement
6. **Confidence** - How certain the extraction is (high/medium/low)

---

## LLM Model Details

**Default Model**: `gpt-4o-mini`
- **Speed**: Fast (~30 seconds per meeting)
- **Cost**: Cheap (~$0.01-0.02 per meeting)
- **Quality**: Good for name/org extraction

**To Use Better Model** (edit `scripts/modal_youtube_testimony.py:339`):
```python
model="gpt-4o",  # Better quality, ~$0.05/meeting, ~2-3 min
```

---

## Error Handling

If LLM extraction fails:
- Script continues and saves raw transcript
- Error logged in `llm_error` field
- Still get diarized transcript with speaker labels
- Can re-run LLM extraction later locally

---

## When to Skip LLM

**Skip LLM extraction if:**
- Just want transcript archive (don't need structure)
- Experimenting with diarization quality
- Want to try different LLM prompts locally first

**Use LLM extraction if:**
- Need speaker names/organizations
- Want to analyze positions (support/oppose)
- Building testimony database
- Running full retrospective analysis

---

## Future Enhancements

Possible improvements:
1. **Better prompts** - More context-aware extraction
2. **Speaker linking** - Connect speakers across meetings
3. **Topic clustering** - Group testimony by themes
4. **Sentiment analysis** - Beyond support/oppose
5. **Quote quality** - Rank quotes by impact

---

## Troubleshooting

### "Secret not found: openai-secret"
```bash
modal secret create openai-secret OPENAI_API_KEY=sk-...
```

### "OpenAI API error: Insufficient quota"
- Check your OpenAI billing: https://platform.openai.com/usage
- Add payment method if needed
- Or skip LLM: `--enable-llm=false`

### LLM extraction returns empty records
- Check transcript quality (poor audio = poor transcription = poor extraction)
- Try with a clearer meeting recording first
- Review LLM prompt in `modal_youtube_testimony.py:310-335`

---

## Next Steps

1. **Test single meeting** with LLM to validate quality
2. **Review structured output** - check if names/orgs extracted correctly
3. **Adjust prompts** if needed (edit function at line 310)
4. **Run full batch** once satisfied with quality

**Ready to test?**
```bash
modal run scripts/modal_youtube_testimony.py::test_single
```
