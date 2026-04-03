# Headless Onboarding Prompt Template

Use this prompt with Claude Code headless mode (`claude -p`) to onboard cities autonomously.

## Single City

```
Onboard {city}, {state}, {county} County to CivicOS.

1. Run: python scripts/onboard.py --city "{city}" --state {state} --county "{county}" --trial
2. If "No meeting bodies discovered": search the city website for agenda/minutes links 
   to find the Granicus/Legistar URL and view_id. Update both data/extraction/city-{slug}.json 
   (archives, default_view_id, column_map) and data/jurisdictions/city-{slug}.yaml. 
   Then re-run --trial (without --force).
3. If YouTube channel doesn't match the city name, set transcripts.source to null in the YAML.
4. If election_sources is missing from the extraction JSON, add civera_election_stats 
   with county_slug "{county_slug}" and division_filter "{city}".
5. Report the [TRIAL_RESULT_JSON] output and any warnings.

Reference: docs/public/onboarding-pr-workflow.md (troubleshooting section)
```

## Batch Loop (Marin County)

```bash
for city in Novato Sausalito Larkspur Fairfax "Corte Madera" Tiburon Ross Belvedere; do
  claude -p "$(cat <<PROMPT
Onboard ${city}, CA, Marin County to CivicOS.

1. Run: python scripts/onboard.py --city "${city}" --state CA --county "Marin" --trial
2. If "No meeting bodies discovered": search the city website for agenda/minutes links 
   to find the Granicus/Legistar URL and view_id. Update both data/extraction/ JSON 
   (archives, default_view_id, column_map) and data/jurisdictions/ YAML. 
   Then re-run --trial (without --force).
3. If YouTube channel doesn't match the city name, set transcripts.source to null in the YAML.
4. If election_sources is missing from the extraction JSON, add civera_election_stats 
   with county_slug "marin" and division_filter "${city}".
5. Report the [TRIAL_RESULT_JSON] output and any warnings.

Reference: docs/public/onboarding-pr-workflow.md (troubleshooting section)
PROMPT
)"
done
```

## Variable Reference

| Variable | Example | How to find |
|----------|---------|-------------|
| `{city}` | Novato | Official city name |
| `{state}` | CA | Two-letter state code |
| `{county}` | Marin | County name (no "County" suffix) |
| `{slug}` | novato | Lowercase, hyphenated (auto-generated) |
| `{county_slug}` | marin | Lowercase county name for Civera API |

## After Trials Pass

Promote passing cities to production:

```bash
# Full Modal ingestion
modal run scripts/modal_ingest.py --jurisdiction city-{slug} \
  --meetings --chunks --agenda --decisions --issues --vectors \
  --meetings-days-past 365

# Deploy
modal deploy packages/civicos-services/src/civicos_services/servers/modal_api.py
```

## Known Failure Modes

| Symptom | Cause | Fix |
|---------|-------|-----|
| "No meeting bodies discovered" | Granicus view_id not at default 1-5 | Search city website for agenda links, find view_id |
| Wrong YouTube channel (neighboring city) | Name-similarity false positive | Set `transcripts.source: null` |
| 0 elections | Missing `election_sources` in JSON | Add civera config manually |
| SeeClickFix timeout | Intermittent API issue | Re-run; or set `issue_source: null` if city doesn't use it |
| "Could not find insertion point in jurisdiction.py" | Registry generator warning | Safe to ignore |
