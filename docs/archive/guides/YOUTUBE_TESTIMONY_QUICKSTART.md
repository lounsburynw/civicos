# YouTube Testimony Extraction - Quick Start (WhisperX Edition!)

## ✅ What's Ready

- ✅ POC script created: `scripts/extract_youtube_testimony_poc.py`
- ✅ Dependencies installed: `yt-dlp`, `whisperx`, `ffmpeg`
- ✅ Documentation complete: `docs/pilot/YOUTUBE_TESTIMONY_EXTRACTION.md`

## 🚀 Next Steps (5 minutes to test!)

### 1. Install WhisperX (1 minute)

```bash
source civic-env/bin/activate
pip install whisperx
```

### 2. Get Hugging Face Token (2 minutes - FREE!)

Visit: https://huggingface.co/settings/tokens

- Create account (free, no credit card)
- Click "New token" → Select "Read" access
- Copy your token

**Accept model terms** (required for diarization):
- Visit: https://huggingface.co/pyannote/segmentation
- Click "Agree and access repository"
- Visit: https://huggingface.co/pyannote/speaker-diarization-3.1
- Click "Agree and access repository"

### 3. Set Token

```bash
export HF_TOKEN="paste_your_token_here"
```

### 4. Run POC on Oct 6 Wildfire Meeting (5-10 minutes)

```bash
# Activate environment
source civic-env/bin/activate

# Run POC (will auto-detect Apple Silicon GPU!)
python scripts/extract_youtube_testimony_poc.py \
  "https://www.cityofsanrafael.org/meetings/city-council-october-6-2024/"
```

**What happens**:
1. Extracts YouTube video ID from page (~1 sec)
2. Downloads audio as MP3 (~30 sec)
3. Downloads Whisper model first time (~2 GB, 2-3 min)
4. Transcribes with Whisper (~2-4 min on Apple Silicon)
5. Speaker diarization (~1-2 min)
6. Extracts testimony structure with LLM (~30 sec)
7. Displays results + saves JSON

**Expected output**:
- ~8 speakers identified
- Full testimony quotes
- Speaker positions (support/oppose)
- Timestamps for each speaker

**Cost**: $0 (completely free!)

### 4. Review Results

Check the saved JSON:
```bash
cat data/pilot/youtube_testimony_*.json | jq .
```

Compare to video:
```bash
# The script will show the YouTube URL
# Watch it to validate speaker count and accuracy
```

## 📊 What You'll Get

**vs Legistar API** (names only):
- ✅ Full testimony quotes
- ✅ Speaker positions (support/oppose)
- ✅ Organization mentions
- ✅ Timestamps
- ✅ 100% coverage (every meeting has video)

**Cost for all 25 meetings**: $0 (completely free with WhisperX!)

## 💡 Why WhisperX?

- **🆓 Free** - No API costs, runs locally
- **🔒 Private** - Audio never leaves your machine
- **⚡ Fast** - Apple Silicon GPU acceleration
- **🎯 Accurate** - State-of-the-art Whisper + pyannote diarization
- **📦 Self-contained** - No cloud dependencies

**First run is slower** (~10 min) due to model downloads, but subsequent runs are fast (~3-4 min per 2-hour meeting).

## 🎯 Success Criteria

After running the POC, validate:
- [ ] Speaker count matches video (±2 speakers acceptable)
- [ ] Testimony quotes are accurate
- [ ] Speaker attribution is consistent
- [ ] Positions (support/oppose) make sense

If POC looks good → proceed with batch processing all 25 meetings!

## 📚 Documentation

- **Full guide**: `docs/pilot/YOUTUBE_TESTIMONY_EXTRACTION.md`
- **Setup guide**: `docs/pilot/YOUTUBE_TESTIMONY_SETUP.md`
- **Session 104 summary**: `docs/pilot/TESTIMONY_ENRICHMENT.md`

## ❓ Troubleshooting

**"No YouTube video found"**
- Meeting may not have video yet
- Try a more recent meeting (2025 meetings are more likely to have videos)

**"whisperx not installed"**
```bash
pip install whisperx
```

**"FFmpeg not found"**
- Already installed! (`/opt/homebrew/bin/ffmpeg`)

**"Model download fails" or "Out of memory"**
- First run downloads ~2GB of models
- Requires ~8GB RAM for large-v2 model
- Try smaller model: edit script to use "base" or "medium" instead of "large-v2"

**"Transcription too slow"**
- First run: 10+ minutes (downloading models)
- Subsequent runs: 3-4 minutes (models cached)
- CPU-only: Add `--device cpu` (slower but works)

## 🔄 Alternative: AssemblyAI (Cloud)

If WhisperX doesn't work on your machine, use AssemblyAI:

```bash
# Get API key from https://www.assemblyai.com/ ($50 free credits)
export ASSEMBLYAI_API_KEY="your_key"

# Force AssemblyAI method
python scripts/extract_youtube_testimony_poc.py \
  --method assemblyai \
  "https://www.cityofsanrafael.org/meetings/city-council-october-6-2024/"
```

**Trade-offs**:
- ✅ Faster (cloud processing)
- ✅ No local resources needed
- ❌ Costs $0.74 per 2-hour meeting
- ❌ Audio uploaded to cloud

## 🚀 After POC Success

1. Create batch processing script for all 25 meetings
2. Insert testimony into database
3. Run coalition discovery queries
4. Integrate with vector search (Session 105)

---

**Ready to test?** Just need your AssemblyAI API key!
