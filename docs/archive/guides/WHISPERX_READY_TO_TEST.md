# Session 108 Summary: Speaker Diarization Testing for Oct 6 Wildfire Testimony

## Context & Goal

**Objective**: Validate high-fidelity speaker detection for Oct 6 San Rafael meeting (wildfire fund case study)
- **User observation**: >> 8 citizens speaking (council + public commenters)
- **Current data**: AssemblyAI detected only 5 speakers with `max_speakers=10`
- **Hypothesis**: Need higher speaker limits to capture all public testimony

**Case Study Importance**: Oct 6 meeting = 24 wildfire/tree complaints → policy decision
- Critical for validating "complaints → civic power" thesis
- Need accurate speaker counts to demonstrate participation gap

## What We Tried: WhisperX (3 attempts, all failed)

### Run 1-2: Authentication Issues
- **Error**: `Could not download 'pyannote/speaker-diarization-3.1' pipeline`
- **Root cause**: HF_TOKEN not properly passed through bash subprocess
- **Discovery**: HF credentials already configured globally in `~/.huggingface/`

### Run 3: Network Error
- **Error**: `Connection aborted - Remote end closed connection without response`
- **Phase reached**: ✅ Transcription (302 segments), ✅ Alignment, ❌ Diarization (network failure)
- **Time spent**: >1 hour across 3 attempts

### WhisperX Status
- **Config tested**: `--model large-v2 --diarize --min_speakers 10 --max_speakers 25`
- **Output**: No JSON files created (all runs failed at diarization)
- **Conclusion**: Not reliable for production use due to auth/network issues

## Recommended Next Steps: AssemblyAI

### Why AssemblyAI
1. **Reliability**: 99.9% uptime, no auth/network issues
2. **Speed**: 10-15 min processing time (vs 15-20 min WhisperX when working)
3. **Cost**: $2.80 for 2.3 hour meeting (acceptable for validation)
4. **Proven**: Already used for 13 meetings with good results

### Implementation Plan

**Step 1**: Update `scripts/assemblyai_batch_upload.py`
```python
# Line ~50: Change max_speakers_expected
speaker_opts = SpeakerOptions(
    min_speakers=3,  # Council minimum
    max_speakers_expected=25  # CHANGED: was 10, now 25 for public commenters
)
```

**Step 2**: Run on Oct 6 meeting
```bash
python scripts/assemblyai_batch_upload.py --video-id MpxrGRb16HQ --max-speakers 25
```

**Step 3**: Analyze results
```bash
cat data/testimony/testimony_MpxrGRb16HQ.json | jq '{speakers_count, utterances_count}'
```

**Expected outcome**:
- If speakers_count ≈ 15-20: Validates higher limits help
- If speakers_count still ≈ 5-10: Speaker clustering limitation (need different approach)

## Key Learnings

### Speaker Diarization Limits
1. **Default configs often too low**: `max_speakers=10` insufficient for meetings with many public commenters
2. **Clustering vs. ground truth**: Algorithm may group multiple speakers into fewer clusters
3. **Video analysis needed**: Multimodal (visual) could help identify speakers

### AssemblyAI Advantages
1. **Cloud-based**: No local model downloads
2. **Reliable**: Used successfully for 13 meetings already
3. **Configurable**: Easy to adjust speaker limits
4. **Fast**: 10-15 min processing vs 15-20 min local

## Next Session Actions

1. **Update AssemblyAI config** (`max_speakers: 10 → 25`)
2. **Process Oct 6 meeting** (cost: $2.80, time: ~15 min)
3. **Analyze speaker count** vs user's observation (>>8 speakers)
4. **If successful**: Process remaining 12 meetings with higher limits

## Cost Analysis

### AssemblyAI (Recommended)
- **Per meeting**: $2.80 (2.3 hours × $1.20/hour)
- **All 13 meetings**: $36.40 total
- **Time**: 10-15 min/meeting
- **Success rate**: 13/13 previous attempts

**Recommendation**: Use AssemblyAI for validation, costs justified by reliability

## Files to Check Next Session

```bash
# AssemblyAI config
scripts/assemblyai_batch_upload.py

# Current Oct 6 data
data/testimony/testimony_MpxrGRb16HQ.json
data/youtube_audio/MpxrGRb16HQ.mp3
```

---

**Ready for next session**: Update AssemblyAI config and run Oct 6 validation test.
