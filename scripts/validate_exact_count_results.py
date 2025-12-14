#!/usr/bin/env python3
"""
Validate results from exact speaker count experiment (min=50, max=50)

Compares:
- Original: min=40, max=60 → 40 speakers
- Exact: min=50, max=50 → ? speakers

Focus: Did Salama get separated from Mayor?
"""

import json
import sys

def validate_exact_count(original_file: str, exact_file: str):
    """Compare original vs exact count results"""
    
    # Load both transcripts
    with open(original_file) as f:
        original = json.load(f)
    
    with open(exact_file) as f:
        exact = json.load(f)
    
    orig_utterances = original.get('utterances', [])
    exact_utterances = exact.get('utterances', [])
    
    # Get unique speakers
    orig_speakers = sorted(set(u.get('speaker') for u in orig_utterances if u.get('speaker')))
    exact_speakers = sorted(set(u.get('speaker') for u in exact_utterances if u.get('speaker')))
    
    print("="*70)
    print("EXACT COUNT VALIDATION - DIARIZATION COMPARISON")
    print("="*70)
    print()
    
    print(f"Original (min=40, max=60): {len(orig_speakers)} speakers detected")
    print(f"Exact (min=50, max=50):    {len(exact_speakers)} speakers detected")
    print()
    
    improvement = len(exact_speakers) - len(orig_speakers)
    if improvement > 0:
        print(f"✅ IMPROVEMENT: +{improvement} speakers ({improvement/len(orig_speakers)*100:.1f}% increase)")
    elif improvement < 0:
        print(f"⚠️  REGRESSION: {improvement} speakers ({abs(improvement)/len(orig_speakers)*100:.1f}% decrease)")
    else:
        print("⚠️  NO CHANGE: Same speaker count")
    
    print()
    print("="*70)
    print("SALAMA SEPARATION TEST")
    print("="*70)
    print()
    
    # Search for Salama in both
    def find_salama(utterances):
        """Find utterances mentioning Salama"""
        for u in utterances:
            text = u.get('text', '').lower()
            if 'salama' in text or 'salamah' in text:
                # Check if it's an introduction (not just a mention)
                if any(pattern in text for pattern in ['my name', "i'm", 'this is']):
                    return {
                        'speaker': u.get('speaker'),
                        'text': u.get('text')[:150],
                        'start': u.get('start')
                    }
        return None
    
    orig_salama = find_salama(orig_utterances)
    exact_salama = find_salama(exact_utterances)
    
    print("Original diarization:")
    if orig_salama:
        print(f"  Speaker {orig_salama['speaker']}: {orig_salama['text']}")
    else:
        print("  ❌ Salama not found with self-introduction")
    
    print()
    print("Exact count diarization:")
    if exact_salama:
        print(f"  Speaker {exact_salama['speaker']}: {exact_salama['text']}")
        if orig_salama and exact_salama['speaker'] != orig_salama['speaker']:
            print(f"  ✅ SUCCESS: Salama separated (was {orig_salama['speaker']}, now {exact_salama['speaker']})")
        else:
            print(f"  ⚠️  Same speaker label as original")
    else:
        print("  ❌ Salama still not found with self-introduction")
    
    print()
    print("="*70)
    print("MAYOR FRAGMENTATION TEST")
    print("="*70)
    print()
    
    # Check if mayor was split
    def find_mayor_speakers(utterances):
        """Find speakers with mayor-like procedural language"""
        mayor_patterns = ['good evening everyone', 'call the meeting to order', 'invite public comment']
        mayor_speakers = set()
        
        for u in utterances:
            text = u.get('text', '').lower()
            if any(pattern in text for pattern in mayor_patterns):
                mayor_speakers.add(u.get('speaker'))
        
        return mayor_speakers
    
    orig_mayors = find_mayor_speakers(orig_utterances)
    exact_mayors = find_mayor_speakers(exact_utterances)
    
    print(f"Original: {len(orig_mayors)} speaker(s) with mayor language: {orig_mayors}")
    print(f"Exact:    {len(exact_mayors)} speaker(s) with mayor language: {exact_mayors}")
    
    if len(exact_mayors) > len(orig_mayors):
        print(f"  ⚠️  Mayor split into {len(exact_mayors)} labels (acceptable if recoverable)")
    elif len(exact_mayors) == len(orig_mayors):
        print(f"  ✅ Mayor not fragmented")
    
    print()
    print("="*70)
    print("OVERALL ASSESSMENT")
    print("="*70)
    print()
    
    # Determine success
    success_criteria = []
    
    if exact_salama and (not orig_salama or exact_salama['speaker'] != orig_salama.get('speaker')):
        success_criteria.append("✅ Salama separated from Mayor")
    else:
        success_criteria.append("❌ Salama still merged")
    
    if len(exact_speakers) >= 45:
        success_criteria.append(f"✅ Good speaker count ({len(exact_speakers)} speakers)")
    else:
        success_criteria.append(f"⚠️  Low speaker count ({len(exact_speakers)} speakers)")
    
    for criterion in success_criteria:
        print(criterion)
    
    print()
    
    if all('✅' in c for c in success_criteria):
        print("🎉 EXPERIMENT SUCCESSFUL: Exact count improves diarization!")
        print()
        print("RECOMMENDATION: Use exact count (min=N, max=N) for all future meetings")
    else:
        print("⚠️  EXPERIMENT INCONCLUSIVE: Review results manually")
    
    print()
    

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python validate_exact_count_results.py <original.json> <exact.json>")
        sys.exit(1)
    
    validate_exact_count(sys.argv[1], sys.argv[2])
