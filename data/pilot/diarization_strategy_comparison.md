# Diarization Strategy Comparison: Range vs Exact Count

## Current Approach (Session 109)

**Parameters**: min=40, max=60 (±10 from LLM estimate of 50)
**Result**: 40 speakers detected
**Problem**: Salama merged with Mayor (under-segmentation)

## Proposed Approach

**Parameters**: min=50, max=50 (exact YouTube count)
**Expected**: 50 speaker labels forced
**Hypothesis**: Over-segmentation better than under-segmentation

## Trade-off Analysis

### Scenario 1: Current (min=40, max=60)

**What happens**:
- AssemblyAI clusters similar voices together
- Result: 40 speakers (conservative merge)
- **Problem**: Salama + Mayor merged → lost speaker attribution

**Impact on testimony extraction**:
- ❌ Lost: Salama's testimony attribution
- ✅ Kept: Coherent single speaker blocks

### Scenario 2: Proposed (min=50, max=50)

**What happens**:
- AssemblyAI forced to create 50 speaker labels
- May split single speakers into multiple labels
- **Benefit**: Prevents unwanted merges (Salama + Mayor)

**Impact on testimony extraction**:
- ✅ Kept: Salama gets separate speaker label (recoverable)
- ⚠️ Risk: Mayor split into Mayor_A + Mayor_B (but both still Mayor)
- ✅ Fix: Our merge script can re-combine via name matching

## User's Key Insight

> "Over-segmentation just cuts out certain pieces of testimony"

**Translation**:
- Over-segmentation: Speaker A → Labels A1, A2, A3
  - Still extractable via self-introduction in each segment
  - Merge script can recombine: "Belle Cole" appears in A1, A2, A3 → same person
  
- Under-segmentation: Speaker A + B → Label C
  - **UNRECOVERABLE**: Lost attribution entirely
  - Can't distinguish who said what
  - Salama + Mayor example

## Evidence from Session 109

**YouTube LLM Analysis** (50 speakers):
- 40 actual speakers
- 8-10 name variants (Mayor Kate + Kate = same person)
- 2-3 mentioned-not-spoken (Chief, Walter Gonzalez)

**AssemblyAI Result** (40 speakers):
- Correctly identified ~37-40 unique voices
- But merged Salama + Mayor (1 error)

## Recommendation: Test Both Approaches

### Test 1: Current (min=40, max=60)
- Cost: Already done ($2.80)
- Result: 40 speakers, 1 known merge error

### Test 2: Exact Count (min=50, max=50)
- Cost: $2.80
- Expected: 50 speakers, possibly with splits
- Validation: Check if Salama gets separate label

### Test 3: Conservative Upper Bound (min=50, max=70)
- Cost: $2.80
- Let AssemblyAI decide within range
- May find 50-60 speakers

## Predicted Outcome

**Forcing min=max=50**:
- ✅ Salama gets separate label (solves current problem)
- ⚠️ Mayor possibly split into 2-3 labels (recoverable via our merge)
- ✅ Public commenters all preserved (they introduce themselves)
- ⚠️ Council members possibly over-split (but we have minutes cross-reference)

**Net Impact**: Positive for testimony extraction use case

## Implementation

```python
# Option 1: Exact count (user's proposal)
min_speakers_expected=50,
max_speakers_expected=50

# Option 2: Conservative upper bound
min_speakers_expected=50,
max_speakers_expected=70

# Current (Session 109)
min_speakers_expected=40,
max_speakers_expected=60
```

## Validation Criteria

After re-running, check:
1. ✅ Salama has separate speaker label (not merged with Mayor)
2. ✅ Belle Cole still identified (not fragmented beyond recognition)
3. ✅ Sherna Deamer still identified
4. ⚠️ Mayor may be split (acceptable if coherent via merge script)

## Decision

**Recommend**: Test exact count (min=50, max=50)

**Rationale**:
1. User's intuition is sound (over-segmentation > under-segmentation)
2. Our merge pipeline can handle fragmentation (fuzzy matching + self-intros)
3. Current approach lost Salama (unrecoverable)
4. Cost is minimal ($2.80 to validate)
5. If successful, improves accuracy from 2/3 to 3/3 wildfire speakers

**If exact count works**: Use YouTube LLM count as **exact parameter** for all future meetings
**If too fragmented**: Fall back to range (min=count, max=count+20)
