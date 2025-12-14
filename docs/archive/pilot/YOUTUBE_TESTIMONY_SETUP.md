# YouTube Testimony Extraction - Setup Guide

Quick start guide for extracting testimony from San Rafael YouTube videos.

---

## Prerequisites

### 1. Install Dependencies

```bash
# Activate virtual environment
cd /Users/nicolaslounsbury/projects/civic
source civic-env/bin/activate

# Install required packages
pip install yt-dlp assemblyai beautifulsoup4

# Verify FFmpeg is installed (required by yt-dlp)
ffmpeg -version
```

If FFmpeg is not installed:
```bash
# macOS
brew install ffmpeg

# Linux
sudo apt-get install ffmpeg
```

### 2. Get AssemblyAI API Key

**Free tier**: $50 in credits (~135 hours of transcription)

1. Visit: https://www.assemblyai.com/
2. Click "Start building for free"
3. Sign up (no credit card required)
4. Go to dashboard: https://www.assemblyai.com/app
5. Copy your API key

### 3. Set API Key

Option 1 - Environment variable (recommended):
```bash
export ASSEMBLYAI_API_KEY="your_api_key_here"
```

Option 2 - Add to .env file:
```bash
echo "ASSEMBLYAI_API_KEY=your_api_key_here" >> .env
```

Option 3 - Pass as argument:
```bash
python scripts/extract_youtube_testimony_poc.py URL --api-key your_key
```

---

## Running the POC

### Test on Oct 6 Wildfire Meeting

```bash
# Activate environment
source civic-env/bin/activate

# Set API key
export ASSEMBLYAI_API_KEY="your_key"

# Run POC
python scripts/extract_youtube_testimony_poc.py \
  "https://www.cityofsanrafael.org/meetings/city-council-october-6-2024/"
```

### Expected Output

```
🎬 YOUTUBE TESTIMONY EXTRACTION - POC
======================================================================
🔍 Extracting video ID from URL...
✅ Found video ID via iframe: abc123xyz

📥 Downloading audio for video abc123xyz...
✅ Downloaded audio: /tmp/abc123xyz.mp3
   Duration: 120 minutes
   Size: 56.2 MB

🎙️  Transcribing with AssemblyAI...
   Uploading audio file...
   Transcription status: completed
✅ Transcription complete!
   Total utterances: 342
   Unique speakers: 8
   Duration: 120.3 minutes

🤖 Extracting testimony structure with LLM...
   Using model: gpt-4o-mini
✅ Extracted 8 testimony records

======================================================================
📊 EXTRACTION RESULTS
======================================================================

🎥 Video: https://www.youtube.com/watch?v=abc123xyz
⏱️  Duration: 120.3 minutes
🗣️  Speakers detected: 8
💬 Utterances: 342

📋 TESTIMONY EXTRACTED: 8 speakers
----------------------------------------------------------------------

1. Jane Smith
   Label: Speaker A
   Topic: Wildfire prevention funding
   Position: support
   Organization: Marin Conservation League
   Time: 45:23
   Quote: "I strongly support the allocation of $1.1M for wildfire prevention..."

2. Robert Johnson
   Label: Speaker B
   Topic: Wildfire prevention funding
   Position: support
   Time: 47:15
   Quote: "As a resident of the hills, I've seen the fire danger firsthand..."

...

💾 Results saved to: data/pilot/youtube_testimony_abc123xyz.json

✅ POC COMPLETE!
```

---

## Cost Tracking

The script will use AssemblyAI credits. Track usage:

1. Visit: https://www.assemblyai.com/app/billing
2. Check "Credits Used" and "Credits Remaining"

**Expected costs**:
- Oct 6 meeting (2 hours): $0.74 from $50 free credits
- Remaining: $49.26 (~133 hours)

---

## Troubleshooting

### Error: "yt-dlp not installed"

```bash
pip install yt-dlp
```

### Error: "FFmpeg not found"

```bash
# macOS
brew install ffmpeg

# Linux
sudo apt-get install ffmpeg
```

### Error: "AssemblyAI API key required"

Set the environment variable:
```bash
export ASSEMBLYAI_API_KEY="your_key_here"
```

### Error: "No YouTube video found on page"

The meeting may not have a video published yet. Try:
1. Check the meeting page manually
2. Look for "Watch online" section
3. Try a different meeting date

### Error: "Transcription failed"

Check:
1. API key is valid
2. You have remaining credits
3. Audio file was downloaded successfully

---

## Next Steps

After POC validation:

1. **Review accuracy**: Compare extracted testimony to video
2. **Adjust prompts**: Improve LLM extraction if needed
3. **Batch processing**: Run on all 25 meetings
4. **Database integration**: Insert into testimony table

---

## Support

- AssemblyAI Docs: https://www.assemblyai.com/docs
- AssemblyAI Support: https://www.assemblyai.com/support
- yt-dlp Issues: https://github.com/yt-dlp/yt-dlp/issues
