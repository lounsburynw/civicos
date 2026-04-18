-- Migration: rename chunks.agenda_item='closing' to 'unparsed'
--
-- Background: packages/civicos/src/civicos/_internal/meetings/pdf_parser.py
-- _parse_with_patterns used 'closing' / 'Closing Materials' as a fallback
-- label when AGENDA_ITEM_PATTERN regex did not match anywhere in the PDF.
-- The regex only matched the San Rafael / ProudCity format ("Agenda Item
-- No. 6.a") and missed the numbered-bullet format used by Alameda County,
-- San Francisco, Berkeley, and many other jurisdictions. Result: 36,611
-- current chunks (and historically many more across every jurisdiction)
-- were labeled as if they were in the closing section when they were
-- actually the entire agenda packet.
--
-- The code fix (same session) adds a secondary regex pattern for the
-- numbered-bullet format and renames the fallback label to 'unparsed' /
-- 'Unparsed Section' so new extractions are honest about the gap.
--
-- This migration relabels existing current chunks to match the new code.
-- Historical versions (valid_to IS NOT NULL) are not touched — they
-- represent what the system said at those points in time and should not
-- be retroactively rewritten.
--
-- Why not re-extract? Content-hash idempotency would skip unchanged PDFs,
-- so a pure rename accomplishes the honesty goal cheaply. A future LLM-
-- based item-boundary detector (tracked as a separate follow-up) is the
-- path to actually recovering per-item labels for these chunks.
--
-- Before:
--   current chunks with agenda_item='closing': 36,611
--   historical chunks with agenda_item='closing': 0
--
-- After:
--   current chunks with agenda_item='unparsed': 36,611
--   historical chunks with agenda_item='closing': 0 (unchanged)

BEGIN;

UPDATE chunks
   SET agenda_item = 'unparsed',
       agenda_title = 'Unparsed Section'
 WHERE agenda_item = 'closing'
   AND agenda_title = 'Closing Materials'
   AND valid_to IS NULL
   AND deleted_at IS NULL;

COMMIT;
