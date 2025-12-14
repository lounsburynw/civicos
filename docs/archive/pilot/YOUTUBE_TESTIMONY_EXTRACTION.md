# YouTube Testimony Extraction with Speaker Diarization

**Status**: Research complete, implementation pending
**Created**: 2025-11-13
**Purpose**: Extract testimony from San Rafael YouTube meeting videos using speech-to-text + speaker diarization

---

## Overview

San Rafael publishes **full YouTube videos** for all City Council meetings, which enables **richer testimony extraction** than Legistar API:

- ✅ Speaker identification (via diarization)
- ✅ Full testimony quotes
- ✅ Timestamps for each speaker
- ✅ Position inference (support/oppose from tone + content)
- ✅ Organization mentions

**vs Legistar API** (just speaker names, no content)

---

## Architecture

### Pipeline Flow

```
1. EXTRACT VIDEO ID
   └─> Parse San Rafael meeting page HTML
       Input:  Meeting URL (e.g., /meetings/city-council-march-03-2025/)
       Output: YouTube video ID (e.g., rbbh5eOeOtM)
       Time:   <1 second per meeting

2. DOWNLOAD AUDIO
   └─> yt-dlp (Python library)
       Input:  YouTube video ID
       Output: MP3 audio file
       Time:   ~30 seconds per 2-hour meeting
       Cost:   $0 (free download)

3. TRANSCRIBE + DIARIZE
   └─> AssemblyAI or Deepgram API
       Input:  MP3 audio file
       Output: Transcript with speaker labels + timestamps
       Time:   ~2 minutes per 2-hour meeting (real-time or faster)
       Cost:   $0.37/hour (AssemblyAI) or $0.0043/min (Deepgram)

4. EXTRACT TESTIMONY
   └─> LLM structured extraction
       Input:  Transcript with speakers + agenda items
       Output: Speaker names, positions, testimony text per item
       Time:   ~30 seconds per meeting (LLM call)
       Cost:   ~$0.01 per meeting (gpt-4o-mini)

5. STORE IN DATABASE
   └─> Insert into testimony table
       Same as Legistar approach
```

---

## Service Comparison

### AssemblyAI (Recommended ⭐)

**Pricing**: $0.37/hour ($0.00617/minute)
- Speaker diarization: **Included at no extra cost**
- Free trial: $50 in credits (~135 hours)
- Volume discounts: Up to 50% for high usage

**Features**:
- Speaker labels across 95 languages
- Automatic language detection
- High accuracy for meeting audio
- Meeting-specific features (action items, summaries)
- RESTful API + Python SDK

**Advantages**:
- Simple flat pricing
- Meeting-optimized models
- Generous free tier
- Great documentation

**Code Example**:
```python
import assemblyai as aai

aai.settings.api_key = "YOUR_API_KEY"

config = aai.TranscriptionConfig(
    speaker_labels=True,
    speakers_expected=10  # Optional hint
)

transcriber = aai.Transcriber()
transcript = transcriber.transcribe("meeting_audio.mp3", config)

for utterance in transcript.utterances:
    print(f"Speaker {utterance.speaker}: {utterance.text}")
```

**Cost for San Rafael**:
- 25 meetings × 2 hours each = 50 hours
- 50 hours × $0.37/hour = **$18.50 total**
- Free with $50 trial credits!

### Deepgram

**Pricing**: $0.0043/minute ($0.258/hour)
- Speaker diarization: Reports say "included" but some sources say extra cost
- Free trial: $150 in credits
- Usage-based pricing (pay as you go)

**Features**:
- Speaker diarization for meetings
- Real-time and batch options
- Multiple model options (Nova-2, Enhanced, Base)
- Streaming support

**Advantages**:
- Slightly cheaper per hour
- Larger free trial credits
- Real-time streaming option

**Disadvantages**:
- Mixed reports on diarization pricing
- Less meeting-specific features
- Diarization accuracy issues in overlapping speech

**Cost for San Rafael**:
- 25 meetings × 2 hours each = 50 hours
- 50 hours × $0.258/hour = **$12.90 total**
- Free with $150 trial credits!

### Recommendation: AssemblyAI

**Why AssemblyAI**:
1. **Clear pricing** - No confusion about diarization costs
2. **Meeting-optimized** - Better accuracy for City Council audio
3. **Simpler API** - More straightforward Python SDK
4. **Free tier covers pilot** - $50 credits = 135 hours (we need 50)

---

## Implementation Plan

### Phase 1: Proof of Concept (1-2 hours)

**Goal**: Extract testimony from Oct 6 wildfire meeting

**Steps**:
1. Extract video ID from meeting page
2. Download audio with yt-dlp
3. Transcribe with AssemblyAI (free trial)
4. Extract testimony structure with LLM
5. Compare against manual watching

**Success criteria**:
- ✅ Identify 8+ speakers (expected from Oct 6)
- ✅ Extract testimony quotes
- ✅ Map to specific agenda items
- ✅ Infer positions (support/oppose)

**Code**: `scripts/extract_youtube_testimony_poc.py`

### Phase 2: Batch Processing (3-4 hours)

**Goal**: Process all 25 San Rafael City Council meetings

**Steps**:
1. Load validated decisions JSON
2. Extract video IDs for all meetings
3. Batch download audio files
4. Batch transcribe with AssemblyAI
5. Extract testimony per decision
6. Insert into testimony table

**Success criteria**:
- ✅ Process 25 meetings end-to-end
- ✅ Extract 125-375 speakers (5-15 per meeting)
- ✅ Stay within $50 free tier
- ✅ Generate coalition discovery data

**Code**: `scripts/batch_youtube_testimony.py`

### Phase 3: Quality Validation (1 hour)

**Goal**: Validate accuracy against manual spot-checks

**Steps**:
1. Manually watch 3-5 meetings
2. Compare speaker counts
3. Validate testimony quotes
4. Check speaker attribution

**Success criteria**:
- ✅ Speaker count accuracy >90%
- ✅ Testimony content accuracy >85%
- ✅ Speaker labels consistent (Speaker A stays A throughout)

---

## Technical Implementation

### Dependencies

```bash
# Audio extraction
pip install yt-dlp

# Speech-to-text (choose one)
pip install assemblyai
# OR
pip install deepgram-sdk

# LLM for testimony extraction (existing)
# Uses existing llm_provider.py
```

### Step 1: Extract Video ID

```python
def extract_youtube_video_id(meeting_url: str) -> str:
    """
    Extract YouTube video ID from San Rafael meeting page

    Args:
        meeting_url: e.g., https://www.cityofsanrafael.org/meetings/city-council-march-03-2025/

    Returns:
        Video ID: e.g., rbbh5eOeOtM
    """
    import requests
    from bs4 import BeautifulSoup
    import re

    response = requests.get(meeting_url)
    soup = BeautifulSoup(response.content, 'html.parser')

    # Look for YouTube iframe embed
    iframe = soup.find('iframe', src=re.compile(r'youtube\.com/embed/'))
    if iframe:
        src = iframe['src']
        video_id = src.split('/')[-1].split('?')[0]
        return video_id

    # Look for YouTube player div (data attribute)
    player_div = soup.find('div', {'data-video-id': True})
    if player_div:
        return player_div['data-video-id']

    # Fallback: Look in page source for YouTube links
    youtube_pattern = r'youtube\.com/watch\?v=([a-zA-Z0-9_-]+)'
    match = re.search(youtube_pattern, response.text)
    if match:
        return match.group(1)

    return None
```

### Step 2: Download Audio

```python
import yt_dlp
import tempfile

def download_youtube_audio(video_id: str) -> str:
    """
    Download YouTube video audio as MP3

    Args:
        video_id: YouTube video ID

    Returns:
        Path to downloaded MP3 file
    """
    url = f"https://www.youtube.com/watch?v={video_id}"

    # Create temp file for audio
    temp_dir = tempfile.gettempdir()
    output_path = f"{temp_dir}/{video_id}.mp3"

    ydl_opts = {
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '128',  # Lower quality = faster upload
        }],
        'outtmpl': output_path.replace('.mp3', ''),
        'quiet': True,
        'no_warnings': True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    return output_path
```

### Step 3: Transcribe with AssemblyAI

```python
import assemblyai as aai
from typing import List, Dict

def transcribe_with_diarization(audio_path: str) -> List[Dict]:
    """
    Transcribe audio with speaker diarization

    Args:
        audio_path: Path to MP3 file

    Returns:
        List of utterances with speaker labels
    """
    aai.settings.api_key = os.getenv('ASSEMBLYAI_API_KEY')

    config = aai.TranscriptionConfig(
        speaker_labels=True,
        speakers_expected=15,  # City Council meetings typically have 5-15 speakers
        language_code='en'  # San Rafael is English
    )

    transcriber = aai.Transcriber()
    transcript = transcriber.transcribe(audio_path, config)

    # Wait for completion (blocking)
    if transcript.status == aai.TranscriptStatus.error:
        raise Exception(f"Transcription failed: {transcript.error}")

    # Extract utterances
    utterances = []
    for utterance in transcript.utterances:
        utterances.append({
            'speaker': utterance.speaker,
            'text': utterance.text,
            'start': utterance.start,  # milliseconds
            'end': utterance.end,
            'confidence': utterance.confidence
        })

    return utterances
```

### Step 4: Extract Testimony Structure

```python
from llm_provider import get_model_for_task

def extract_testimony_from_transcript(
    utterances: List[Dict],
    agenda_items: List[Dict],
    meeting_date: str
) -> List[Dict]:
    """
    Use LLM to structure transcript into testimony records

    Args:
        utterances: Raw transcript with speaker labels
        agenda_items: List of agenda items from decision JSON
        meeting_date: ISO date

    Returns:
        List of testimony records (speaker name, item, position, text)
    """
    # Build context for LLM
    transcript_text = "\n\n".join([
        f"[{u['start']//60000}:{(u['start']//1000)%60:02d}] Speaker {u['speaker']}: {u['text']}"
        for u in utterances
    ])

    agenda_context = "\n".join([
        f"{item['item_ref']}: {item['title']}"
        for item in agenda_items
    ])

    prompt = f"""
You are analyzing a City Council meeting transcript to extract public testimony.

Meeting Date: {meeting_date}

Agenda Items:
{agenda_context}

Transcript:
{transcript_text}

Extract testimony records for each speaker. For each testimony:
1. Speaker name (if they introduce themselves, otherwise "Speaker N")
2. Agenda item they're addressing (match to item_ref)
3. Position (support/oppose/neutral/comment)
4. Organization (if mentioned)
5. Key quotes (1-2 sentences)

Return JSON array of testimony records.
"""

    model = get_model_for_task('agenda_parsing')
    response = model.generate(prompt, response_format='json')

    return response['testimony']
```

### Step 5: Insert into Database

```python
import sqlite3
import json

def insert_youtube_testimony(
    testimony_records: List[Dict],
    decision_id: int,
    db_path: str = "data/civic_participation.db"
) -> int:
    """
    Insert testimony records into database

    Args:
        testimony_records: Extracted testimony
        decision_id: FK to decisions table
        db_path: Database path

    Returns:
        Number of records inserted
    """
    conn = sqlite3.connect(db_path)

    inserted = 0
    for record in testimony_records:
        conn.execute("""
            INSERT INTO testimony (
                decision_id,
                speaker_name,
                position,
                organization,
                testimony_text,
                speaking_order,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
        """, [
            decision_id,
            record['speaker_name'],
            record['position'],
            record.get('organization'),
            record.get('key_quotes'),
            record.get('speaking_order', 0)
        ])
        inserted += 1

    conn.commit()
    conn.close()

    return inserted
```

---

## Cost Analysis

### 25 San Rafael City Council Meetings

**Assumptions**:
- Average meeting length: 2 hours
- Total audio: 50 hours
- Speakers per meeting: 5-15 (average 10)
- Total speakers: ~250

### Costs Breakdown

| Service | Cost | Notes |
|---------|------|-------|
| YouTube download | $0 | Free (yt-dlp) |
| AssemblyAI transcription | $18.50 | $0.37/hour × 50 hours |
| LLM testimony extraction | $2.50 | $0.10 per meeting × 25 |
| **Total** | **$21.00** | **Covered by $50 free trial** |

### Comparison to Alternatives

| Approach | Cost | Quality | Coverage |
|----------|------|---------|----------|
| **YouTube + AssemblyAI** | **$21** | **High (testimony text)** | **100%** |
| Legistar API | $0 | Medium (names only) | 60-80% |
| Minutes parsing | $2.50 | Low (inconsistent) | 40-60% |
| Manual watching | $0 | Highest | 100% (slow) |

---

## Data Quality Expected

### Speaker Identification

**AssemblyAI diarization accuracy**:
- Single speaker: 95%+
- 2-5 speakers: 90-95%
- 6-10 speakers: 85-90%
- 10+ speakers: 75-85%

**Challenges**:
- Overlapping speech (common in heated discussions)
- Similar voices
- Background noise
- Speaker changes mid-sentence

**Mitigation**:
- Use `speakers_expected` hint (improves accuracy)
- LLM can help re-attribute confused segments
- Manual validation for high-stakes cases (Oct 6)

### Testimony Content

**Expected accuracy**:
- Transcription: 90-95% (AssemblyAI is highly accurate)
- Speaker names: 60-80% (if they introduce themselves)
- Positions: 70-85% (LLM inference from content)
- Organizations: 50-70% (if mentioned explicitly)

**Much better than Legistar API**:
- Legistar: Speaker names only, no content
- YouTube: Full testimony text + position inference

---

## Next Steps

### Immediate (Session 104 Stretch Goal)

1. **Create POC script**: `scripts/extract_youtube_testimony_poc.py`
2. **Test on Oct 6**: Validate against wildfire case study
3. **Sign up for AssemblyAI**: Get $50 free credits
4. **Document results**: Accuracy metrics

### Session 105 Integration

1. **Batch processing**: Process all 25 San Rafael meetings
2. **Database population**: Insert into testimony table
3. **Vector embeddings**: Include testimony text in ChromaDB
4. **Coalition queries**: Test with real data

### Future Enhancements

1. **Multi-jurisdiction**: Expand to other cities with YouTube videos
2. **Real-time processing**: Process meetings as they stream
3. **Speaker name linking**: Match "Speaker A" to actual names via minutes cross-reference
4. **Position confidence**: Score support/oppose confidence

---

## Alternative: Deepgram Implementation

If AssemblyAI doesn't work well, here's Deepgram approach:

```python
from deepgram import DeepgramClient, PrerecordedOptions

def transcribe_with_deepgram(audio_path: str) -> List[Dict]:
    """Transcribe with Deepgram speaker diarization"""

    deepgram = DeepgramClient(api_key=os.getenv('DEEPGRAM_API_KEY'))

    with open(audio_path, 'rb') as audio:
        source = {'buffer': audio, 'mimetype': 'audio/mp3'}

        options = PrerecordedOptions(
            model='nova-2',
            smart_format=True,
            diarize=True,
            diarize_version='2023-09-04'
        )

        response = deepgram.listen.prerecorded.v('1').transcribe_file(source, options)

    # Extract utterances
    utterances = []
    for word in response.results.channels[0].alternatives[0].words:
        utterances.append({
            'speaker': word.speaker,
            'text': word.punctuated_word,
            'start': word.start * 1000,  # Convert to milliseconds
            'end': word.end * 1000,
            'confidence': word.confidence
        })

    return utterances
```

---

## References

- AssemblyAI Pricing: https://www.assemblyai.com/pricing
- AssemblyAI Speaker Diarization: https://www.assemblyai.com/docs/speech-to-text/speaker-diarization
- Deepgram Pricing: https://deepgram.com/pricing
- yt-dlp Documentation: https://github.com/yt-dlp/yt-dlp
- San Rafael YouTube: https://www.youtube.com/cityofsanrafael

---

**Session**: 104 (research), 105 (implementation target)
**Status**: Research complete, ready for POC
**Recommendation**: Start with AssemblyAI POC for Oct 6 wildfire meeting
