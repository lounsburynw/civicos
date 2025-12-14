-- Add short_name fields to issues table
-- Format: KEYWORD-123 (e.g., EVICTION-1, POTHOLE-5)

ALTER TABLE issues ADD COLUMN short_name_keyword TEXT;
ALTER TABLE issues ADD COLUMN short_name_number INTEGER;

-- Create index for efficient lookup and counter queries
CREATE INDEX idx_issues_short_name_keyword ON issues(short_name_keyword);
CREATE INDEX idx_issues_short_name_full ON issues(short_name_keyword, short_name_number);
