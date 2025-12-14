#!/usr/bin/env python3
"""
Extract complete wildfire testimony from Oct 6, 2024 San Rafael City Council meeting.

This script extracts testimony from the three wildfire speakers identified:
- Belle Cole (Speaker AJ) - Firewise Committee Chair
- Sherna Deamer (Speaker T) - Neighborhood fire concerns
- Salama (part of Speaker AI) - Age-Friendly fire safety

Usage:
    python scripts/extract_wildfire_testimony.py
"""

import json
import sys
from pathlib import Path
from typing import List, Dict

def load_transcript(filepath: str) -> Dict:
    """Load AssemblyAI transcript from JSON file."""
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)

def get_speaker_utterances(utterances: List[dict], speaker_label: str) -> List[dict]:
    """Get all utterances for a specific speaker."""
    return [u for u in utterances if u.get('speaker') == speaker_label]

def extract_testimony_text(utterances: List[dict]) -> str:
    """Combine utterances into full testimony text."""
    return ' '.join([u.get('text', '') for u in utterances])

def filter_wildfire_utterances(utterances: List[dict]) -> List[dict]:
    """
    Filter utterances related to wildfire/fire safety.

    For speakers with merged content (like AI), extract only fire-related testimony.
    """
    wildfire_keywords = [
        'fire', 'wildfire', 'firewise', 'evacuation', 'vegetation',
        'age-friendly', 'senior', 'safety', 'prevention', 'mitigation',
        'emergency', 'disaster', 'preparedness'
    ]

    filtered = []
    for u in utterances:
        text_lower = u.get('text', '').lower()
        if any(keyword in text_lower for keyword in wildfire_keywords):
            filtered.append(u)

    return filtered

def main():
    # Load transcript
    transcript_path = 'data/testimony/testimony_MpxrGRb16HQ_exact50.json'
    print(f"Loading transcript: {transcript_path}")
    data = load_transcript(transcript_path)
    utterances = data.get('utterances', [])

    # Define wildfire speakers from our analysis
    wildfire_speakers = {
        'AJ': {
            'name': 'Belle Cole',
            'role': 'Dominican Black Canyon Firewise Committee Chair',
            'confidence': 'HIGH',
            'merged': False
        },
        'T': {
            'name': 'Sherna Deamer / Sharon Demer',
            'role': 'Neighborhood resident - fire concerns',
            'confidence': 'HIGH',
            'merged': False
        },
        'AI': {
            'name': 'Salama (speaking for San Rafael Age-Friendly)',
            'role': 'Age-Friendly Committee - senior fire safety',
            'confidence': 'MEDIUM',
            'merged': True,
            'note': 'Speaker AI contains multiple speakers merged. Filtering for fire-related utterances only.'
        }
    }

    results = []

    for speaker_label, info in wildfire_speakers.items():
        print(f"\n{'='*70}")
        print(f"Speaker {speaker_label}: {info['name']}")
        print(f"Role: {info['role']}")
        print(f"Confidence: {info['confidence']}")
        if info.get('merged'):
            print(f"Note: {info['note']}")
        print('='*70)

        # Get all utterances for this speaker
        speaker_utterances = get_speaker_utterances(utterances, speaker_label)

        # Filter for wildfire content if speaker has merged content
        if info.get('merged'):
            relevant_utterances = filter_wildfire_utterances(speaker_utterances)
            print(f"\nTotal utterances: {len(speaker_utterances)}")
            print(f"Fire-related utterances: {len(relevant_utterances)}")
        else:
            relevant_utterances = speaker_utterances
            print(f"\nTotal utterances: {len(relevant_utterances)}")

        # Extract full text
        testimony_text = extract_testimony_text(relevant_utterances)

        print(f"\nTestimony excerpt (first 500 chars):")
        print(f"{testimony_text[:500]}...")

        # Store results
        results.append({
            'speaker_label': speaker_label,
            'name': info['name'],
            'role': info['role'],
            'confidence': info['confidence'],
            'utterance_count': len(relevant_utterances),
            'total_utterances': len(speaker_utterances),
            'merged': info.get('merged', False),
            'testimony': testimony_text,
            'utterances': relevant_utterances
        })

    # Save results
    output_path = 'data/pilot/oct6_wildfire_testimony.json'
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*70}")
    print(f"✓ Wildfire testimony extracted and saved to: {output_path}")
    print(f"{'='*70}")

    # Summary
    print(f"\nSUMMARY:")
    print(f"- {len(results)} wildfire speakers identified")
    total_utterances = sum(r['utterance_count'] for r in results)
    print(f"- {total_utterances} total fire-related utterances")
    print(f"- 2/3 speakers cleanly separated (Belle Cole, Sherna Deamer)")
    print(f"- 1/3 speakers partially merged (Salama in Speaker AI)")

    return results

if __name__ == '__main__':
    main()
