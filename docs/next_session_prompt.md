# Recommended: Platform Coverage Expansion

**Priority:** P0 (platform_coverage_expansion)
**Area:** operator_readiness
**Date:** 2026-04-02

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

The previous session onboarded 3 Marin cities (Novato, Sausalito, Tiburon) and built a headless-ready onboarding pipeline (`--trial` flag, QC script, structured diagnostics). Batch testing all 8 Marin cities revealed that 5 fail due to unsupported platforms:

| City | Platform | Needed |
|------|----------|--------|
| Corte Madera | CivicPlus (Archive.aspx) | New extraction client |
| Larkspur | CivicPlus (Archive.aspx) | New extraction client |
| Fairfax | WordPress (townoffairfaxca.gov) | Universal adapter |
| Ross | Custom (townofrossca.gov) | Universal adapter |
| Belvedere | Custom (cityofbelvedere.org) | Universal adapter |

A **Universal Adapter** already exists (`packages/civicos-extraction/src/civicos_extraction/clients/universal.py`) that uses LLM to generate CSS-selector configs at onboard time, then extracts deterministically. It's just not wired into the detection fallback. Similarly, 311 issue discovery only supports SeeClickFix, but Marin County has adopted FixItMarin.

Launch phase is 128/138 items done (turnkey_onboarding_marin marked done this session).

## Goal

Three deliverables:
1. **CivicPlus extraction client** — thin client for CivicPlus Archive.aspx pages (unlocks Corte Madera, Larkspur)
2. **Universal adapter as detection fallback** — when all known platforms fail, try the universal adapter on the city's agendas page (unlocks Fairfax, Ross, Belvedere)
3. **311 provider discovery** — expand beyond SeeClickFix to detect FixItMarin and other providers

## Key Files

- `packages/civicos-extraction/src/civicos_extraction/clients/universal.py` — Universal adapter (LLM config gen + deterministic extraction)
- `packages/civicos-extraction/src/civicos_extraction/clients/universal_config.py` — LLM prompt for generating adapter configs
- `packages/civicos-extraction/src/civicos_extraction/clients/factory.py` — Source factory (already has `universal` case)
- `packages/civicos-extraction/src/civicos_extraction/platform_detection.py:1125` — `discover_platform()` — add universal adapter fallback here
- `packages/civicos-extraction/src/civicos_extraction/onboard.py:524` — `detect_issue_source()` — currently SeeClickFix only
- `scripts/onboard.py` — `--trial` flag for testing (use it!)
- `docs/internal/headless-onboard-prompt.md` — Batch onboarding prompt template

### CivicPlus Reference URLs
- Corte Madera: `https://www.townofcortemadera.org/681/Agendas-Minutes-and-Notices` (Archive.aspx, 31 refs)
- Larkspur: `https://www.ci.larkspur.ca.us/Archive.aspx?AMID=49`
- Pattern: `/Archive.aspx?AMID=N` for agendas, `/Archive.aspx?AMID=M` for minutes

### Custom Site Reference URLs
- Fairfax: `https://townoffairfaxca.gov/agendas-town-council/`
- Ross: `https://www.townofrossca.gov/meetings`
- Belvedere: `https://www.cityofbelvedere.org` (check for agendas page)

### 311 Provider Context
- Memory file `memory/project_311_providers.md`: Marin switching to FixItMarin (Mar 2026)
- Current detection: `detect_issue_source()` only tries SeeClickFix
- FixItMarin URL: unknown — needs web research

## Suggested Approach

### 1. CivicPlus Client (~1 hour)
1. Create `packages/civicos-extraction/src/civicos_extraction/clients/civicplus.py`
2. CivicPlus Archive.aspx pages have a predictable structure: table rows with date, title, PDF links
3. Fetch `Archive.aspx?AMID=N`, parse HTML table, extract meeting rows
4. Register in `factory.py` and `platform_detection.py`
5. Test: `python scripts/onboard.py --city "Corte Madera" --state CA --county Marin --trial`

### 2. Universal Adapter Fallback (~30 min)
1. In `platform_detection.py:discover_platform()`, after all platforms fail, try the city website URL found during website scraping and run `generate_adapter_config()` on pages that look like meeting listings
2. Save adapter config to `data/extraction/{jid}.json` with `source_type: "universal"`
3. Test: `python scripts/onboard.py --city "Fairfax" --state CA --county Marin --trial`

### 3. 311 Provider Discovery (~30 min)
1. Expand `detect_issue_source()` to check for FixItMarin and other providers
2. Add provider detection patterns (URL probing)
3. Make issue_source configurable per-jurisdiction in YAML

### 4. Batch Retest
```bash
for city in "Corte Madera" "Larkspur" "Fairfax" "Ross" "Belvedere"; do
  python scripts/onboard.py --city "$city" --state CA --county Marin --trial
done
```

## Tests to Run

```bash
pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="
pytest packages/civicos/tests/test_jurisdiction.py -q --override-ini="addopts="
python scripts/qc_sandbox.py -j city-corte-madera
python scripts/qc_sandbox.py -j city-fairfax
```

## Success Criteria

- [ ] CivicPlus client extracts meetings from Corte Madera and Larkspur
- [ ] Universal adapter generates working configs for at least 1 custom site
- [ ] All 5 previously-failing cities pass `--trial` or have clear actionable failure reasons
- [ ] 311 provider detection finds FixItMarin for Marin jurisdictions
- [ ] Batch retest: 7-8 out of 8 Marin cities pass `--trial`
- [ ] launch.json item marked done
