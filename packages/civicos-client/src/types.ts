/**
 * Data types for CivicOS API responses.
 *
 * These match the response format from the CivicOS REST API
 * and relay coordination endpoints.
 */

// === City Pulse API response ===

export interface CityPulseData {
  jurisdiction: string;
  generated_at: string;
  /** Upcoming meetings (misleadingly named in the API) */
  decisions_this_week: PulseMeeting[];
  /** Agenda items from upcoming meetings */
  upcoming_items: PulseAgendaItem[];
  /** Recent decision outcomes */
  recent_outcomes: PulseOutcome[];
  /** Community issue statistics */
  community_pulse: CommunityPulse;
  clerk_email?: string;
  relay_url?: string;
  error?: string;
}

export interface PulseMeeting {
  title: string;
  date: string;
  time: string;
  location: string;
  meeting_datetime: string;
}

export interface PulseAgendaItem {
  id: string;
  meeting_id: string;
  item_number: string;
  title: string;
  project_type?: string;
  stance_eligible: boolean;
  comment_eligible: boolean;
  description: string;
  why_it_matters: string;
  meeting_title: string;
  meeting_date: string;
}

export interface PulseOutcome {
  id: string;
  title: string;
  outcome: string;
  outcome_description?: string;
  is_upcoming?: boolean;
  vote_tally?: string;
  date: string;
}

export interface CommunityPulse {
  total_issues?: number;
  top_types?: Record<string, number>;
}

// === Decision Detail (from /decision-detail) ===

export interface DecisionDetailData {
  found: boolean;
  summary?: string;
  is_upcoming?: boolean;
  decision?: {
    id: string;
    title: string;
    outcome: string;
    outcome_description?: string;
    date: string;
    body?: string;
    votes?: Record<string, number>;
  };
  testimony?: {
    public_comments?: TestimonyComment[];
    council_discussion?: TestimonyComment[];
  };
  related_decisions?: Array<{
    title: string;
    outcome: string;
    date: string;
  }>;
}

export interface TestimonyComment {
  speaker: string;
  text: string;
  video_url?: string;
  start_timestamp?: string;
}

// === Data Provenance (from /data-provenance) ===

export interface DataProvenance {
  jurisdiction: string;
  mcp_endpoint: string;
  relay_url: string;
  storage_backend: string;
  total_storage_docs: number;
  total_vector_docs: number;
  overall_coverage_percent: number | null;
  corpora: CorpusInfo[];
  freshness: {
    earliest_meeting: string | null;
    latest_meeting: string | null;
    last_updated: string | null;
  };
  generated_at: string;
}

export interface CorpusInfo {
  corpus_type: string;
  display_name: string;
  storage_count: number;
  vector_count: number;
  coverage_percent: number | null;
  last_indexed: string | null;
}

// === Voice Counts ===

export interface VoiceCounts {
  support: number;
  oppose: number;
  watching: number;
  total: number;
  attested?: number;
  unattested?: number;
}

// === Initiatives & Civic Actions ===

export interface Initiative {
  id: string;
  topic: string;
  title: string;
  description: string;
  location?: string;
  coordination_url?: string;
  public_key: string;
  timestamp: string;
  status: string;
  voice_count: number;
  creator_attested?: boolean;
  attested_voice_count?: number;
}

export interface CivicAction {
  id: string;
  initiative_id: string;
  action_type: string;
  description: string;
  target?: string;
  deadline?: string;
  template?: string;
  deadline_context?: string;
  coordination_url?: string;
  target_count?: number;
  public_key: string;
  timestamp: string;
  revoked: boolean;
}

export interface CivicActionProgress {
  action_id: string;
  commitment_count: number;
  completion_count: number;
  target_count?: number;
  progress_percent?: number;
}

// === Issue Geography (from /issue-geography) ===

export interface IssuePoint {
  lat: number;
  lng: number;
  type: string;
  status: string;
  address: string;
  created_at: string;
}

export interface IssueGeography {
  points: IssuePoint[];
  total: number;
}

// === Budget Summary (from /budget-summary) ===

export interface BudgetCategory {
  category: string;
  budgeted_dollars: number;
  percentage: number;
  item_count: number;
}

export interface BudgetSummary {
  categories: BudgetCategory[];
  total_budgeted_dollars: number;
  fiscal_year: string;
  group_by: string;
}

// === Comments ===

export interface Comment {
  entity: string;
  comment_text: string;
  public_key: string;
  signature: string;
  timestamp: string;
  jurisdiction?: string;
  stance?: string;
  deleted: boolean;
  attested?: boolean;
}

export interface CommentCounts {
  entity: string;
  count: number;
  attested?: number;
  unattested?: number;
}

export interface CommentSynthesis {
  entity_id: string;
  total: number;
  support: number;
  oppose: number;
  neutral: number;
}

// === Context Bundle (from /get-item-context) ===

export interface ContextBundle {
  item: ContextItem;
  sections: ContextSections;
  suggested_questions: string[];
  metadata: ContextMetadata;
}

export interface ContextItem {
  type: string;
  id: string;
  title: string;
  description?: string;
  why_it_matters?: string;
  jurisdiction: string;
}

export interface ContextSections {
  history?: HistorySection;
  regulatory?: RegulatorySection;
  community?: unknown;
  financial?: unknown;
  testimony?: TestimonySection;
  participation?: unknown;
}

export interface HistorySection {
  related_decisions: RelatedDecision[];
  summary?: string;
}

export interface RelatedDecision {
  id: string;
  title: string;
  outcome?: string;
  date?: string;
}

export interface RegulatorySection {
  applicable_codes: ApplicableCode[];
}

export interface ApplicableCode {
  title: string;
  code_ref?: string;
  summary?: string;
}

export interface TestimonySection {
  public_comments: TestimonyComment[];
  council_discussion?: TestimonyComment[];
}

export interface ContextMetadata {
  assembled_at: string;
  jurisdiction: string;
  depth: string;
  sections_included: string[];
  degraded: boolean;
  assembly_time_ms: number;
}

// === API wrapper response ===

export interface ToolResponse<T = unknown> {
  success: boolean;
  data: T;
  error?: string;
}
