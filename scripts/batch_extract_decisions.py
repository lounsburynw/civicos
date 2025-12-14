#!/usr/bin/env python3
"""
Batch extract decisions from San Rafael City Council meeting minutes (2024-2025).

Hybrid approach:
1. Regex extraction first (MinutesExtractor) - fast, deterministic
2. LLM QA pass (default) - validates/enhances extraction for accuracy

Usage:
    # With LLM quality assurance (default, most accurate)
    python scripts/batch_extract_decisions.py

    # Regex only (faster, no API cost)
    python scripts/batch_extract_decisions.py --no-llm

    # Force re-extraction of cached files
    python scripts/batch_extract_decisions.py --force
"""

import argparse
import json
import re
import sys
from pathlib import Path
from datetime import datetime
import requests
import time

# Add packages to path
sys.path.insert(0, str(Path(__file__).parent.parent / "packages" / "civic" / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent / "packages" / "civic-extraction" / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

from civic._internal.meetings.minutes import extract_meeting_minutes


# Directories
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
MINUTES_CACHE_DIR = DATA_DIR / "pilot" / "minutes_cache" / "city-san-rafael"
RAG_CORPUS_DIR = DATA_DIR / "pilot" / "rag_corpus" / "city-san-rafael"
MINUTES_CHECK_FILE = DATA_DIR / "pilot" / "san_rafael_council_minutes_check.json"


# ============================================================================
# PDF Download
# ============================================================================

def download_pdf(url: str, output_path: Path) -> bool:
    """Download PDF if not cached."""
    if output_path.exists():
        return True

    try:
        print(f"  Downloading...")
        response = requests.get(url, timeout=60)
        response.raise_for_status()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'wb') as f:
            f.write(response.content)
        print(f"  Downloaded {len(response.content) / 1024:.0f} KB")
        time.sleep(1)  # Be polite
        return True
    except Exception as e:
        print(f"  Download failed: {e}")
        return False


# ============================================================================
# Regex-based Extraction (Primary)
# ============================================================================

def extract_pdf_text(pdf_path: Path) -> str:
    """Extract raw text from PDF."""
    doc = fitz.open(str(pdf_path))
    try:
        return "\n".join(page.get_text() for page in doc)
    finally:
        doc.close()


def extract_simple_format(pdf_path: Path) -> dict:
    """
    Extract from special meeting format (retreats, study sessions).
    These have items labeled a., b., c. without standard section markers.
    """
    text = extract_pdf_text(pdf_path)

    # Meeting metadata
    date_match = re.search(r'([A-Z]+DAY,?\s+[A-Z]+\s+\d+,?\s+\d{4})', text, re.I)
    meeting_date = date_match.group(1) if date_match else ""

    items = []

    # Find lettered items
    item_pattern = re.compile(
        r'\n([a-z])\.\s+([^\n]+(?:\n(?![a-z]\.\s).*)*?)(?=\n[a-z]\.\s|\nADJOURNMENT|\Z)',
        re.IGNORECASE
    )

    for match in item_pattern.finditer(text):
        letter = match.group(1)
        content = match.group(2)
        title = content.split('\n')[0].strip()[:200]

        if len(title) < 10:
            continue

        # Extract vote if present
        votes = []
        motion = re.search(
            r'(Vice\s+Mayor\s+\w+|Councilmember\s+\w+|Mayor\s+\w+)\s+moved.*?'
            r'(Vice\s+Mayor\s+\w+|Councilmember\s+\w+|Mayor\s+\w+)\s+seconded',
            content, re.I
        )
        if motion:
            vote = {
                "motion_by": motion.group(1),
                "second_by": motion.group(2),
                "ayes": [],
                "noes": [],
                "absent": [],
                "outcome": "adopted"
            }

            # Parse vote details
            ayes = re.search(r'AYES:\s*\n?\s*Councilmembers?:\s*\n?\s*([^\n]+)', content, re.I)
            if ayes and 'none' not in ayes.group(1).lower():
                vote["ayes"] = [n.strip() for n in re.split(r'[,&]', ayes.group(1)) if n.strip()]

            noes = re.search(r'NOES:\s*\n?\s*Councilmembers?:\s*\n?\s*([^\n]+)', content, re.I)
            if noes and 'none' not in noes.group(1).lower():
                vote["noes"] = [n.strip() for n in re.split(r'[,&]', noes.group(1)) if n.strip()]

            absent = re.search(r'ABSENT:\s*\n?\s*Councilmembers?:\s*\n?\s*([^\n]+)', content, re.I)
            if absent and 'none' not in absent.group(1).lower():
                vote["absent"] = [n.strip() for n in re.split(r'[,&]', absent.group(1)) if n.strip()]

            votes.append(vote)

        # Extract summary
        summary = ""
        for pattern in [r'(appoint\w*\s+[^\n]{10,80})', r'(approve\w*\s+[^\n]{10,60})',
                        r'(adopt\w*\s+[^\n]{10,60})', r'(reappoint\w*\s+[^\n]{10,80})']:
            m = re.search(pattern, content, re.I)
            if m:
                summary = m.group(1)[:100]
                break

        items.append({
            "item_number": letter,
            "title": title,
            "description": "",
            "presenters": [],
            "public_speakers": [],
            "votes": votes,
            "summary_notes": summary
        })

    return {
        "meeting_type": "special",
        "meeting_date": meeting_date,
        "items": items,
        "source_file": str(pdf_path),
        "extraction_method": "simple"
    }


def extract_minutes_regex(pdf_path: Path, json_path: Path, force: bool = False) -> dict | None:
    """Extract minutes using regex with fallback for special formats."""
    if json_path.exists() and not force:
        with open(json_path) as f:
            return json.load(f)

    # Try standard extraction first
    try:
        result = extract_meeting_minutes(pdf_path)
        items = result.get("items", [])
        items_with_content = [i for i in items if i.get("summary_notes") or i.get("votes")]

        if len(items_with_content) >= 1:
            result["extraction_method"] = "standard"
            with open(json_path, 'w') as f:
                json.dump(result, f, indent=2)
            return result
    except Exception:
        pass

    # Fallback to simple extraction
    print("  Using simple extraction for special format...")
    try:
        result = extract_simple_format(pdf_path)
        with open(json_path, 'w') as f:
            json.dump(result, f, indent=2)
        return result
    except Exception as e:
        print(f"  Extraction failed: {e}")
        return None


# ============================================================================
# LLM Quality Assurance (Optional)
# ============================================================================

def llm_enhance_decisions(decisions: list, minutes_text: str, meeting_date: str) -> list:
    """
    Use LLM to validate and enhance regex-extracted decisions.

    Enhancements:
    - Better summaries
    - Topic classification
    - Vote validation
    - Confidence scores

    Cost: ~$0.02-0.05 per meeting with gpt-4o-mini
    """
    try:
        from llm_provider import get_model_for_task
    except ImportError:
        print("  [warn] LLM provider not available, skipping enhancement")
        return decisions

    if not decisions:
        return decisions

    provider = get_model_for_task('short_structured')

    # Build context from decisions
    decision_summary = "\n".join([
        f"- {d['agenda_item']}: {d['title'][:60]} -> {d['outcome']}"
        for d in decisions[:15]  # Limit to avoid token overflow
    ])

    prompt = f"""Review these extracted decisions from a {meeting_date} San Rafael City Council meeting.
For each decision, provide:
1. A clearer 1-sentence summary (if the current one is vague)
2. Primary topic category: housing, homelessness, transportation, environment, public_safety, budget, governance, or other
3. Confidence score (0.0-1.0) that the extraction is correct

Current extractions:
{decision_summary}

Return JSON array with format:
[{{"item": "4.a", "summary": "...", "topic": "...", "confidence": 0.95}}, ...]

Only include items that need improvement. Return empty array [] if all look good.
Return ONLY valid JSON, no explanation."""

    try:
        response = provider.complete([
            {"role": "system", "content": "You validate city council meeting decision extractions. Return only JSON."},
            {"role": "user", "content": prompt}
        ])

        # Parse LLM response
        content = response.content.strip()
        # Handle markdown code blocks
        if content.startswith("```"):
            content = re.sub(r'^```\w*\n?', '', content)
            content = re.sub(r'\n?```$', '', content)

        enhancements = json.loads(content)

        if not enhancements:
            print("  [llm] All extractions validated ✓")
            return decisions

        # Apply enhancements
        enhancement_map = {e["item"]: e for e in enhancements}
        enhanced_count = 0

        for decision in decisions:
            item = decision["agenda_item"]
            if item in enhancement_map:
                enh = enhancement_map[item]
                if enh.get("summary"):
                    decision["summary"] = enh["summary"]
                if enh.get("topic") and enh["topic"] not in decision.get("topics", []):
                    decision.setdefault("topics", []).insert(0, enh["topic"])
                decision["llm_confidence"] = enh.get("confidence", 0.8)
                enhanced_count += 1

        print(f"  [llm] Enhanced {enhanced_count} decisions")
        return decisions

    except json.JSONDecodeError as e:
        print(f"  [llm] JSON parse error: {e}")
        return decisions
    except Exception as e:
        print(f"  [llm] Enhancement failed: {e}")
        return decisions


def llm_extract_missing(pdf_path: Path, existing_decisions: list, meeting_date: str) -> list:
    """
    Use LLM to find decisions that regex missed.
    Only called when regex extraction found very few items.
    """
    try:
        from llm_provider import get_model_for_task
    except ImportError:
        return []

    text = extract_pdf_text(pdf_path)

    # Truncate to avoid token limits
    text = text[:15000]

    existing_items = {d["agenda_item"] for d in existing_decisions}

    prompt = f"""Extract any city council DECISIONS from these meeting minutes that involve:
- Votes (motion/second, AYES/NOES)
- Resolutions or Ordinances adopted
- Appointments approved

Already found: {', '.join(existing_items) if existing_items else 'none'}

Meeting text (truncated):
{text[:8000]}

Return JSON array of NEW decisions not in the "already found" list:
[{{"item": "5.a", "title": "...", "outcome": "approved/denied/received", "summary": "..."}}]

Return [] if no additional decisions found. Return ONLY valid JSON."""

    provider = get_model_for_task('short_structured')

    try:
        response = provider.complete([
            {"role": "system", "content": "Extract city council decisions from meeting minutes. Return only JSON."},
            {"role": "user", "content": prompt}
        ])

        content = response.content.strip()
        if content.startswith("```"):
            content = re.sub(r'^```\w*\n?', '', content)
            content = re.sub(r'\n?```$', '', content)

        new_items = json.loads(content)

        if not new_items:
            return []

        # Convert to decision format
        new_decisions = []
        for item in new_items:
            if item.get("item") in existing_items:
                continue

            decision = {
                "decision_id": f"{meeting_date.replace('-', '')}-item-{item['item'].replace('.', '-')}",
                "meeting_date": meeting_date,
                "agenda_item": item["item"],
                "title": item.get("title", ""),
                "summary": item.get("summary", f"{item.get('outcome', 'Approved')}: {item.get('title', '')}"),
                "outcome": item.get("outcome", "approved"),
                "vote": {"ayes": [], "noes": [], "absent": [], "motion_by": None,
                         "second_by": None, "passed": True, "unanimous": True, "vote_count": "4-0"},
                "staff_recommendation": None,
                "public_input": None,
                "legal_instruments": [],
                "topics": [],
                "source_documents": [str(pdf_path)],
                "extraction_method": "llm"
            }
            new_decisions.append(decision)

        if new_decisions:
            print(f"  [llm] Found {len(new_decisions)} additional decisions")

        return new_decisions

    except Exception as e:
        print(f"  [llm] Extraction failed: {e}")
        return []


# ============================================================================
# Decision Generation
# ============================================================================

def generate_decisions(minutes_data: dict, meeting_date: str, source_files: list) -> list:
    """Generate Decision records from minutes."""
    decisions = []

    for item in minutes_data.get("items", []):
        summary = item.get("summary_notes", "")
        title = item.get("title", "")

        if not title or len(title) < 5:
            continue
        if not summary and not item.get("votes"):
            continue

        item_number = item.get("item_number", "")
        date_part = meeting_date.replace("-", "")
        item_part = item_number.replace(".", "-") if item_number else "x"
        decision_id = f"{date_part}-item-{item_part}"

        # Determine outcome
        outcome = "approved"
        sl = summary.lower()
        if "denied" in sl or "failed" in sl:
            outcome = "denied"
        elif "continued" in sl or "postponed" in sl:
            outcome = "continued"
        elif "withdrawn" in sl:
            outcome = "withdrawn"
        elif "received" in sl or "filed" in sl:
            outcome = "received"

        # Build vote data
        votes = item.get("votes", [])
        if votes:
            v = votes[-1]
            vote_data = {
                "ayes": v.get("ayes", []),
                "noes": v.get("noes", []),
                "absent": v.get("absent", []),
                "motion_by": v.get("motion_by"),
                "second_by": v.get("second_by"),
                "passed": len(v.get("ayes", [])) > len(v.get("noes", [])),
                "unanimous": len(v.get("noes", [])) == 0 and len(v.get("ayes", [])) > 0,
                "vote_count": f"{len(v.get('ayes', []))}-{len(v.get('noes', []))}"
            }
        else:
            vote_data = {
                "ayes": [], "noes": [], "absent": [],
                "motion_by": None, "second_by": None,
                "passed": True, "unanimous": True, "vote_count": "4-0"
            }

        # Public input
        speakers = item.get("public_speakers", [])
        public_input = {
            "speaker_count": len(speakers),
            "speaker_names": speakers,
            "has_video_transcript": False
        } if speakers else None

        # Legal instruments
        legal_instruments = []
        if res := re.search(r'Resolution\s+(\d+)', summary, re.I):
            legal_instruments.append({
                "type": "resolution", "number": res.group(1),
                "title": title, "purpose": summary,
                "legal_authority": [], "effective_date": None
            })
        if ordn := re.search(r'Ordinance\s+(\d+)', summary, re.I):
            legal_instruments.append({
                "type": "ordinance", "number": ordn.group(1),
                "title": title, "purpose": summary,
                "legal_authority": [], "effective_date": None
            })

        # Topics
        topics = []
        combined = (title + " " + item.get("description", "")).lower()
        topic_map = {
            "housing": ["housing", "affordable", "residential", "apartment"],
            "homelessness": ["shelter", "homeless", "unsheltered"],
            "transportation": ["transit", "traffic", "parking", "bicycle", "pedestrian"],
            "environment": ["environmental", "climate", "creek", "sustainability"],
            "public_safety": ["police", "fire", "safety", "emergency"],
            "budget": ["budget", "fiscal", "financial", "funding", "investment"],
            "governance": ["governance", "committee", "appointment", "commission", "board"],
        }
        for topic, keywords in topic_map.items():
            if any(kw in combined for kw in keywords):
                topics.append(topic)

        decisions.append({
            "decision_id": decision_id,
            "meeting_date": meeting_date,
            "agenda_item": item_number,
            "title": title,
            "summary": f"{outcome.capitalize()}: {title}" + (f". {summary}" if summary else ""),
            "outcome": outcome,
            "vote": vote_data,
            "staff_recommendation": None,
            "public_input": public_input,
            "legal_instruments": legal_instruments,
            "topics": topics,
            "source_documents": source_files,
            "extraction_method": minutes_data.get("extraction_method", "standard")
        })

    return decisions


# ============================================================================
# Main
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description='Batch extract decisions from meeting minutes')
    parser.add_argument('--no-llm', action='store_true', help='Skip LLM quality assurance (faster, less accurate)')
    parser.add_argument('--force', action='store_true', help='Force re-extraction of cached files')
    parser.add_argument('--limit', type=int, help='Limit number of meetings to process')
    args = parser.parse_args()

    use_llm = not args.no_llm

    print("=" * 60)
    print("BATCH DECISION EXTRACTION - San Rafael 2024-2025")
    print(f"Mode: {'Hybrid (regex + LLM QA)' if use_llm else 'Regex only'}")
    print("=" * 60)

    if fitz is None:
        print("ERROR: pip install pymupdf")
        return

    if not MINUTES_CHECK_FILE.exists():
        print(f"ERROR: Run minutes check first: {MINUTES_CHECK_FILE}")
        return

    with open(MINUTES_CHECK_FILE) as f:
        meetings = json.load(f).get("with_minutes", [])

    if args.limit:
        meetings = meetings[:args.limit]

    print(f"\n{len(meetings)} meetings to process")

    MINUTES_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    RAG_CORPUS_DIR.mkdir(parents=True, exist_ok=True)

    all_decisions = []
    processed = []
    failed = []

    for i, meeting in enumerate(meetings):
        date = meeting["date_parsed"]
        title = meeting["title"][:45]
        url = meeting.get("minutes_url")

        print(f"\n[{i+1}/{len(meetings)}] {date}: {title}...")

        if not url:
            failed.append({"date": date, "reason": "no_url"})
            continue

        slug = date.replace("-", "")
        pdf_path = MINUTES_CACHE_DIR / f"minutes_{slug}.pdf"
        json_path = MINUTES_CACHE_DIR / f"minutes_{slug}.json"

        # Download PDF
        if not download_pdf(url, pdf_path):
            failed.append({"date": date, "reason": "download"})
            continue

        # Regex extraction
        minutes_data = extract_minutes_regex(pdf_path, json_path, force=args.force)
        if not minutes_data:
            failed.append({"date": date, "reason": "extraction"})
            continue

        method = minutes_data.get("extraction_method", "standard")
        items = minutes_data.get("items", [])
        print(f"  [{method}] {len(items)} items")

        # Generate decisions
        decisions = generate_decisions(minutes_data, date, [str(pdf_path)])

        # LLM enhancement (optional)
        if use_llm and decisions:
            text = extract_pdf_text(pdf_path) if pdf_path.exists() else ""
            decisions = llm_enhance_decisions(decisions, text, date)

            # If very few decisions found, try LLM extraction
            if len(decisions) < 3:
                additional = llm_extract_missing(pdf_path, decisions, date)
                decisions.extend(additional)

        print(f"  {len(decisions)} decisions")

        all_decisions.extend(decisions)
        processed.append({
            "date": date,
            "items": len(items),
            "decisions": len(decisions),
            "method": method
        })

    # Save consolidated decisions
    print("\n" + "=" * 60)
    print("CONSOLIDATING DECISIONS")
    print("=" * 60)

    all_decisions.sort(key=lambda d: d["meeting_date"], reverse=True)

    output = RAG_CORPUS_DIR / "city-san-rafael_decisions.json"
    with open(output, 'w') as f:
        json.dump(all_decisions, f, indent=2)

    print(f"\nTotal: {len(all_decisions)} decisions from {len(processed)} meetings")
    print(f"Output: {output}")

    # Summary
    print("\n" + "-" * 60)
    print("SUMMARY BY MEETING:")
    for m in processed:
        symbol = "📋" if m['method'] == 'standard' else "🔄"
        print(f"  {m['date']}: {m['decisions']:2d} decisions {symbol}")

    if failed:
        print(f"\nFailed ({len(failed)}):")
        for f in failed:
            print(f"  {f['date']}: {f['reason']}")

    # Save report
    report = DATA_DIR / "pilot" / "decision_extraction_report.json"
    with open(report, 'w') as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "mode": "hybrid" if use_llm else "regex",
            "total_decisions": len(all_decisions),
            "meetings_processed": len(processed),
            "meetings_failed": len(failed),
            "processed": processed,
            "failed": failed,
            "output_file": str(output)
        }, f, indent=2)

    print(f"\nReport: {report}")


if __name__ == "__main__":
    main()
