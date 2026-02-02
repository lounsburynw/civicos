/**
 * TypeScript interfaces for CivicOS
 * Matches civic-app-schema.json
 */

// ============================================================================
// Core Entities (Backend Schema)
// ============================================================================

export interface CivicEvent {
  id: string;
  title: string;
  description: string;
  when: string; // ISO 8601 date-time
  deadline: string; // ISO 8601 date-time
  engagement_info: string;
  impact_summary: string;
  source_url: string;
  location?: string;
  meeting_type?: 'city_council' | 'planning_commission' | 'public_hearing' | 'community_meeting' | 'committee';
  project_type?: ProjectType;
  engagement_tier?: 'quick_action' | 'full_engagement' | 'expert_level';
  jurisdiction: Jurisdiction;
  contact_info?: ContactInfo;
  wiki_enhancement?: WikiEnhancement;
  legislative_context?: LegislativeContext;
  agenda_expansion?: AgendaExpansion; // Parsed agenda items from PDF
  created_at?: string;
  scraped_from?: string;
  _metadata?: Record<string, any>; // Platform-specific metadata (Legistar, CivicClerk, etc.)
}

export type ProjectType =
  | 'housing'
  | 'transportation'
  | 'environment'
  | 'budget'
  | 'education'
  | 'development'
  | 'public_safety'
  | 'community'
  | 'elections'
  | 'governance'
  | 'traffic' // Alias for transportation (legacy support)
  | 'infrastructure' // Alias for development (legacy support)
  | 'other';

export interface ContactInfo {
  email: string;
  name?: string;
  title?: string;
  phone?: string;
  office?: string;
}

export interface WikiEnhancement {
  success_strategy: string;
  precedent_examples?: string[];
  recommended_approach?: string;
  related_events?: string[];
}

export interface LegislativeContext {
  state_legislation_refs?: string[];
  federal_program_refs?: string[];
  jurisdiction_specific?: Record<string, {
    amount?: string;
    allocation_deadline?: string;
  }>;
  relevance_summary?: string;
  // Hydrated from API (not in schema refs, but returned by API)
  state_legislation?: StateBill[];
  federal_programs?: FederalProgram[];
}

export interface AgendaExpansion {
  available: boolean;
  source_url?: string;
  parsed: boolean;
  actionable_items: ActionableItem[];
  total_items?: number; // Optional - calculated from items if not provided
  actionable_count?: number; // Optional - calculated from items if not provided
}

export interface ActionableItem {
  item_ref: string; // "7.2"
  title: string;
  description: string;
  actionable: boolean;
  actionable_because?: string;
  project_types: string[]; // ["housing", "environment"]
  legislative_context?: {
    state_legislation_refs: string[];
    federal_program_refs: string[];
  };
}

export interface StateBill {
  bill: string;
  title: string;
  status: string;
  leverage_point: string;
  official_url: string;
  summary?: string;
  keywords?: string[];
  topics?: string[];
  state?: string;
}

export interface FederalProgram {
  program_name: string;
  agency: string;
  leverage_point: string;
  fy2025_allocation?: string;
  info_url: string;
  description?: string;
  keywords?: string[];
  overview?: string;
  program_id?: string;
  topics?: string[];
}

export interface Jurisdiction {
  id: string;
  name: string;
  type: 'city' | 'county' | 'school_district' | 'special_district' | 'state' | 'federal';
  website?: string;
  meeting_calendar_url?: string;
  contact_info?: ContactInfo;
  // Frontend additions from GET /api/jurisdictions
  event_count?: number;
  issue_count?: number;
  cdbg_allocation?: string;
  // Hierarchy fields for jurisdictional tree
  county?: string;
  state?: string;
}

export interface Location {
  street_address?: string;
  city: string;
  county: string;
  state: string;
  postal_code?: string;
  jurisdiction_ids?: string[];
  coordinates?: {
    latitude: number;
    longitude: number;
  };
}

// ============================================================================
// Issue System (Backend Schema)
// ============================================================================

export interface Issue {
  id: string;
  user_id: string;
  description: string;
  issue_type: ProjectType | null;
  jurisdiction_id: string;
  location?: {
    address: string;
    latitude: number;
    longitude: number;
  };
  status: 'open' | 'closed'; // Lifecycle status only. Check matched_events.length > 0 for connection status.
  closed_reason?: 'resolved' | 'duplicate' | 'not-actionable' | 'abandoned'; // Required when status='closed'
  closed_at?: string; // ISO 8601 date-time
  closed_note?: string; // Optional note about closure
  created_at: string; // ISO 8601 date-time
  updated_at: string; // ISO 8601 date-time
  matched_events: EventReference[];
  related_issues: string[]; // Issue IDs
  discussion_group_id?: string;
  // AI-generated content
  ai_title?: string;
  ai_summary?: string;
  ai_generated_at?: string;
  short_name?: string; // Human-readable ID (e.g., "EVICTION-1", "POTHOLE-5")
  ai_analysis?: {
    match_confidence?: number;
    suggested_actions?: string[];
    escalation_probability?: number;
  };
}

// ============================================================================
// Operational Issue System (Session 91 - SeeClickFix Integration)
// ============================================================================

export interface OperationalIssue {
  id: string; // "scf-123"
  source: 'seeclickfix';
  issue_type: 'operational';
  title: string;
  description: string;
  status: 'open' | 'closed' | 'acknowledged';
  category: string;
  location: {
    address: string;
    lat: number;
    lng: number;
    point: any; // GeoJSON Point
  };
  created_at: string;
  updated_at: string;
  reporter: {
    name: string;
    civic_points: number;
  };
  media?: {
    image_url?: string;
    image_thumbnail?: string;
  };
  html_url?: string; // Link to SeeClickFix page
  // Matching data (added by frontend/backend)
  matched_events?: Array<{
    event_id: string;
    confidence: number;
    reasoning: string;
    event?: CivicEvent; // Hydrated event data
  }>;
}

export interface EventReference {
  event_id: string;
  match_score: number | null; // 0-100 for automatic matches, null for manual links
  match_reason?: string | null;
}

export interface IssueTimelineEntry {
  entry_id: string;
  issue_id: string;
  timestamp: string; // ISO 8601 date-time
  event_type: 'filed' | 'matched' | 'linked' | 'status_change' | 'response' | 'action_taken';
  description: string;
  source: 'user' | 'system' | 'admin';
  metadata?: Record<string, any>;
}

// ============================================================================
// Following System (Phase 2 - Task 2)
// ============================================================================

export interface Follow {
  follow_id: string;
  user_id: string;
  focal_type: 'issue' | 'event';
  focal_id: string;
  jurisdiction_id?: string;
  created_at: string; // ISO 8601 date-time
}

export interface CoordinationThread {
  thread_id: string;
  focal_type: 'issue' | 'event';
  focal_id: string;
  created_at: string; // ISO 8601 date-time
  last_message_at?: string; // ISO 8601 date-time
}

export interface FollowInfoResponse {
  follower_count: number;
  thread_id: string | null;
  your_following: boolean;
}

export interface UserFollowsResponse {
  follows: Follow[];
  metadata: {
    total_follows: number;
    issue_follows: number;
    event_follows: number;
  };
}

// ============================================================================
// Coordination Messaging (Phase 2 - Task 3)
// ============================================================================

export interface ThreadMessage {
  message_id: string;
  thread_id: string;
  user_id: string;
  content: string;
  created_at: string; // ISO 8601 date-time
  parent_message_id?: string | null; // For nested threading (Phase 2)
  reply_count?: number; // Number of direct replies (Phase 2)
  replies?: ThreadMessage[]; // Nested replies array (Phase 2)
}

export interface ThreadParticipant {
  user_id: string;
  follow_id: string;
  joined_at: string; // ISO 8601 date-time
  last_seen_at: string; // ISO 8601 date-time
}

export interface ThreadMessagesResponse {
  messages: ThreadMessage[];
  participants: ThreadParticipant[];
  related_issues?: RelatedIssue[]; // For event threads only (Phase 2 - Issue→Discussion Integration)
}

export interface RelatedIssue {
  issue_id: string;
  description_preview: string;
  status: 'open' | 'escalated' | 'resolved'; // Lifecycle status only
  created_at: string; // ISO 8601 date-time
  user_id: string;
  ai_title?: string;
  short_name?: string;
}

export interface SendMessageRequest {
  user_id: string;
  content: string;
  parent_message_id?: string; // Optional parent for nested replies (Phase 2)
}

// Socket.io event types
export interface SocketMessage {
  message_id: string;
  thread_id: string;
  user_id: string;
  content: string;
  created_at: string;
  parent_message_id?: string | null; // For nested threading (Phase 2)
  reply_count?: number; // Number of direct replies (Phase 2)
}

export interface TypingEvent {
  user_id: string;
  thread_id: string;
  is_typing: boolean;
}

export interface ProposedAgendaItem {
  id: string;
  title: string;
  description: string;
  source_issues?: string[];
  supporting_users: string[];
  target_event: string; // Event ID
  status: 'draft' | 'submitted' | 'accepted' | 'rejected';
}

export interface DiscussionGroup {
  id: string;
  platform: 'slack' | 'discord' | 'signal';
  platform_url?: string;
  focal_point_type: 'CivicEvent' | 'Issue' | 'ProposedAgendaItem';
  focal_point_id: string;
  member_count?: number;
  created_at: string;
}

// ============================================================================
// User & Session (Backend Schema)
// ============================================================================

export interface User {
  id: string;
  email: string;
  experience_level: 'new' | 'returning' | 'expert';
  location: Location;
  civic_profile: CivicProfile;
  preferences?: UserPreferences;
  created_at?: string;
  last_active?: string;
}

export interface CivicProfile {
  visits: number;
  interactions: number;
  comments_submitted: number;
  meetings_attended: number;
  neighbors_connected: number;
  issues_followed: string[];
  civic_interests: ProjectType[];
  notification_preferences?: {
    newsletter?: boolean;
    meeting_reminders?: boolean;
    neighbor_updates?: boolean;
    government_responses?: boolean;
  };
}

export interface UserPreferences {
  interface_mode?: 'simple' | 'expert';
  conversation_style?: 'casual' | 'informative' | 'action_oriented';
  privacy_level?: 'private' | 'neighbors_only' | 'public';
  notifications_enabled?: boolean;
  default_jurisdiction?: string;
  workspace_layouts?: Record<string, WorkspaceLayout>;
}

export interface CommunityConnection {
  id: string;
  users: string[]; // User IDs
  shared_interests: string[];
  shared_location: Location;
  connection_type: 'issue_based' | 'geographic' | 'meeting_coordination' | 'comment_collaboration';
  status: 'suggested' | 'connected' | 'active' | 'inactive';
  created_at: string;
  last_interaction?: string;
}

// ============================================================================
// Conversation & Messages (Backend Schema)
// ============================================================================

export interface Conversation {
  id: string;
  user_id: string;
  session_id: string;
  messages: Message[];
  context: ConversationContext;
  ui_state: UIState;
  created_at: string;
  updated_at: string;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: string;
  actions?: MessageAction[];
  context_triggers?: ('show_sidebar' | 'reveal_feature' | 'suggest_neighbor' | 'offer_expert_mode')[];
  metadata?: {
    civic_keywords?: string[];
    detected_issues?: string[];
    user_experience_signals?: string[];
  };
}

export interface MessageAction {
  id: string;
  label: string;
  action_type: 'quick_start' | 'join_discussion' | 'draft_comment' | 'schedule_meeting' | 'connect_neighbors' | 'view_impact' | 'mcp_tool_call';
  mcp_tool?: string;
  mcp_parameters?: Record<string, any>;
  parameters?: Record<string, any>;
  experience_gate?: 'new' | 'returning' | 'expert';
  style?: 'primary' | 'secondary' | 'expert';
}

export interface ConversationContext {
  current_topic?: string;
  civic_issues_mentioned?: string[];
  user_goals?: string[];
  related_events?: string[];
  neighbor_mentions?: string[];
  suggested_actions?: string[];
  conversation_phase?: 'discovery' | 'education' | 'action_planning' | 'community_building' | 'expert_mode';
}

export interface UIState {
  mode: 'simple' | 'expert';
  visible_components: ('sidebar' | 'quick_access' | 'expert_shortcuts' | 'user_context' | 'action_buttons')[];
  sidebar_sections?: ('community' | 'actions' | 'impact' | 'progress')[];
  feature_revelations?: Record<string, boolean>;
  personalization?: {
    header_style?: string;
    quick_actions?: string[];
    default_suggestions?: string[];
  };
}

// ============================================================================
// Workspace Types (Frontend-Specific)
// ============================================================================

export interface ArtifactTab {
  id: string;
  type: ArtifactType;
  title: string;
  pinned: boolean;
  data: any; // CivicEvent | Issue | ProposedAgendaItem | etc.
}

export type ArtifactType = 'event' | 'issue' | 'proposal' | 'discussion' | 'legislative' | 'wiki';

export interface WorkspaceLayout {
  mode: 'single' | 'split-h' | 'split-v' | 'grid';
  openTabs: ArtifactTab[];
  activeTabId: string | null;
  sidebarCollapsed: boolean;
  chatPanelVisible: boolean;
  chatPanelHeight: number;
}

// ============================================================================
// API Request/Response Types
// ============================================================================

export interface APIResponse<T> {
  data?: T;
  error?: string;
  status: number;
}

export interface ConversationRequest {
  message: string;
  context?: {
    type: ArtifactType;
    id: string;
  };
  user_id?: string;
  city?: string;
  event_context?: {
    title?: string;
    description?: string;
    when?: string;
    project_type?: string;
  };
}

export interface ConversationResponse {
  response: string;
  actions?: MessageAction[];
  suggested_artifacts?: ArtifactTab[];
  // Issue filing response
  issue_id?: string;
  matched_events?: EventReference[];
}

export interface JurisdictionsResponse {
  jurisdictions: Jurisdiction[];
  metadata: {
    total_count: number;
    total_events: number;
    total_issues: number;
  };
}

export interface IssuesResponse {
  issues: Issue[];
  metadata: {
    total_issues: number;
    matched_count: number;
    open_count: number;
  };
}

export interface FileIssueRequest {
  user_id: string;
  description: string;
  jurisdiction_id: string;
  issue_type?: ProjectType;
  location?: {
    address?: string;
    latitude?: number;
    longitude?: number;
  };
}

export interface FileIssueResponse {
  issue_id: string;
  status: 'open'; // Always 'open' on creation (lifecycle status). Check matched_events.length > 0 for connection status.
  matched_events: Array<{
    event_id: string;
    title: string;
    when: string;
    meeting_type: string;
    match_score: number;
    match_reason: string;
  }>;
  message: string;
}

export interface EventsResponse {
  events: CivicEvent[];
  metadata?: {
    jurisdiction_id?: string;
    project_type?: string;
    count: number;
  };
}

// ============================================================================
// Newsletter (Backend Schema)
// ============================================================================

export interface Newsletter {
  id: string;
  jurisdiction: Jurisdiction;
  events: CivicEvent[];
  generation_metadata?: {
    scrape_urls?: string[];
    ai_model_used?: string;
    wiki_files_loaded?: string[];
    generation_cost?: number;
    processing_time?: number;
  };
  html_content: string;
  text_content: string;
  subject_line: string;
  send_date?: string;
  recipients?: string[];
  analytics?: {
    sent_count?: number;
    open_rate?: number;
    click_rate?: number;
    action_conversion_rate?: number;
  };
  created_at: string;
}

// ============================================================================
// Wiki Knowledge (Backend Schema)
// ============================================================================

export interface WikiKnowledge {
  id: string;
  type: 'jurisdiction' | 'strategy' | 'law' | 'government_structure' | 'template';
  title: string;
  content: string;
  jurisdiction_scope?: string[];
  topic_tags?: string[];
  last_updated?: string;
  file_path: string;
}

// ============================================================================
// Civic Action (Backend Schema)
// ============================================================================

export interface CivicAction {
  id: string;
  user_id: string;
  event_id?: string;
  action_type: 'comment_submitted' | 'meeting_attended' | 'petition_signed' | 'neighbor_connected' | 'discussion_joined';
  status: 'planned' | 'completed' | 'responded_to';
  content?: string;
  government_response?: string;
  impact_measured?: string;
  created_at: string;
  completed_at?: string;
  response_received_at?: string;
}

// ============================================================================
// Helper Types
// ============================================================================

export interface AppSession {
  id: string;
  user_id: string;
  conversation_id: string;
  device_info?: {
    user_agent?: string;
    screen_size?: string;
    mobile?: boolean;
  };
  feature_usage?: Record<string, number>;
  civic_progression?: {
    experience_signals?: string[];
    readiness_for_expert_mode?: boolean;
    feature_unlock_history?: string[];
  };
  started_at: string;
  last_activity: string;
}

export interface AppContext {
  current_user: User;
  active_session: AppSession;
  current_conversation: Conversation;
  available_events: CivicEvent[];
  user_communities?: CommunityConnection[];
  user_actions_history?: CivicAction[];
  relevant_wiki_knowledge?: WikiKnowledge[];
  app_configuration?: {
    feature_flags?: Record<string, boolean>;
    ai_model_settings?: {
      primary_model?: string;
      temperature?: number;
      max_tokens?: number;
    };
    ui_customization?: {
      theme?: string;
      progressive_disclosure_speed?: 'slow' | 'medium' | 'fast';
    };
  };
}

// ============================================================================
// User Location (Phase 3 - Task 1)
// ============================================================================

export interface UserLocation {
  lat: number;
  lng: number;
  city: string;
  county: string;
  state: string;
  street_name?: string;
  jurisdictions: {
    city?: string;
    county?: string;
  };
}

export interface LocationValidation {
  valid: boolean;
  distance_miles: number;
  ip_location: {
    city: string;
    region: string;
    lat: number;
    lng: number;
  } | null;
  reason: string;
}

export interface SetLocationResponse {
  location: UserLocation;
  validation: LocationValidation;
}

// ============================================================================
// Admin Status (Pilot Phase - Ingestion Visibility)
// ============================================================================

export interface AdminStatusResponse {
  status: 'healthy' | 'degraded' | 'unhealthy';
  timestamp: string;
  jurisdiction: string;
  database: {
    status: 'connected' | 'missing' | 'error';
    path?: string;
    size_bytes?: number;
    meetings: {
      count: number;
      earliest: string | null;
      latest: string | null;
      last_updated: string | null;
    };
    agenda_items: {
      count: number;
      last_enriched: string | null;
    };
    issues: {
      count: number;
      last_updated: string | null;
      by_status?: {
        open?: number;
        closed?: number;
      };
    };
    initiatives: {
      count: number;
      last_updated: string | null;
    };
  };
  // SESSION 338: StorageBackend stats (4-stage pipeline)
  storage?: {
    status: 'connected' | 'unavailable' | 'error';
    backend_type?: string;
    meetings?: {
      count: number;
      earliest: string | null;
      latest: string | null;
      last_updated: string | null;
    };
    agenda_items?: {
      count: number;
    };
    size_bytes?: number | null;
    error?: string;
  };
  chromadb: {
    status: 'connected' | 'no_storage' | 'error' | 'chromadb_not_installed';
    path?: string;
    size_bytes?: number;
    total_documents?: number;
    collections?: {
      [key: string]: {
        name: string;
        count: number;
        created_at: string | null;
        metadata?: Record<string, any>;
      } | null;
    };
  };
  files?: {
    participation_db_size_bytes?: number;
    state_db_size_bytes?: number;
  };
  sources?: {
    meetings?: {
      platform: string;
      available: number | null;
      by_type?: Record<string, number>;
      last_checked?: string;
      error?: string;
      // Coverage data (SESSION 305)
      configured_count?: number;
      discovered_count?: number;
      missing?: string[];
      coverage_percent?: number;
    };
    error?: string;
    _cached_at?: number;
    _from_cache?: boolean;
  } | null;
  // SESSION 358: Sample data for interactive previews
  samples?: {
    meetings: Array<{
      id: string;
      title: string;
      date: string;
      body: string;
    }>;
    search_test?: {
      query: string;
      collection: string;
      results: Array<{
        id: string;
        distance: number | null;
        preview: string;
      }>;
    } | null;
  } | null;
}

/**
 * Response from admin trigger operations (now async)
 * Backend: POST /api/admin/trigger
 * SESSION 341: Now returns operation_id for async tracking
 */
export interface AdminTriggerResponse {
  status: 'accepted' | 'error';
  operation_id?: string;
  operation: string;
  jurisdiction: string;
  message?: string;
  poll_url?: string;
  // Error fields
  error?: string;
  operation_name?: string; // when blocked by running operation
  started_at?: string;
  supported_operations?: string[];
}

/**
 * Operation result data (stored in result_json)
 * SESSION 341: Unified result structure
 */
export interface OperationResult {
  status: 'success' | 'error';
  operation: string;
  jurisdiction: string;
  timestamp: string;
  // fetch_meetings fields
  count_fetched?: number;
  count_normalized?: number;
  count_stored?: number;
  count_new?: number;
  // discover_videos fields (SESSION 303)
  count_meetings?: number;
  count_meetings_with_video?: number;
  count_videos_discovered?: number;
  // download_audio fields (SESSION 306)
  count_pending?: number;
  count_downloaded?: number;
  count_skipped?: number;
  count_errors?: number;
  // transcribe_videos fields (SESSION 307)
  count_with_video?: number;
  count_transcribed?: number;
  count_no_captions?: number;
  // refresh_seeclickfix fields (SESSION 308)
  count_updated?: number;
  // Common fields
  duration_seconds?: number;
  error?: string;
}

/**
 * Progress tracking for operations
 * SESSION 341: Server-side progress
 */
export interface OperationProgress {
  percent: number;
  current_step: string | null;
  items_processed: number;
  items_total: number;
}

/**
 * Server-side operation status response
 * Backend: GET /api/admin/operations/{operation_id}
 * SESSION 341: Full operation tracking
 */
export interface OperationStatus {
  operation_id: string;
  name: string;
  jurisdiction_id: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  started_at: string;
  completed_at: string | null;
  duration_seconds: number | null;
  progress: OperationProgress;
  result: OperationResult | null;
  error: string | null;
}

/**
 * List operations response
 * Backend: GET /api/admin/operations
 * SESSION 341: Operations history
 */
export interface OperationsListResponse {
  operations: OperationListItem[];
  count: number;
  filters: {
    jurisdiction: string | null;
    status: string | null;
    limit: number;
  };
}

/**
 * Compact operation item for list view
 */
export interface OperationListItem {
  operation_id: string;
  name: string;
  jurisdiction_id: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  started_at: string;
  completed_at: string | null;
  duration_seconds: number | null;
  progress_percent: number;
  error: string | null;
}

/**
 * Running operation state for admin progress indicator
 * SESSION 309/341: Now tracks server-side operation_id
 */
export interface RunningOperation {
  operation_id: string;
  operation: string;
  startedAt: Date;
  label: string;
}

/**
 * Data browser response for admin data endpoints
 * SESSION 363: Added missing type for data browser
 */
export interface DataBrowserResponse {
  data_type: string;
  jurisdiction: string;
  items: Record<string, any>[];
  total: number;
  page: number;
  per_page: number;
  total_pages: number;
  schema: Record<string, string>;
  note?: string;
}

// ============================================================================
// Vector Stats Types (SESSION 367: Dynamic corpus support)
// ============================================================================

/**
 * Stats for a single vector collection/corpus
 * SESSION 367: Unified type for all corpus types from API
 */
export interface VectorCollectionStats {
  vector_count: number;
  source_count: number;
  coverage_percent: number | null;
  source_table: string | null;  // null for corpus-only types
  collection_suffix: string;
  one_to_one: boolean;
  linkage_status: 'linked' | 'corpus_only' | 'not_indexed' | 'empty';
  linked_count: number;
  available: boolean;
  corpus_source?: string | null;  // e.g., "nov17_chunks.json"
}

/**
 * Corpus type enumeration
 * SESSION 367: All corpus types returned by UnifiedSearch.get_available_corpora()
 */
export type CorpusType =
  | 'decision'
  | 'pdf'
  | 'issue'
  | 'transcript'
  | 'municipal_code'
  | 'legislation'
  | 'programs';

/**
 * Vector stats response from /api/admin/vector-stats
 * SESSION 367: Dynamic collections keyed by CorpusType
 */
export interface VectorStatsResponse {
  jurisdiction_id: string;
  collections: Record<string, VectorCollectionStats>;  // Keyed by corpus type
  embedding_model: string;
  embedding_dimension: number;
}

// ============================================================================
// Voice Counts (Coordination Protocol - Pilot Phase)
// ============================================================================

/**
 * Voice count response from coordination API
 * GET /api/coordination/voice/counts/{entity}
 *
 * Entity format: decision:{jurisdiction}:{date}:{item-ref}
 * Example: decision:city-san-rafael:2026-02-03:item-6a
 */
export interface VoiceCountResponse {
  entity: string;
  support: number;
  oppose: number;
  watching: number;
  total: number;
}

// ============================================================================
// MCP Registry (Discovery of CivicOS MCP Servers)
// ============================================================================

/**
 * Location information for an MCP operator
 */
export interface MCPOperatorLocation {
  city: string;
  county?: string;
  state: string;
}

/**
 * Contact information for an MCP operator
 */
export interface MCPOperatorContact {
  organization: string;
  url?: string;
  email?: string;
}

/**
 * Health status of an MCP operator
 */
export interface MCPOperatorHealth {
  status: 'healthy' | 'unhealthy' | 'unknown';
  tools_count?: number;
  checked_at: string;
  response_time_ms?: number;
}

/**
 * An MCP server operator in the registry
 */
export interface MCPOperator {
  id: string;
  jurisdiction_id: string;
  name: string;
  description?: string;
  mcp_endpoint: string;
  type: 'official' | 'community' | 'experimental';
  status: 'active' | 'inactive' | 'deprecated';
  authoritative_for: string[];
  tools_count?: number;
  location?: MCPOperatorLocation;
  contact?: MCPOperatorContact;
  health?: MCPOperatorHealth;
}

/**
 * Registry metadata
 */
export interface MCPRegistryMetadata {
  protocol_version: string;
  documentation_url?: string;
  github_url?: string;
}

/**
 * Full MCP server registry response
 * GET /api/mcp/registry
 */
export interface MCPRegistry {
  version: string;
  updated: string;
  registry_url?: string;
  operators: MCPOperator[];
  metadata?: MCPRegistryMetadata;
}
