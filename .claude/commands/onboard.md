# Onboard a New City

Interactive city onboarding wizard. Guides you through platform detection, config generation, validation, and deployment.

## Steps

### Step 1: Gather Information

Ask the user for:
- **City name** (required) — e.g., "Berkeley", "El Cerrito"
- **City website URL** (required) — e.g., "https://berkeleyca.gov"
- **State** (default: CA)
- **County** (required for HUD data) — e.g., "Alameda"
- **Known platform** (optional) — legistar, civicclerk, proudcity, or granicus

### Step 2: Run Platform Detection + Config Generation

```bash
source civicos-env/bin/activate && civicos-onboard "<CITY_NAME>" --url <URL> --state <STATE> --county "<COUNTY>" --dry-run
```

If the user provided a known platform, add `--platform <PLATFORM>`.

Show the user the generated config and explain any TODOs.

### Step 3: Review Against Existing Config (if any)

Check if a config already exists:
```bash
ls data/jurisdictions/city-<slug>.yaml 2>/dev/null
```

If it exists, compare the generated config against the existing one and highlight differences.

### Step 4: Write Config (if user approves)

Run without `--dry-run` to write the config file:
```bash
source civicos-env/bin/activate && civicos-onboard "<CITY_NAME>" --url <URL> --state <STATE> --county "<COUNTY>"
```

### Step 5: Validate

```bash
source civicos-env/bin/activate && civicos-validate city-<slug>
```

### Step 6: Guide Through TODOs

Help the user fill in remaining TODOs:
1. **Contact info** — clerk email, city hall address, phone
2. **Meeting archives** — platform-specific archive URLs or IDs
3. **HUD grantee** — look up at https://www.hudexchange.info/grantees/allocations-awards/
4. **Zip codes** — city zip codes for geographic filtering
5. **Neighborhoods** — major neighborhood names
6. **Budget source** — opengov or municipal_portal
7. **Transcripts** — youtube playlist ID or granicus source

### Step 7: Deploy (when ready)

```bash
source civicos-env/bin/activate && civicos-deploy city-<slug> --dry-run
source civicos-env/bin/activate && civicos-deploy city-<slug>
```

## Notes

- Platform detection works best for Legistar and ProudCity sites. Granicus uses separate subdomains (e.g., `city.granicus.com`) that aren't discoverable from the main website — use `--platform granicus` if known.
- The generated config passes validation but has many TODOs. A city is deployment-ready only after TODOs are filled in.
- Existing configs in `data/jurisdictions/` serve as reference templates.
