#!/usr/bin/env python3
"""
Automated housing legislative context generation using Perplexity API.
Generates draft files for human verification before commit.
"""

import json
import os
import requests
from datetime import datetime
from typing import Dict, List, Any

PERPLEXITY_API_KEY = os.environ.get('PERPLEXITY_API_KEY')

def query_perplexity(prompt: str, model: str = "sonar-pro") -> Dict[str, Any]:
    """Query Perplexity API and return full response."""
    response = requests.post(
        'https://api.perplexity.ai/chat/completions',
        headers={
            'Authorization': f'Bearer {PERPLEXITY_API_KEY}',
            'Content-Type': 'application/json'
        },
        json={
            'model': model,
            'messages': [{'role': 'user', 'content': prompt}],
            'max_tokens': 4000,
            'temperature': 0.2
        },
        timeout=120
    )
    response.raise_for_status()
    return response.json()

def discover_state_bills() -> Dict[str, Any]:
    """Discover California housing bills with full metadata."""
    prompt = """For California housing legislation from 2017-2025, provide COMPLETE metadata in JSON format for the following bills:
1. SB 9 (2021) - HOME Act
2. AB 2011 (2022) - Affordable Housing streamlining
3. SB 35 (2017) - Streamlined approvals
4. SB 330 (2019) - Housing Crisis Act
5. AB 1287 (2023) - Density Bonus expansion
6. SB 1123 (2024) - Vacant lot subdivision

For each bill, provide:
{
  "bill_id": "ca-sb9",
  "bill_number": "SB 9",
  "bill_name": "California Housing Opportunity and More Efficiency (HOME) Act",
  "year_enacted": 2021,
  "enactment_date": "2021-09-16",
  "status": "Active",
  "local_implementation_required": true,
  "local_deadline": "2022-01-01",
  "summary": "Brief 1-2 sentence summary",
  "leverage_point": "How residents can use this at local meetings",
  "official_url": "https://leginfo.legislature.ca.gov/faces/billTextClient.xhtml?bill_id=...",
  "keywords": ["housing", "affordable housing", "zoning", "density", "ADU"]
}

Return ONLY valid JSON array of bill objects. Use actual verified dates from leginfo.legislature.ca.gov."""

    print("Querying Perplexity for state bill metadata...")
    result = query_perplexity(prompt)

    return {
        'content': result['choices'][0]['message']['content'],
        'citations': result.get('citations', []),
        'cost': result['usage']['cost']['total_cost']
    }

def discover_federal_programs() -> Dict[str, Any]:
    """Discover federal housing programs relevant to California cities."""
    prompt = """For federal housing programs relevant to California local governments, provide COMPLETE metadata in JSON format for:
1. Community Development Block Grant (CDBG)
2. HOME Investment Partnerships Program
3. Any other major federal programs for affordable housing

For each program, provide:
{
  "program_id": "cdbg",
  "program_name": "Community Development Block Grant",
  "administering_agency": "HUD",
  "description": "2-3 sentence description",
  "eligible_activities": ["affordable housing", "infrastructure", "public services"],
  "local_compliance_required": true,
  "annual_reporting": true,
  "resident_input_opportunities": ["Annual Action Plan public comment", "Consolidated Plan hearings"],
  "leverage_point": "How residents can influence funding allocation",
  "official_url": "https://www.hud.gov/program_offices/comm_planning/communitydevelopment/programs",
  "keywords": ["affordable housing", "community development", "federal funding"]
}

Return ONLY valid JSON array of program objects. Include specific citizen participation requirements."""

    print("Querying Perplexity for federal programs...")
    result = query_perplexity(prompt)

    return {
        'content': result['choices'][0]['message']['content'],
        'citations': result.get('citations', []),
        'cost': result['usage']['cost']['total_cost']
    }

def parse_json_from_response(content: str) -> Any:
    """Extract JSON from response (handles markdown code blocks)."""
    # Try to find JSON in markdown code blocks
    if '```json' in content:
        start = content.find('```json') + 7
        end = content.find('```', start)
        content = content[start:end].strip()
    elif '```' in content:
        start = content.find('```') + 3
        end = content.find('```', start)
        content = content[start:end].strip()

    # Try to parse as JSON
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        # If direct parse fails, try to find JSON array/object
        for start_char, end_char in [('[', ']'), ('{', '}')]:
            start = content.find(start_char)
            end = content.rfind(end_char)
            if start != -1 and end != -1:
                try:
                    return json.loads(content[start:end+1])
                except json.JSONDecodeError:
                    continue
        raise ValueError(f"Could not extract JSON from response: {content[:200]}...")

def generate_state_legislation_json(bills_data: Dict[str, Any]) -> Dict[str, Any]:
    """Generate california_housing.json from Perplexity data."""
    try:
        bills = parse_json_from_response(bills_data['content'])
    except (json.JSONDecodeError, ValueError) as e:
        print(f"WARNING: Could not parse Perplexity response as JSON: {e}")
        print("Using manual structure instead...")
        # Fallback: use the bills from initial discovery
        bills = []

    state_legislation = {}
    for bill in bills:
        bill_id = bill.get('bill_id', f"ca-{bill.get('bill_number', 'unknown').lower().replace(' ', '')}")
        state_legislation[bill_id] = {
            "bill": bill.get('bill_name', bill.get('bill_number', 'Unknown')),
            "status": bill.get('status', 'Active'),
            "enacted": bill.get('enactment_date'),
            "local_implementation_required": bill.get('local_implementation_required', True),
            "local_deadline": bill.get('local_deadline'),
            "leverage_point": bill.get('leverage_point', ''),
            "official_url": bill.get('official_url', ''),
            "summary": bill.get('summary', ''),
            "keywords": bill.get('keywords', ["housing", "affordable housing"])
        }

    return {
        "jurisdiction": "california",
        "topic": "housing",
        "last_updated": datetime.now().isoformat(),
        "data_sources": [
            "Perplexity Sonar Pro API",
            "leginfo.legislature.ca.gov (cited by Perplexity)",
            "NEEDS HUMAN VERIFICATION"
        ],
        "verification_status": "DRAFT - NOT VERIFIED",
        "perplexity_citations": bills_data['citations'],
        "state_legislation": state_legislation,
        "federal_programs": {}
    }

def generate_federal_programs_json(programs_data: Dict[str, Any]) -> Dict[str, Any]:
    """Generate federal_programs/housing.json from Perplexity data."""
    try:
        programs = parse_json_from_response(programs_data['content'])
    except (json.JSONDecodeError, ValueError) as e:
        print(f"WARNING: Could not parse Perplexity response as JSON: {e}")
        programs = []

    federal_programs = {}
    for program in programs:
        program_id = program.get('program_id', program.get('program_name', 'unknown').lower().replace(' ', '-'))
        federal_programs[program_id] = {
            "program_name": program.get('program_name', 'Unknown'),
            "administering_agency": program.get('administering_agency', ''),
            "description": program.get('description', ''),
            "eligible_activities": program.get('eligible_activities', []),
            "local_compliance_required": program.get('local_compliance_required', True),
            "annual_reporting": program.get('annual_reporting', True),
            "resident_input_opportunities": program.get('resident_input_opportunities', []),
            "leverage_point": program.get('leverage_point', ''),
            "official_url": program.get('official_url', ''),
            "keywords": program.get('keywords', ["affordable housing", "federal funding"])
        }

    return {
        "jurisdiction": "federal",
        "topic": "housing",
        "last_updated": datetime.now().isoformat(),
        "data_sources": [
            "Perplexity Sonar Pro API",
            "HUD.gov (cited by Perplexity)",
            "NEEDS HUMAN VERIFICATION"
        ],
        "verification_status": "DRAFT - NOT VERIFIED",
        "perplexity_citations": programs_data['citations'],
        "programs": federal_programs
    }

def generate_verification_checklist(state_data: Dict, federal_data: Dict) -> str:
    """Generate markdown checklist for human verification."""
    checklist = f"""# Housing Legislative Context - Verification Checklist

**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M')}
**Status**: DRAFT - REQUIRES HUMAN VERIFICATION

## Instructions

Before committing these files, verify each item below:

### State Legislation ({len(state_data['state_legislation'])} bills)

"""

    for bill_id, bill in state_data['state_legislation'].items():
        checklist += f"""
#### {bill_id.upper()} - {bill['bill']}

- [ ] Verify bill number and name at {bill['official_url'] or 'leginfo.legislature.ca.gov'}
- [ ] Verify enactment date: {bill['enacted'] or 'MISSING'}
- [ ] Verify local deadline: {bill['local_deadline'] or 'MISSING'}
- [ ] Verify summary accuracy
- [ ] Verify leverage point is actionable
- [ ] Check official URL works
- [ ] Apply 3-part actionability test:
  - [ ] Local implementation required? {bill['local_implementation_required']}
  - [ ] Specific deadline exists? {bill['local_deadline'] or 'NO'}
  - [ ] Clear resident leverage point? {bool(bill['leverage_point'])}

**Notes**:
```
[Your verification notes here]
```
---
"""

    checklist += f"""
### Federal Programs ({len(federal_data['programs'])} programs)

"""

    for prog_id, prog in federal_data['programs'].items():
        checklist += f"""
#### {prog_id.upper()} - {prog['program_name']}

- [ ] Verify program name and agency at {prog['official_url'] or 'HUD.gov'}
- [ ] Verify citizen participation requirements
- [ ] Verify eligible activities list
- [ ] Check official URL works

**Notes**:
```
[Your verification notes here]
```
---
"""

    checklist += f"""
## Perplexity Citations

### State Legislation
{chr(10).join(f"{i+1}. {cite}" for i, cite in enumerate(state_data.get('perplexity_citations', [])))}

### Federal Programs
{chr(10).join(f"{i+1}. {cite}" for i, cite in enumerate(federal_data.get('perplexity_citations', [])))}

## Final Sign-off

- [ ] All bills verified against leginfo.legislature.ca.gov
- [ ] All federal programs verified against official sources
- [ ] All 3-part actionability tests passed
- [ ] All URLs tested and working
- [ ] Ready to commit with audit trail

**Verified by**: _______________
**Date**: _______________
"""

    return checklist

def main():
    """Main automation flow."""
    if not PERPLEXITY_API_KEY:
        print("ERROR: PERPLEXITY_API_KEY not set")
        return 1

    total_cost = 0.0

    # Step 1: Discover state bills (or load from cache)
    print("\n" + "="*80)
    print("STEP 1: Discovering California state bills")
    print("="*80)

    cache_file = 'data/legislative_context/.cache_state_bills.json'
    if os.path.exists(cache_file):
        print(f"Loading from cache: {cache_file}")
        with open(cache_file, 'r') as f:
            bills_data = json.load(f)
        print("✓ Loaded cached state legislation data")
    else:
        bills_data = discover_state_bills()
        total_cost += bills_data['cost']
        print(f"✓ Found state legislation data (cost: ${bills_data['cost']:.4f})")
        # Cache the result
        os.makedirs(os.path.dirname(cache_file), exist_ok=True)
        with open(cache_file, 'w') as f:
            json.dump(bills_data, f, indent=2)
        print(f"✓ Cached to: {cache_file}")

    # Step 2: Discover federal programs (or load from cache)
    print("\n" + "="*80)
    print("STEP 2: Discovering federal housing programs")
    print("="*80)

    cache_file_federal = 'data/legislative_context/.cache_federal_programs.json'
    if os.path.exists(cache_file_federal):
        print(f"Loading from cache: {cache_file_federal}")
        with open(cache_file_federal, 'r') as f:
            programs_data = json.load(f)
        print("✓ Loaded cached federal program data")
    else:
        try:
            programs_data = discover_federal_programs()
            total_cost += programs_data['cost']
            print(f"✓ Found federal program data (cost: ${programs_data['cost']:.4f})")
            # Cache the result
            with open(cache_file_federal, 'w') as f:
                json.dump(programs_data, f, indent=2)
            print(f"✓ Cached to: {cache_file_federal}")
        except requests.exceptions.Timeout:
            print("⚠ Timeout on federal programs query - using minimal fallback")
            programs_data = {
                'content': '[]',
                'citations': [],
                'cost': 0.0
            }
            print("NOTE: Re-run script to retry federal programs query")

    # Step 3: Generate draft JSONs
    print("\n" + "="*80)
    print("STEP 3: Generating draft JSON files")
    print("="*80)

    state_json = generate_state_legislation_json(bills_data)
    federal_json = generate_federal_programs_json(programs_data)

    # Save state legislation
    state_path = 'data/legislative_context/california_housing.json.DRAFT'
    os.makedirs(os.path.dirname(state_path), exist_ok=True)
    with open(state_path, 'w') as f:
        json.dump(state_json, f, indent=2)
    print(f"✓ Saved: {state_path}")

    # Save federal programs
    federal_path = 'data/federal_programs/housing.json.DRAFT'
    os.makedirs(os.path.dirname(federal_path), exist_ok=True)
    with open(federal_path, 'w') as f:
        json.dump(federal_json, f, indent=2)
    print(f"✓ Saved: {federal_path}")

    # Save Perplexity raw responses for audit trail
    audit_path = 'data/legislative_context/housing_perplexity_audit.json'
    with open(audit_path, 'w') as f:
        json.dump({
            'generated_at': datetime.now().isoformat(),
            'total_cost': total_cost,
            'state_bills': {
                'response': bills_data['content'],
                'citations': bills_data['citations'],
                'cost': bills_data['cost']
            },
            'federal_programs': {
                'response': programs_data['content'],
                'citations': programs_data['citations'],
                'cost': programs_data['cost']
            }
        }, f, indent=2)
    print(f"✓ Saved audit trail: {audit_path}")

    # Step 4: Generate verification checklist
    print("\n" + "="*80)
    print("STEP 4: Generating verification checklist")
    print("="*80)

    checklist = generate_verification_checklist(state_json, federal_json)
    checklist_path = 'data/legislative_context/VERIFICATION_CHECKLIST.md'
    with open(checklist_path, 'w') as f:
        f.write(checklist)
    print(f"✓ Saved: {checklist_path}")

    # Summary
    print("\n" + "="*80)
    print("AUTOMATION COMPLETE")
    print("="*80)
    print(f"Total Perplexity cost: ${total_cost:.4f}")
    print(f"State bills: {len(state_json['state_legislation'])}")
    print(f"Federal programs: {len(federal_json['programs'])}")
    print()
    print("Next steps:")
    print("1. Review DRAFT files:")
    print(f"   - {state_path}")
    print(f"   - {federal_path}")
    print("2. Complete verification checklist:")
    print(f"   - {checklist_path}")
    print("3. Remove .DRAFT suffix when verified")
    print("4. Commit with audit trail")
    print()

    return 0

if __name__ == '__main__':
    exit(main())
