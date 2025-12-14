-- Query to view comments with all their associated agenda items
-- Usage: sqlite3 data/civic_participation.db < scripts/query_comment_agenda_items.sql

SELECT
    c.id as comment_id,
    c.event_id,
    c.position,
    GROUP_CONCAT(cai.agenda_item_id, ', ') as agenda_items,
    COUNT(cai.agenda_item_id) as item_count,
    substr(c.ai_draft, 1, 100) || '...' as draft_preview,
    c.created_at
FROM comments c
LEFT JOIN comment_agenda_items cai ON c.id = cai.comment_id
GROUP BY c.id
ORDER BY c.created_at DESC
LIMIT 20;
