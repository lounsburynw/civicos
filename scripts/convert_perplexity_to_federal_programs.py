#!/usr/bin/env python3
"""
Convert Perplexity audit trail responses into structured federal program JSON files.
"""

import json
import os
import re
from datetime import datetime

def extract_program_info(response_text, program_name):
    """Extract structured information from Perplexity response text."""

    # Helper function to extract section content
    def extract_section(pattern, text):
        match = re.search(pattern, text, re.DOTALL)
        if match:
            content = match.group(1).strip()
            # Extract bullet points
            bullets = []
            for line in content.split('\n'):
                line = line.strip()
                if line.startswith('- **') or line.startswith('- '):
                    # Remove markdown formatting
                    clean_line = re.sub(r'\[.*?\]\(.*?\)', '', line)  # Remove links
                    clean_line = re.sub(r'\*\*(.*?)\*\*', r'\1', clean_line)  # Remove bold
                    clean_line = clean_line.lstrip('- ').strip()
                    if clean_line:
                        bullets.append(clean_line)
            return bullets
        return []

    # Extract sections
    eligible_activities = extract_section(r'## 2\. Eligible Activities.*?\n(.*?)(?=## 3\.)', response_text)
    if not eligible_activities:
        eligible_activities = extract_section(r'## Eligible Activities.*?\n(.*?)(?=## )', response_text)

    citizen_participation = extract_section(r'## 3\. Citizen Participation Requirements.*?\n(.*?)(?=## 4\.)', response_text)
    if not citizen_participation:
        citizen_participation = extract_section(r'## Citizen Participation Requirements.*?\n(.*?)(?=## )', response_text)

    leverage_points = extract_section(r'## 4\. Leverage Points for Residents.*?\n(.*?)(?=## 5\.)', response_text)
    if not leverage_points:
        leverage_points = extract_section(r'## Leverage Points for Residents.*?\n(.*?)(?=## )', response_text)

    # Extract official URLs
    official_url_match = re.search(r'Official federal program URL.*?\[?(https?://[^\s\)]+)', response_text)
    official_url = official_url_match.group(1) if official_url_match else ""

    # Extract agency
    agency_match = re.search(r'\*\*Administering federal agency:\*\* (.*?)[\[\n]', response_text)
    agency = agency_match.group(1).strip() if agency_match else ""

    # Extract description
    desc_match = re.search(r'\*\*Description.*?:\*\* (.*?)(?=\n\n##)', response_text, re.DOTALL)
    description = desc_match.group(1).strip() if desc_match else ""
    description = re.sub(r'\[.*?\]\(.*?\)', '', description)  # Remove citations

    return {
        "program_name": program_name,
        "administering_agency": agency,
        "description": description,
        "eligible_activities": eligible_activities[:7],  # Limit to 7
        "local_compliance_required": True,
        "annual_reporting": True,
        "resident_input_opportunities": citizen_participation[:5] if citizen_participation else [],
        "leverage_point": ". ".join(leverage_points[:2]) if leverage_points else "",
        "official_url": official_url
    }

def process_audit_file(audit_file, topic):
    """Process a Perplexity audit file and return structured programs."""
    with open(audit_file) as f:
        data = json.load(f)

    programs = {}

    for query in data.get('queries', []):
        program_name = query['program_name']
        response = query['response']

        # Create program ID (lowercase, no special chars)
        program_id = re.sub(r'[^a-z0-9]+', '_', program_name.lower()).strip('_')

        program_info = extract_program_info(response, program_name)
        programs[program_id] = program_info

    return programs

def main():
    """Main conversion process."""

    # Process each topic
    topics = {
        'housing': 'data/federal_programs/housing_perplexity_audit.json',
        'transportation': 'data/federal_programs/transportation_perplexity_audit.json',
        'environment': 'data/federal_programs/environment_perplexity_audit.json'
    }

    for topic, audit_file in topics.items():
        if not os.path.exists(audit_file):
            print(f"⚠️  Skipping {topic} - audit file not found")
            continue

        print(f"\n📋 Processing {topic}...")

        programs = process_audit_file(audit_file, topic)

        # Load existing file if it exists
        output_file = f'data/federal_programs/{topic}.json'
        if os.path.exists(output_file):
            with open(output_file) as f:
                existing_data = json.load(f)
        else:
            existing_data = {
                "jurisdiction": "federal",
                "topic": topic,
                "last_updated": datetime.now().isoformat(),
                "data_sources": [
                    "Perplexity Sonar Pro API",
                    "Federal agency websites (cited by Perplexity)"
                ],
                "programs": {}
            }

        # Merge programs (new ones only)
        for program_id, program_info in programs.items():
            if program_id not in existing_data['programs']:
                existing_data['programs'][program_id] = program_info
                print(f"  ✅ Added: {program_info['program_name']}")
            else:
                # Update existing program
                existing_data['programs'][program_id] = program_info
                print(f"  🔄 Updated: {program_info['program_name']}")

        # Update timestamp
        existing_data['last_updated'] = datetime.now().isoformat()

        # Write back
        with open(output_file, 'w') as f:
            json.dump(existing_data, f, indent=2)

        print(f"  💾 Saved to: {output_file}")

    print("\n✅ Conversion complete!")

if __name__ == '__main__':
    main()
