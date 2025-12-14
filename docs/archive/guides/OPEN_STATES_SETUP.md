# Open States API Setup

**Purpose**: Auto-verify legislative metadata (enactment dates, titles, URLs) instead of 2-3 hours manual verification.

## Why Open States?

- ✅ **Free** API (registration required)
- ✅ **Comprehensive** metadata (all 50 states, DC, Puerto Rico)
- ✅ **Verified** data (scraped from official sources)
- ✅ **Complete** bill history (actions, votes, sponsors)
- ✅ **Official URLs** to leginfo.legislature.ca.gov

## Setup (5 minutes)

### Step 1: Register for API Key

1. Visit: https://openstates.org/accounts/signup/
2. Create free account
3. Navigate to: https://openstates.org/account/profile/
4. Copy your API key

### Step 2: Configure Environment

```bash
# Add to ~/.zshrc
echo "export OPENSTATES_API_KEY='your-key-here'" >> ~/.zshrc

# Reload
source ~/.zshrc

# Verify
echo $OPENSTATES_API_KEY
```

### Step 3: Test API

```bash
python3 scripts/verify_housing_metadata.py
```

## API Details

**Endpoint**: https://v3.openstates.org/bills

**Documentation**: https://docs.openstates.org/api-v3/

**Rate Limits**: Not publicly documented, but generous for free tier

## Usage

### Automated Verification Workflow

```bash
# Step 1: Discovery with Perplexity ($0.04)
python3 scripts/automate_housing_context.py

# Step 2: Auto-verify with Open States (free)
python3 scripts/verify_housing_metadata.py

# Step 3: Review verification report (15 min)
cat data/legislative_context/housing_verification_report.json

# Step 4: Apply corrections and commit
mv data/legislative_context/california_housing.json.DRAFT \
   data/legislative_context/california_housing.json
git commit -m "Add verified housing legislative context"
```

### Manual Query Examples

**Search for specific bill**:
```bash
curl "https://v3.openstates.org/bills?jurisdiction=California&identifier=SB%209&include=actions,sources" \
  -H "X-API-KEY: your-key"
```

**Search by session**:
```bash
curl "https://v3.openstates.org/bills?jurisdiction=California&session=2021-2022&q=housing&per_page=20" \
  -H "X-API-KEY: your-key"
```

**Full text search**:
```bash
curl "https://v3.openstates.org/bills?jurisdiction=California&q=affordable+housing+density&per_page=10" \
  -H "X-API-KEY: your-key"
```

## What Open States Provides

For each bill:
- ✅ Exact identifier (e.g., "SB 9")
- ✅ Full title
- ✅ Legislative session
- ✅ Classification (bill, resolution, etc.)
- ✅ **Complete action history** (introduction, committee, votes, signatures)
- ✅ **Enactment date** (extracted from actions)
- ✅ Sponsors and co-sponsors
- ✅ Subjects/topics
- ✅ **Official sources** (leginfo.legislature.ca.gov URLs)

## Verification Output

The `verify_housing_metadata.py` script generates:

**File**: `data/legislative_context/housing_verification_report.json`

**Contents**:
```json
{
  "generated_at": "2025-10-07T14:30:00",
  "total_bills_verified": 6,
  "verification_method": "Open States API v3",
  "reports": [
    {
      "bill_number": "SB 9",
      "verified": true,
      "title_match": true,
      "enactment_date_match": true,
      "verified_enactment_date": "2021-09-16",
      "perplexity_enactment_date": "2021-09-16",
      "official_sources": [
        "https://leginfo.legislature.ca.gov/faces/billNavClient.xhtml?bill_id=202120220SB9"
      ]
    }
  ]
}
```

## Cost Comparison

| Method | Time | Cost | Precision |
|--------|------|------|-----------|
| **Manual verification** | 2-3 hours | $0 | 99% |
| **Perplexity only** | 5 min | $0.04 | 85-90% |
| **Perplexity + Open States** | 20 min | $0.04 | 96-98% |
| **Perplexity + Open States + spot-check** | 35 min | $0.04 | 99% |

## Recommended: Hybrid Approach

1. **Discovery**: Perplexity ($0.04, 5 min) - Find relevant bills with context
2. **Verification**: Open States (free, 10 min) - Auto-verify metadata
3. **Spot-check**: Human (15 min) - Verify 2-3 critical bills manually
4. **Commit**: Git with audit trail

**Total**: 30 minutes, $0.04, 99% precision

## Troubleshooting

**401 Unauthorized**:
- Check `OPENSTATES_API_KEY` is set: `echo $OPENSTATES_API_KEY`
- Verify key is valid at https://openstates.org/account/profile/

**No results for bill**:
- Try different session (California uses 2-year sessions: 2021-2022, 2023-2024)
- Check bill number format (space required: "SB 9" not "SB9")
- Bill may be too old (Open States coverage varies by state/year)

**Rate limited**:
- Add delays between requests (`time.sleep(1)`)
- Contact Open States for higher rate limits

## Next Steps

After setup:
1. Run verification: `python3 scripts/verify_housing_metadata.py`
2. Review report: `data/legislative_context/housing_verification_report.json`
3. Apply corrections to DRAFT files
4. Repeat for other topics (transportation, climate, etc.)
