-- Migration 011: Testimony Storage Schema
--
-- Stores testimony from city council meetings with speaker attribution, topic
-- classification, and links to agenda items and SeeClickFix complaints.
--
-- Session: 111 (production hardening)
-- Date: 2024-11-23
--
-- Tables:
--   - testimony_meetings: Meeting metadata and processing info
--   - testimony_speakers: Speaker identification with confidence levels
--   - testimony_utterances: Individual speaker utterances with timestamps
--   - testimony_topics: Topic classification and matching to agendas/complaints
--
-- Dependencies:
--   - Requires jurisdictions table (from core schema)
--
-- Usage:
--   sqlite3 data/civic_participation.db < migrations/011_testimony_storage.sql

-- ============================================================================
-- Table: testimony_meetings
-- ============================================================================
-- Stores metadata about processed meetings and their transcripts
--
-- Fields:
--   - meeting_id: Unique identifier (format: {jurisdiction}_{date}_{video_id})
--   - jurisdiction_id: Foreign key to jurisdictions table
--   - meeting_date: Date of meeting (ISO format: YYYY-MM-DD)
--   - youtube_video_id: YouTube video ID for source video
--   - assemblyai_transcript_id: AssemblyAI transcript ID for retrieval
--   - speaker_count_estimated: LLM-estimated speaker count before processing
--   - speaker_count_actual: Actual speaker count from AssemblyAI diarization
--   - processing_cost_usd: Total cost for processing (YouTube LLM + AssemblyAI + name extraction)
--   - processed_at: Timestamp when processing completed

CREATE TABLE IF NOT EXISTS testimony_meetings (
    meeting_id TEXT PRIMARY KEY,
    jurisdiction_id TEXT NOT NULL,
    meeting_date TEXT NOT NULL,
    youtube_video_id TEXT,
    assemblyai_transcript_id TEXT,
    speaker_count_estimated INTEGER,
    speaker_count_actual INTEGER,
    processing_cost_usd REAL,
    processed_at TEXT,
    FOREIGN KEY (jurisdiction_id) REFERENCES jurisdictions(id)
);

-- Index for querying meetings by jurisdiction and date
CREATE INDEX IF NOT EXISTS idx_testimony_meetings_jurisdiction_date
ON testimony_meetings(jurisdiction_id, meeting_date DESC);

-- ============================================================================
-- Table: testimony_speakers
-- ============================================================================
-- Stores speaker identification with confidence levels and methods
--
-- Fields:
--   - speaker_id: Unique identifier (format: {meeting_id}_{speaker_label})
--   - meeting_id: Foreign key to testimony_meetings
--   - speaker_label: AssemblyAI speaker label (A, B, C, ..., AA, AB, etc.)
--   - name: Identified speaker name (or "Unknown (X)" if not identified)
--   - role: Speaker role (public, council, staff, unknown)
--   - confidence: Identification confidence (high, medium, low)
--   - identification_method: How speaker was identified (pattern, llm, minutes, none)
--   - utterance_count: Number of utterances by this speaker

CREATE TABLE IF NOT EXISTS testimony_speakers (
    speaker_id TEXT PRIMARY KEY,
    meeting_id TEXT NOT NULL,
    speaker_label TEXT NOT NULL,
    name TEXT,
    role TEXT,
    confidence TEXT,
    identification_method TEXT,
    utterance_count INTEGER,
    FOREIGN KEY (meeting_id) REFERENCES testimony_meetings(meeting_id) ON DELETE CASCADE
);

-- Index for querying speakers by meeting
CREATE INDEX IF NOT EXISTS idx_testimony_speakers_meeting
ON testimony_speakers(meeting_id);

-- Index for querying speakers by name (for finding repeat testifiers)
CREATE INDEX IF NOT EXISTS idx_testimony_speakers_name
ON testimony_speakers(name) WHERE name NOT LIKE 'Unknown%';

-- Index for querying speakers by role
CREATE INDEX IF NOT EXISTS idx_testimony_speakers_role
ON testimony_speakers(role);

-- ============================================================================
-- Table: testimony_utterances
-- ============================================================================
-- Stores individual speaker utterances with timestamps for audio alignment
--
-- Fields:
--   - utterance_id: Unique identifier (format: {speaker_id}_{sequence})
--   - speaker_id: Foreign key to testimony_speakers
--   - text: Utterance text content
--   - start_ms: Start time in milliseconds from beginning of audio
--   - end_ms: End time in milliseconds
--   - confidence: AssemblyAI transcription confidence (0.0-1.0)
--   - sequence: Utterance sequence number within speaker's testimony

CREATE TABLE IF NOT EXISTS testimony_utterances (
    utterance_id TEXT PRIMARY KEY,
    speaker_id TEXT NOT NULL,
    text TEXT NOT NULL,
    start_ms INTEGER,
    end_ms INTEGER,
    confidence REAL,
    sequence INTEGER,
    FOREIGN KEY (speaker_id) REFERENCES testimony_speakers(speaker_id) ON DELETE CASCADE
);

-- Index for querying utterances by speaker
CREATE INDEX IF NOT EXISTS idx_testimony_utterances_speaker
ON testimony_utterances(speaker_id, sequence);

-- Full-text search index for testimony content search
-- Note: This enables queries like "Find all testimony mentioning 'wildfire'"
CREATE VIRTUAL TABLE IF NOT EXISTS testimony_utterances_fts USING fts5(
    utterance_id UNINDEXED,
    speaker_id UNINDEXED,
    text,
    content=testimony_utterances,
    content_rowid=rowid
);

-- Triggers to keep FTS index in sync with testimony_utterances
CREATE TRIGGER IF NOT EXISTS testimony_utterances_fts_insert
AFTER INSERT ON testimony_utterances BEGIN
    INSERT INTO testimony_utterances_fts(rowid, utterance_id, speaker_id, text)
    VALUES (new.rowid, new.utterance_id, new.speaker_id, new.text);
END;

CREATE TRIGGER IF NOT EXISTS testimony_utterances_fts_delete
AFTER DELETE ON testimony_utterances BEGIN
    DELETE FROM testimony_utterances_fts WHERE rowid = old.rowid;
END;

CREATE TRIGGER IF NOT EXISTS testimony_utterances_fts_update
AFTER UPDATE ON testimony_utterances BEGIN
    DELETE FROM testimony_utterances_fts WHERE rowid = old.rowid;
    INSERT INTO testimony_utterances_fts(rowid, utterance_id, speaker_id, text)
    VALUES (new.rowid, new.utterance_id, new.speaker_id, new.text);
END;

-- ============================================================================
-- Table: testimony_topics
-- ============================================================================
-- Stores topic classification and links to agenda items and complaints
--
-- Fields:
--   - topic_id: Unique identifier (format: {speaker_id}_{topic})
--   - speaker_id: Foreign key to testimony_speakers
--   - topic: Topic classification (housing, transportation, wildfire, etc.)
--   - keywords: JSON array of matched keywords for this topic
--   - matched_agenda_items: JSON array of linked agenda item IDs
--   - matched_complaints: JSON array of linked SeeClickFix issue IDs
--   - confidence: Topic classification confidence (0.0-1.0)

CREATE TABLE IF NOT EXISTS testimony_topics (
    topic_id TEXT PRIMARY KEY,
    speaker_id TEXT NOT NULL,
    topic TEXT NOT NULL,
    keywords TEXT,
    matched_agenda_items TEXT,
    matched_complaints TEXT,
    confidence REAL,
    FOREIGN KEY (speaker_id) REFERENCES testimony_speakers(speaker_id) ON DELETE CASCADE
);

-- Index for querying topics by speaker
CREATE INDEX IF NOT EXISTS idx_testimony_topics_speaker
ON testimony_topics(speaker_id);

-- Index for querying by topic (for finding all wildfire testimony, etc.)
CREATE INDEX IF NOT EXISTS idx_testimony_topics_topic
ON testimony_topics(topic);

-- ============================================================================
-- Example Queries
-- ============================================================================
--
-- 1. Find all wildfire testimony from past 12 months:
--    SELECT
--        m.meeting_date,
--        s.name,
--        s.role,
--        GROUP_CONCAT(u.text, ' ') as testimony
--    FROM testimony_meetings m
--    JOIN testimony_speakers s ON s.meeting_id = m.meeting_id
--    JOIN testimony_utterances u ON u.speaker_id = s.speaker_id
--    JOIN testimony_topics t ON t.speaker_id = s.speaker_id
--    WHERE
--        m.jurisdiction_id = 'san-rafael'
--        AND t.topic = 'wildfire'
--        AND m.meeting_date >= date('now', '-12 months')
--    GROUP BY s.speaker_id
--    ORDER BY m.meeting_date;
--
-- 2. Find residents who testified multiple times:
--    SELECT
--        s.name,
--        COUNT(DISTINCT m.meeting_id) as meeting_count,
--        GROUP_CONCAT(DISTINCT t.topic) as topics
--    FROM testimony_speakers s
--    JOIN testimony_meetings m ON m.meeting_id = s.meeting_id
--    JOIN testimony_topics t ON t.speaker_id = s.speaker_id
--    WHERE s.name NOT LIKE 'Unknown%'
--    GROUP BY s.name
--    HAVING meeting_count > 1
--    ORDER BY meeting_count DESC;
--
-- 3. Find testimony patterns by topic:
--    SELECT
--        t.topic,
--        COUNT(DISTINCT s.speaker_id) as speaker_count,
--        COUNT(DISTINCT m.meeting_id) as meeting_count,
--        AVG(s.utterance_count) as avg_utterances
--    FROM testimony_topics t
--    JOIN testimony_speakers s ON s.speaker_id = t.speaker_id
--    JOIN testimony_meetings m ON m.meeting_id = s.meeting_id
--    WHERE m.jurisdiction_id = 'san-rafael'
--    GROUP BY t.topic
--    ORDER BY speaker_count DESC;
--
-- 4. Full-text search for specific testimony:
--    SELECT
--        s.name,
--        m.meeting_date,
--        u.text
--    FROM testimony_utterances_fts fts
--    JOIN testimony_utterances u ON u.utterance_id = fts.utterance_id
--    JOIN testimony_speakers s ON s.speaker_id = u.speaker_id
--    JOIN testimony_meetings m ON m.meeting_id = s.meeting_id
--    WHERE testimony_utterances_fts MATCH 'wildfire OR evacuation'
--    ORDER BY m.meeting_date DESC;
--
-- ============================================================================
-- Migration Complete
-- ============================================================================
