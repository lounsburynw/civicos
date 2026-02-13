/**
 * Data types for City Pulse feed.
 *
 * These match the response format from the CivicOS REST API
 * /api/tools/city-pulse endpoint.
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
  vote_tally?: string;
  date: string;
}

export interface CommunityPulse {
  total_issues?: number;
  top_types?: Record<string, number>;
}

// === API wrapper response ===

export interface ToolResponse<T = unknown> {
  success: boolean;
  data: T;
  error?: string;
}
