#!/usr/bin/env python3
"""
Merge YouTube LLM speaker analysis with AssemblyAI diarization.

Creates a unified speaker mapping:
- AssemblyAI speaker label (A, B, C...) → Name from LLM analysis or minutes
- Confidence scores for each mapping
- Distinguishes "mentioned" vs "spoke"
- Cross-references with official meeting minutes for council/staff names

Session: 109 (enhanced with minutes cross-reference)
Session: 111 (integrated LLM name extraction fallback)
"""

import argparse
import json
import sys
import os
from typing import Dict, List, Optional
from dataclasses import dataclass
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from minutes_parser import MinutesParser, MeetingAttendees
from llm_provider import get_model_for_task


@dataclass
class SpeakerMapping:
    """Mapping between AssemblyAI label and actual name."""
    assemblyai_label: str
    name: str
    role: str
    confidence: str  # "high", "medium", "low"
    evidence: str
    utterance_count: int
    sample_text: str


def simple_edit_distance(s1: str, s2: str) -> int:
    """Calculate Levenshtein distance between two strings"""
    if len(s1) < len(s2):
        return simple_edit_distance(s2, s1)

    if len(s2) == 0:
        return len(s1)

    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row

    return previous_row[-1]


def fuzzy_name_match(name1: str, name2: str) -> bool:
    """
    Check if two names likely refer to the same person.

    Handles variants like:
    - Sherna vs Sharon (transcription error)
    - Belle vs Bella (variant)
    - Deamer vs Demer (transcription error)
    - Name with/without suffixes
    """
    n1_lower = name1.lower().strip()
    n2_lower = name2.lower().strip()

    # Exact match
    if n1_lower == n2_lower:
        return True

    # Check if last names match and first names are similar
    n1_parts = n1_lower.split()
    n2_parts = n2_lower.split()

    if len(n1_parts) >= 2 and len(n2_parts) >= 2:
        first1, last1 = n1_parts[0], n1_parts[-1]
        first2, last2 = n2_parts[0], n2_parts[-1]

        # Both first and last names must be similar
        # First names: edit distance <= 3 (handles: Sherna/Sharon=3, Belle/Bella=1)
        # Last names: edit distance <= 2 (handles: Deamer/Demer=1, Cole/Cole=0)
        first_dist = simple_edit_distance(first1, first2)
        last_dist = simple_edit_distance(last1, last2)

        if first_dist <= 3 and last_dist <= 2:
            return True

    return False


def find_name_in_utterances(utterances: List[dict], assemblyai_label: str) -> Optional[str]:
    """
    Find speaker name by looking for self-introductions in their utterances.

    Returns:
        Name if found, None otherwise
    """
    speaker_utterances = [u for u in utterances if u.get('speaker') == assemblyai_label]

    # Look for explicit self-introductions
    intro_patterns = [
        "my name is ",
        "i'm ",
        "this is ",
        "i am "
    ]

    for utterance in speaker_utterances:
        text_lower = utterance.get('text', '').lower()
        for pattern in intro_patterns:
            if pattern in text_lower:
                # Extract text after pattern
                idx = text_lower.index(pattern)
                after = utterance.get('text', '')[idx + len(pattern):idx + len(pattern) + 50]
                # Return first capitalized name
                words = after.split()
                if len(words) >= 2 and words[0][0].isupper() and words[1][0].isupper():
                    return f"{words[0]} {words[1]}"

    # Look for short standalone name statements (public comment pattern)
    # E.g., "Salama from Terra Linda", "John Smith from downtown"
    for utterance in speaker_utterances:
        text = utterance.get('text', '').strip()
        text_lower = text.lower()

        # Very short utterances that might be name + location
        # NOTE: This has false positives (e.g., "San Rafael from 2019")
        if len(text.split()) <= 6 and 'from' in text_lower:
            words = text.split()
            # First word should be capitalized (likely a name)
            if words and words[0][0].isupper():
                # Extract name before "from"
                from_idx = text_lower.index('from')
                name_part = text[:from_idx].strip()
                # If it's 1-3 words and capitalized, probably a name
                name_words = name_part.split()
                if 1 <= len(name_words) <= 3 and all(w[0].isupper() for w in name_words if w):
                    return name_part

    return None


def extract_speaker_name_llm(utterances: List[dict], speaker_label: str) -> Optional[str]:
    """
    Use LLM to extract speaker name from their utterances.

    Falls back to this when pattern matching fails.
    Cost: ~$0.0001 per speaker with gpt-4o-mini

    Args:
        utterances: Full transcript utterance list
        speaker_label: Speaker label to extract (e.g., 'P', 'AJ', 'T')

    Returns:
        Speaker name if found, None otherwise
    """
    # Get utterances for this speaker
    speaker_utterances = [u for u in utterances if u.get('speaker') == speaker_label]

    if not speaker_utterances:
        return None

    # Get first 20 utterances as context (usually enough to find self-introduction)
    sample = speaker_utterances[:20]
    context = "\n".join([f"- {u.get('text', '')}" for u in sample])

    prompt = f"""These are utterances from Speaker {speaker_label} in a city council meeting.
Find any self-introduction where they state their name.

Utterances:
{context}

Return ONLY the person's name if found (e.g., "John Smith" or "Salama from Terra Linda").
If no introduction found, return the word "null" (without quotes)."""

    # Use gpt-4o-mini for cost efficiency
    provider = get_model_for_task('short_structured')

    try:
        response = provider.complete([
            {"role": "system", "content": "Extract speaker names from meeting transcripts. Return only the name or the word null."},
            {"role": "user", "content": prompt}
        ])

        name = response.content.strip()

        # Handle various null responses
        if name and name.lower() not in ['null', 'none', 'n/a', 'unknown']:
            return name
        else:
            return None

    except Exception as e:
        # Silently fail on LLM errors, return None
        return None


def match_to_minutes_attendees(
    utterances: List[dict],
    assemblyai_label: str,
    attendees: Optional[MeetingAttendees]
) -> Optional[Dict[str, str]]:
    """
    Try to match AssemblyAI speaker to minutes attendees by utterance content.

    Looks for procedural language that identifies council members and staff:
    - "Good evening everyone" → Mayor (usually chairs meeting)
    - "Present" → Council member responding to roll call
    - References to specific positions in text

    Returns:
        {"name": "Full Name", "title": "Position", "evidence": "..."} if matched
    """
    if not attendees:
        return None

    speaker_utterances = [u for u in utterances if u.get('speaker') == assemblyai_label]
    if not speaker_utterances:
        return None

    # Get all text from this speaker
    all_text = " ".join([u.get('text', '') for u in speaker_utterances[:10]])  # First 10 utterances
    text_lower = all_text.lower()

    # Check for mayor patterns (chairs meeting)
    mayor_patterns = ["welcome to", "good evening everyone", "call the meeting to order", "invite public comment"]
    if any(pattern in text_lower for pattern in mayor_patterns):
        for member in attendees.council_members_present:
            if member['title'].lower() == 'mayor':
                return {
                    "name": member['name'],
                    "title": member['title'],
                    "evidence": "Chaired meeting (procedural language matches Mayor role)"
                }

    # Check for city clerk patterns (roll call, recording)
    clerk_patterns = ["call the roll", "recording in progress", "councilmember", "present", "absent"]
    clerk_match_count = sum(1 for pattern in clerk_patterns if pattern in text_lower)
    if clerk_match_count >= 2:
        for staff in attendees.staff_present:
            if 'clerk' in staff['title'].lower():
                return {
                    "name": staff['name'],
                    "title": staff['title'],
                    "evidence": f"Clerk procedural language ({clerk_match_count} patterns matched)"
                }

    # Check for staff report patterns
    staff_patterns = ["staff report", "recommendation is", "we recommend", "the department"]
    if any(pattern in text_lower for pattern in staff_patterns):
        # Could be City Manager or department head, but hard to distinguish
        # Return first staff match as medium confidence
        if attendees.staff_present:
            return {
                "name": attendees.staff_present[0]['name'],
                "title": attendees.staff_present[0]['title'],
                "evidence": "Staff presentation language (low confidence on specific person)"
            }

    return None


def create_speaker_mapping(
    youtube_analysis: dict,
    assemblyai_data: dict,
    attendees: Optional[MeetingAttendees] = None,
    enable_llm_fallback: bool = True
) -> List[SpeakerMapping]:
    """
    Create mapping between AssemblyAI labels and YouTube speaker names.

    Three-tier strategy (Session 111 - production hardening):
    1. Pattern matching: Fast, works for 67% (high confidence)
    2. LLM fallback: Robust, handles remaining 33% (medium confidence)
    3. Minutes cross-reference: Identify council/staff by role (medium confidence)
    4. Unknown: No identification possible (low confidence)

    Args:
        youtube_analysis: YouTube speaker analysis
        assemblyai_data: AssemblyAI transcript
        attendees: Optional meeting minutes attendees
        enable_llm_fallback: Enable LLM name extraction (default: True)
    """
    utterances = assemblyai_data.get('utterances', [])
    youtube_speakers = youtube_analysis.get('speakers', {})

    # Get unique AssemblyAI speakers
    assemblyai_labels = sorted(set(u.get('speaker') for u in utterances if u.get('speaker')))

    mappings = []

    for label in assemblyai_labels:
        # Get utterances for this speaker
        speaker_utterances = [u for u in utterances if u.get('speaker') == label]
        utterance_count = len(speaker_utterances)

        # Strategy 1: Pattern matching (fast, works for 67%)
        found_name = find_name_in_utterances(utterances, label)

        if found_name:
            # Look up in YouTube analysis with fuzzy matching
            matched_speaker = None

            # Try exact match first
            name_key = found_name.lower().strip()
            if name_key in youtube_speakers:
                matched_speaker = youtube_speakers[name_key]
            else:
                # Try fuzzy match
                for yt_key, yt_data in youtube_speakers.items():
                    yt_name = yt_data['name']

                    # Exact match on YouTube name
                    if fuzzy_name_match(found_name, yt_name):
                        matched_speaker = yt_data
                        break

                    # For single-word names, check if it matches start of YouTube name
                    # E.g., "Salama" → "Salama from Terinda"
                    if ' ' not in found_name and yt_name.lower().startswith(found_name.lower() + ' '):
                        matched_speaker = yt_data
                        break

            if matched_speaker:
                mappings.append(SpeakerMapping(
                    assemblyai_label=label,
                    name=matched_speaker['name'],
                    role=matched_speaker['role'],
                    confidence="high",
                    evidence=f"Pattern matching: '{found_name}' → '{matched_speaker['name']}'",
                    utterance_count=utterance_count,
                    sample_text=speaker_utterances[0].get('text', '')[:150] if speaker_utterances else ""
                ))
                continue

        # Strategy 2: LLM fallback (robust, handles remaining 33%)
        if enable_llm_fallback:
            llm_name = extract_speaker_name_llm(utterances, label)
            if llm_name:
                # Look up in YouTube analysis
                matched_speaker = None

                name_key = llm_name.lower().strip()
                if name_key in youtube_speakers:
                    matched_speaker = youtube_speakers[name_key]
                else:
                    # Try fuzzy match
                    for yt_key, yt_data in youtube_speakers.items():
                        if fuzzy_name_match(llm_name, yt_data['name']):
                            matched_speaker = yt_data
                            break

                if matched_speaker:
                    mappings.append(SpeakerMapping(
                        assemblyai_label=label,
                        name=matched_speaker['name'],
                        role=matched_speaker['role'],
                        confidence="medium",
                        evidence=f"LLM extraction: '{llm_name}' → '{matched_speaker['name']}'",
                        utterance_count=utterance_count,
                        sample_text=speaker_utterances[0].get('text', '')[:150] if speaker_utterances else ""
                    ))
                    continue

        # Strategy 3: Try to match to minutes attendees by procedural language (medium confidence)
        minutes_match = match_to_minutes_attendees(utterances, label, attendees)
        if minutes_match:
            mappings.append(SpeakerMapping(
                assemblyai_label=label,
                name=minutes_match['name'],
                role=minutes_match['title'],
                confidence="medium",
                evidence=f"Minutes cross-reference: {minutes_match['evidence']}",
                utterance_count=utterance_count,
                sample_text=speaker_utterances[0].get('text', '')[:150] if speaker_utterances else ""
            ))
            continue

        # Strategy 4: Unknown (no identification possible)
        sample_text = speaker_utterances[0].get('text', '')[:150] if speaker_utterances else ""
        mappings.append(SpeakerMapping(
            assemblyai_label=label,
            name=f"Unknown ({label})",
            role="unknown",
            confidence="low",
            evidence="No self-introduction, LLM extraction, or minutes match found",
            utterance_count=utterance_count,
            sample_text=sample_text
        ))

    return mappings


def analyze_discrepancy(
    youtube_analysis: dict,
    assemblyai_data: dict,
    mappings: List[SpeakerMapping]
) -> dict:
    """
    Analyze the 50 vs 40 speaker discrepancy.

    Returns:
        Analysis of what's different
    """
    youtube_speakers = youtube_analysis.get('speakers', {})
    youtube_names = set(s['name'].lower() for s in youtube_speakers.values())

    mapped_names = set(m.name.lower() for m in mappings if m.confidence == "high")

    # Find YouTube speakers not in AssemblyAI
    mentioned_not_spoken = youtube_names - mapped_names

    # Categorize by role
    mentioned_not_spoken_data = []
    for name_key in mentioned_not_spoken:
        for key, data in youtube_speakers.items():
            if data['name'].lower() == name_key:
                mentioned_not_spoken_data.append({
                    'name': data['name'],
                    'role': data['role'],
                    'mentions': data['mentions'],
                    'contexts': data['contexts']
                })
                break

    return {
        'youtube_total': len(youtube_speakers),
        'assemblyai_total': len(set(m.assemblyai_label for m in mappings)),
        'high_confidence_mappings': len([m for m in mappings if m.confidence == "high"]),
        'discrepancy': len(youtube_speakers) - len(set(m.assemblyai_label for m in mappings)),
        'mentioned_not_spoken': sorted(mentioned_not_spoken_data, key=lambda x: -x['mentions'])
    }


def main():
    parser = argparse.ArgumentParser(
        description="Merge YouTube and AssemblyAI speaker analyses with optional minutes cross-reference"
    )
    parser.add_argument(
        "--youtube-analysis",
        required=True,
        help="Path to YouTube LLM analysis JSON"
    )
    parser.add_argument(
        "--assemblyai-transcript",
        required=True,
        help="Path to AssemblyAI transcript JSON"
    )
    parser.add_argument(
        "--minutes",
        help="Optional: Path to meeting minutes PDF or text file for cross-reference"
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Output path for merged analysis"
    )
    parser.add_argument(
        "--no-llm-fallback",
        action="store_true",
        help="Disable LLM name extraction fallback (use only pattern matching)"
    )
    parser.add_argument(
        "--verbose",
        action="store_true"
    )

    args = parser.parse_args()

    # Load data
    with open(args.youtube_analysis) as f:
        youtube_data = json.load(f)

    with open(args.assemblyai_transcript) as f:
        assemblyai_data = json.load(f)

    # Load minutes attendees if provided
    attendees = None
    if args.minutes:
        if args.verbose:
            print(f"\n📄 Loading minutes from: {args.minutes}")

        try:
            minutes_parser = MinutesParser()

            # Check if it's a text file or PDF
            if args.minutes.endswith('.txt'):
                with open(args.minutes, 'r') as f:
                    minutes_text = f.read()
            else:
                # Assume PDF, extract text
                from agenda_integration import AgendaIntegrator
                integrator = AgendaIntegrator()

                with open(args.minutes, 'rb') as f:
                    pdf_content = f.read()
                minutes_text = integrator._extract_pdf_text(pdf_content)

            attendees = minutes_parser.extract_meeting_attendees(minutes_text)

            if args.verbose:
                print(f"   ✅ Extracted {len(attendees.council_members_present)} council members, "
                      f"{len(attendees.staff_present)} staff")
        except Exception as e:
            print(f"   ⚠️  Failed to load minutes: {e}")
            print("   Continuing without minutes cross-reference...")

    if args.verbose:
        print("\n" + "="*70)
        print("MERGING YOUTUBE + ASSEMBLYAI SPEAKER ANALYSES")
        print("="*70)
        if not args.no_llm_fallback:
            print("LLM fallback: ENABLED (automatic name extraction for pattern matching failures)")
        else:
            print("LLM fallback: DISABLED (pattern matching only)")

    # Create mappings (with optional minutes attendees and LLM fallback)
    mappings = create_speaker_mapping(
        youtube_data,
        assemblyai_data,
        attendees,
        enable_llm_fallback=not args.no_llm_fallback
    )

    # Analyze discrepancy
    discrepancy = analyze_discrepancy(youtube_data, assemblyai_data, mappings)

    # Calculate identification method breakdown
    method_counts = {
        'pattern': 0,
        'llm': 0,
        'minutes': 0,
        'unknown': 0
    }
    for m in mappings:
        if m.evidence.startswith('Pattern matching'):
            method_counts['pattern'] += 1
        elif m.evidence.startswith('LLM extraction'):
            method_counts['llm'] += 1
        elif m.evidence.startswith('Minutes cross-reference'):
            method_counts['minutes'] += 1
        else:
            method_counts['unknown'] += 1

    if args.verbose:
        print(f"\nYouTube speakers (mentioned): {discrepancy['youtube_total']}")
        print(f"AssemblyAI speakers (spoke): {discrepancy['assemblyai_total']}")
        print(f"High-confidence mappings: {discrepancy['high_confidence_mappings']}")
        print(f"Discrepancy: {discrepancy['discrepancy']} mentioned but didn't speak")

        print(f"\nIdentification Methods:")
        print(f"  Pattern matching: {method_counts['pattern']} ({method_counts['pattern']/len(mappings)*100:.1f}%)")
        print(f"  LLM extraction: {method_counts['llm']} ({method_counts['llm']/len(mappings)*100:.1f}%)")
        print(f"  Minutes cross-ref: {method_counts['minutes']} ({method_counts['minutes']/len(mappings)*100:.1f}%)")
        print(f"  Unknown: {method_counts['unknown']} ({method_counts['unknown']/len(mappings)*100:.1f}%)")

    # Build result
    result = {
        'source': 'merged_youtube_assemblyai',
        'youtube_analysis_file': args.youtube_analysis,
        'assemblyai_transcript_file': args.assemblyai_transcript,
        'summary': discrepancy,
        'identification_methods': {
            'pattern_matching': method_counts['pattern'],
            'llm_extraction': method_counts['llm'],
            'minutes_cross_reference': method_counts['minutes'],
            'unknown': method_counts['unknown'],
            'total_speakers': len(mappings)
        },
        'speaker_mappings': [
            {
                'assemblyai_label': m.assemblyai_label,
                'name': m.name,
                'role': m.role,
                'confidence': m.confidence,
                'evidence': m.evidence,
                'utterance_count': m.utterance_count,
                'sample_utterance': m.sample_text
            }
            for m in sorted(mappings, key=lambda x: x.utterance_count, reverse=True)
        ],
        'mentioned_not_spoken': discrepancy['mentioned_not_spoken']
    }

    # Save
    with open(args.output, 'w') as f:
        json.dump(result, f, indent=2)

    if args.verbose:
        print(f"\n✅ Saved merged analysis to: {args.output}")

        print("\n" + "="*70)
        print("MENTIONED BUT DIDN'T SPEAK (Top 10)")
        print("="*70)
        for speaker in discrepancy['mentioned_not_spoken'][:10]:
            print(f"\n{speaker['name']} ({speaker['role']})")
            print(f"  Mentions: {speaker['mentions']}")
            if speaker['contexts']:
                print(f"  Context: {speaker['contexts'][0]['context']}")

    print("\n" + "="*70)


if __name__ == "__main__":
    main()
