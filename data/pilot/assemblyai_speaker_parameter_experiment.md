# AssemblyAI Speaker Parameter Experiment

**Session**: 109
**Date**: 2025-11-18
**Status**: ⏳ Running (Background ID: f9e6b5)

---

## Hypothesis

**Question**: Does providing accurate speaker count estimates to AssemblyAI improve diarization quality?

**Background**:
- Session 108: Analyzed 4,000 chars → estimated 6 speakers → configured AssemblyAI with min=5, max=10
- AssemblyAI result: **5 speakers detected** (A, B, C, D, E)
- Session 109: Analyzed 125,663 chars (full transcript) → found **50 actual speakers**
- Problem: AssemblyAI forced 50 speakers into 5 clusters (severe merging)

**Hypothesis**: Re-running with min=40, max=60 will improve speaker separation.

---

## Experimental Design

### Control (Original Run - Session 108)

**Configuration**:
```python
SpeakerOptions(
    min_speakers_expected=5,
    max_speakers_expected=10
)
```

**Results**:
- Speakers detected: **5** (A, B, C, D, E)
- Utterances: 217
- Cost: $2.80
- Quality: **Poor** - massive speaker merging
  - Speaker B contains: Vice Mayor Bushy + Quinn Gardner + Belle Cole
  - Salama and Sharon Demer not found (merged into other speakers)
  - Testimony extraction failed for 2 of 3 wildfire speakers (67% failure rate)

### Treatment (New Run - Session 109)

**Configuration**:
```python
SpeakerOptions(
    min_speakers_expected=40,
    max_speakers_expected=60
)
```

**Expected results**:
- Speakers detected: ??? (likely 10-30, not 50)
- Utterances: ??? (likely similar ~200-250)
- Cost: $2.80
- Quality: **Hopefully better** - less merging

**Note**: We don't expect AssemblyAI to actually detect all 50 speakers. Voice clustering algorithms typically max out at 20-30 speakers for practical accuracy. But we expect **some improvement** over 5 speakers.

---

## Success Criteria

### Minimal Success (Improvement but still limited)
- ✅ Speakers detected: 8-15 (2-3x improvement)
- ✅ Belle Cole gets her own speaker label (not merged with Quinn Gardner)
- ⚠️ Salama/Sharon still might not be isolated (brief testimony may cluster with others)

### Moderate Success (Meaningful improvement)
- ✅ Speakers detected: 15-25 (3-5x improvement)
- ✅ All 3 wildfire speakers isolatable
- ✅ Can extract testimony for all 3 with medium-high confidence

### Full Success (Unlikely but ideal)
- ✅ Speakers detected: 30-50 (6-10x improvement)
- ✅ All public commenters separable
- ✅ High-confidence testimony extraction for all speakers

### Failure (No improvement)
- ❌ Speakers detected: 5-7 (minimal change)
- ❌ Same merging issues
- ❌ No improvement in testimony extraction

---

## What We'll Learn

### If Successful (>10 speakers detected):
- ✅ Accurate speaker estimates improve AssemblyAI diarization
- ✅ Full transcript analysis → better parameters → better results
- ✅ Hybrid approach viable: YouTube LLM + AssemblyAI with tuned parameters
- 🎯 **Recommendation**: Always run full transcript analysis first, then AssemblyAI

### If Marginal (6-10 speakers detected):
- ⚠️ Small improvement but not transformative
- ⚠️ AssemblyAI has algorithmic limits regardless of parameters
- ⚠️ May still need manual review for critical testimony
- 🎯 **Recommendation**: Use AssemblyAI for structure, manual review for exact quotes

### If Failed (5 speakers detected):
- ❌ Speaker parameters don't significantly affect AssemblyAI output
- ❌ Algorithm defaults/limits override user parameters
- ❌ Audio quality or algorithm design are bottlenecks
- 🎯 **Recommendation**: Skip AssemblyAI diarization, use transcription only + manual review

---

## Implications for Future Work

### For Oct 6 Case Study:
- **If successful**: Extract testimony from v2 transcript, validate against manual review
- **If failed**: Proceed with manual video review (8 minutes, 1:57:26-2:05:43)

### For 12-Month Retrospective (24 meetings):
- **If successful**: Run full transcript → AssemblyAI pipeline for all meetings ($67 total)
- **If failed**: Use transcription only, manual review for high-stakes decisions

### For 26-City Scaling (624 meetings/year):
- **If successful**: Automated pipeline viable ($1,747/year for diarization)
- **If failed**: Manual review bottleneck (312 hours/year @ 30 min/meeting)

---

## Cost-Benefit Analysis

**Experiment cost**: $2.80 (one additional AssemblyAI run)

**Value if successful**:
- Prove automated testimony extraction viable
- Eliminate manual video review (saves 30 min × 624 meetings = 312 hours/year)
- Foundation pitch: "Automated testimony extraction with 85% accuracy"

**Value if failed**:
- Validate manual review necessity
- Document AssemblyAI limitations for future reference
- Adjust strategy: transcription + manual review for testimony
- Foundation pitch: "Semi-automated with human-in-loop validation"

**Either way, worth $2.80 to know definitively.**

---

## Processing Status

**Started**: 2025-11-18 ~13:27 UTC
**Background ID**: f9e6b5
**Expected completion**: ~13:37 UTC (10 minutes)
**Check status**: `bash -c "cat /tmp/bash_output_f9e6b5.txt"`

**Monitor with**:
```bash
# Check if complete
ls -lh data/testimony/testimony_MpxrGRb16HQ_v2.json

# View results when ready
cat data/testimony/testimony_MpxrGRb16HQ_v2.json | jq '{
  speakers_count,
  utterances_count,
  speaker_config
}'
```

---

## Results (To Be Updated)

**Speakers detected**: ??? (pending)
**Utterances**: ??? (pending)
**Processing time**: ??? seconds
**Cost**: $2.80

**Comparison**:
- Original: 5 speakers → **???% improvement**
- Expected: 10-30 speakers
- Actual: **TO BE DETERMINED**

**Verdict**: **PENDING**

---

**Next**: Wait for processing to complete, then compare results and update strategy.
