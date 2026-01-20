import type {
  CivicEvent,
  Issue,
  OperationalIssue,
  Jurisdiction,
  JurisdictionsResponse,
  IssuesResponse,
  FileIssueRequest,
  FileIssueResponse,
  ConversationRequest,
  ConversationResponse,
  StateBill,
  FederalProgram,
  IssueTimelineEntry,
  FollowInfoResponse,
  UserFollowsResponse,
  ThreadMessagesResponse,
  SendMessageRequest,
  ThreadMessage,
  SetLocationResponse,
  AdminStatusResponse,
  AdminTriggerResponse,
  OperationStatus,
  OperationsListResponse,
  DataBrowserResponse,
  VectorStatsResponse
} from '@/types/civic';

/**
 * Civic API Service
 *
 * Type-safe client for the CivicOS backend API.
 * Uses Vite proxy configuration to route /api requests to backend server.
 */
class CivicAPI {
  private baseURL: string;
  private apiKey: string;

  constructor() {
    // In development, Vite proxy routes /api → http://localhost:8001
    // In production, API should be served from same origin
    this.baseURL = import.meta.env.VITE_API_BASE_URL || '';
    this.apiKey = import.meta.env.VITE_API_KEY || 'dev_key_local';
  }

  /**
   * Get authentication headers for API requests
   */
  private getAuthHeaders(): HeadersInit {
    return {
      'Authorization': `Bearer ${this.apiKey}`,
      'Content-Type': 'application/json'
    };
  }

  /**
   * Get all jurisdictions with event counts
   * GET /api/jurisdictions
   *
   * Backend: routers/:623-770
   */
  async getJurisdictions(): Promise<Jurisdiction[]> {
    const response = await fetch(`${this.baseURL}/api/jurisdictions`, {
      headers: this.getAuthHeaders()
    });
    if (!response.ok) {
      throw new Error(`Failed to fetch jurisdictions: ${response.statusText}`);
    }
    const data: JurisdictionsResponse = await response.json();
    return data.jurisdictions;
  }

  /**
   * Get all events with optional filters
   * GET /api/events?jurisdiction_id=...&project_type=...&start_date=...
   *
   * Backend: routers/ (existing endpoint)
   */
  async getEvents(filters?: {
    jurisdiction_id?: string;
    project_type?: string;
    start_date?: string;
  }): Promise<CivicEvent[]> {
    const params = new URLSearchParams();
    if (filters) {
      Object.entries(filters).forEach(([key, value]) => {
        if (value) params.append(key, value);
      });
    }

    const url = `${this.baseURL}/api/events${params.toString() ? '?' + params.toString() : ''}`;
    const response = await fetch(url, {
      headers: this.getAuthHeaders()
    });

    if (!response.ok) {
      throw new Error(`Failed to fetch events: ${response.statusText}`);
    }

    return response.json();
  }

  /**
   * Search events with advanced filtering (Session 28 - Chat UX Refinements)
   * GET /api/events/search?jurisdiction=...&topic=...&q=...&date_range=...
   *
   * Backend: routers/:798-868
   */
  async searchEvents(params: {
    jurisdiction?: string;
    topic?: string;
    query?: string;
    dateRange?: string;
  }): Promise<{ events: CivicEvent[]; count: number; query: any; jurisdictions_searched: string[] }> {
    const queryParams = new URLSearchParams();

    if (params.jurisdiction) queryParams.append('jurisdiction', params.jurisdiction);
    if (params.topic) queryParams.append('topic', params.topic);
    if (params.query) queryParams.append('q', params.query);
    if (params.dateRange) queryParams.append('date_range', params.dateRange);

    const url = `${this.baseURL}/api/events/search?${queryParams.toString()}`;
    const response = await fetch(url, {
      headers: this.getAuthHeaders()
    });

    if (!response.ok) {
      throw new Error(`Failed to search events: ${response.statusText}`);
    }

    return response.json();
  }

  /**
   * Search user's issues with filtering (Session 63 - Robust Fix)
   * GET /api/issues/search?user_id=...&ownership=...&status=...&category=...&jurisdiction=...&q=...
   *
   * Backend: routers/:1084-1250
   */
  async searchIssues(params: {
    user_id: string;
    ownership?: string;  // Session 63: Separate from status
    status?: string;
    category?: string;
    jurisdiction?: string;
    q?: string;
  }): Promise<{ issues: any[]; count: number; query: any; filters_applied: any }> {
    const queryParams = new URLSearchParams();

    queryParams.append('user_id', params.user_id);
    if (params.ownership) queryParams.append('ownership', params.ownership);
    if (params.status) queryParams.append('status', params.status);
    if (params.category) queryParams.append('category', params.category);
    if (params.jurisdiction) queryParams.append('jurisdiction', params.jurisdiction);
    if (params.q) queryParams.append('q', params.q);

    const url = `${this.baseURL}/api/issues/search?${queryParams.toString()}`;
    const response = await fetch(url, {
      headers: this.getAuthHeaders()
    });

    if (!response.ok) {
      throw new Error(`Failed to search issues: ${response.statusText}`);
    }

    return response.json();
  }

  /**
   * Get single event by ID
   * GET /api/events/{id}
   *
   * Backend: routers/ (existing endpoint)
   */
  async getEvent(id: string): Promise<CivicEvent> {
    const response = await fetch(`${this.baseURL}/api/events/${id}`, {
      headers: this.getAuthHeaders()
    });
    if (!response.ok) {
      throw new Error(`Failed to fetch event ${id}: ${response.statusText}`);
    }
    return response.json();
  }

  /**
   * Get discussion stats for multiple events (Session 33 - Event Discovery)
   * GET /api/events/discussion-stats?event_ids=event1,event2,event3
   *
   * Backend: routers/:2075-2138
   */
  async getEventDiscussionStats(eventIds: string[]): Promise<{
    stats: Array<{
      event_id: string;
      thread_id: string;
      participant_count: number;
      message_count: number;
    }>;
  }> {
    const url = `${this.baseURL}/api/events/discussion-stats?event_ids=${eventIds.join(',')}`;

    const response = await fetch(url, {
      headers: this.getAuthHeaders()
    });

    if (!response.ok) {
      throw new Error(`Failed to fetch discussion stats: ${response.statusText}`);
    }

    return response.json();
  }

  /**
   * Generate AI-powered comment draft for civic event (Session 39 - Auto-inference)
   * POST /api/events/{event_id}/draft-comment
   *
   * Backend: routers/:2012-2250
   *
   * All fields are optional - AI will infer from event/agenda context
   * Session 41: Added archetypes for personalized comment framing (Privacy Tier 1)
   */
  async draftComment(eventId: string, request: {
    userId?: string;  // Optional - for tracking
    archetypes?: Array<{id: string; name: string; score: number; description: string}>;  // Privacy Tier 1
    position?: 'support' | 'oppose' | 'neutral' | 'questions';  // Optional - AI infers
    keyConcern?: string;  // Optional - AI infers from event
    personalContext?: {
      stakes?: string[];
      yearsInArea?: number;
      district?: string;
      expertise?: string;
    };
    agendaItemId?: string;
  } = {}): Promise<{
    draft: string;
    word_count: number;
    estimated_speaking_time: string;
    comment_id: string;
    structured_summary?: {
      tldr: string;
      position: 'support' | 'oppose' | 'neutral' | 'questions';
      key_topics: string[];
      legislative_references: string[];
      primary_archetype?: string;
    };
  }> {
    const response = await fetch(`${this.baseURL}/api/events/${eventId}/draft-comment`, {
      method: 'POST',
      headers: this.getAuthHeaders(),
      body: JSON.stringify(request)
    });

    if (!response.ok) {
      throw new Error(`Failed to generate comment draft: ${response.statusText}`);
    }

    return response.json();
  }

  /**
   * Get existing draft comment for an event (Session 45 - Draft Persistence)
   * GET /api/events/{eventId}/draft-comment?user_id={userId}
   *
   * Returns most recent draft or null if none exists.
   * Enables Google Docs-style draft loading without API generation cost.
   *
   * Backend: routers/:handle_get_draft
   */
  async getDraft(eventId: string, userId: string): Promise<{
    draft_id: string | null;
    draft: string | null;
    structured_summary: any;
    personal_context: any;
    selected_agenda_items: string[];
    is_template: boolean;
    created_at: string;
    updated_at: string;
    submitted: boolean;
  }> {
    const response = await fetch(
      `${this.baseURL}/api/events/${eventId}/draft-comment?user_id=${encodeURIComponent(userId)}`,
      { headers: this.getAuthHeaders() }
    );

    if (!response.ok) {
      throw new Error(`Failed to load draft: ${response.statusText}`);
    }

    return response.json();
  }

  /**
   * Update draft comment (autosave) (Session 45 - Draft Persistence)
   * PUT /api/drafts/{draftId}
   *
   * Updates draft content from user edits (debounced autosave).
   *
   * Backend: routers/:handle_update_draft
   */
  async updateDraft(draftId: string, data: { content: string }): Promise<{ success: boolean; updated_at: string }> {
    const response = await fetch(
      `${this.baseURL}/api/drafts/${draftId}`,
      {
        method: 'PUT',
        headers: this.getAuthHeaders(),
        body: JSON.stringify(data)
      }
    );

    if (!response.ok) {
      throw new Error(`Failed to save draft: ${response.statusText}`);
    }

    return response.json();
  }

  /**
   * Mark draft as submitted (Session 45 - Draft Persistence)
   * POST /api/drafts/{draftId}/submit
   *
   * Marks draft as submitted after user emails to clerk.
   *
   * Backend: routers/:handle_mark_draft_submitted
   */
  async markDraftSubmitted(draftId: string): Promise<{ success: boolean }> {
    const response = await fetch(
      `${this.baseURL}/api/drafts/${draftId}/submit`,
      {
        method: 'POST',
        headers: this.getAuthHeaders()
      }
    );

    if (!response.ok) {
      throw new Error(`Failed to mark draft as submitted: ${response.statusText}`);
    }

    return response.json();
  }

  /**
   * Get all drafts for an event (Session 46 - Multi-Draft System)
   * GET /api/events/{eventId}/drafts?user_id={userId}
   *
   * Returns all drafts for this user+event (multi-draft system).
   * Each draft is keyed by agenda item selection.
   *
   * Backend: routers/:handle_get_all_drafts
   */
  async getAllDrafts(eventId: string, userId: string): Promise<{
    drafts: Array<{
      draft_id: string;
      content: string;
      content_preview: string;
      structured_summary: any;
      personal_context: any;
      selected_agenda_items: string[];
      created_at: string;
      updated_at: string;
      submitted: boolean;
    }>;
  }> {
    const response = await fetch(
      `${this.baseURL}/api/events/${eventId}/drafts?user_id=${encodeURIComponent(userId)}`,
      { headers: this.getAuthHeaders() }
    );

    if (!response.ok) {
      throw new Error(`Failed to load drafts: ${response.statusText}`);
    }

    return response.json();
  }

  /**
   * Regenerate comment for single agenda item (Session 47 - Per-Item Memoization)
   * POST /api/events/{eventId}/items/{itemRef}/regenerate
   *
   * Regenerates comment for one specific item (bypasses cache).
   * Used when user wants to improve one section without affecting others.
   *
   * Backend: routers/:handle_regenerate_item_comment
   */
  async regenerateItemComment(
    eventId: string,
    itemRef: string,
    request: {
      userId: string;
      archetypes: any[];
      personalContext: any;
    }
  ): Promise<{
    content: string;
    word_count: number;
    item_ref: string;
  }> {
    const response = await fetch(
      `${this.baseURL}/api/events/${eventId}/items/${itemRef}/regenerate`,
      {
        method: 'POST',
        headers: this.getAuthHeaders(),
        body: JSON.stringify(request)
      }
    );

    if (!response.ok) {
      throw new Error(`Failed to regenerate item: ${response.statusText}`);
    }

    return response.json();
  }

  /**
   * Delete draft (Session 48)
   * DELETE /api/drafts/{draftId}
   */
  async deleteDraft(draftId: string): Promise<{ success: boolean; message: string }> {
    const response = await fetch(
      `${this.baseURL}/api/drafts/${draftId}`,
      {
        method: 'DELETE',
        headers: this.getAuthHeaders()
      }
    );

    if (!response.ok) {
      throw new Error(`Failed to delete draft: ${response.statusText}`);
    }

    return response.json();
  }

  /**
   * Get operational issues (SeeClickFix complaints) for a jurisdiction
   * GET /api/operational-issues/{jurisdiction_id}
   *
   * Backend: routers/ (Session 90 - SeeClickFix Integration)
   */
  async getOperationalIssues(
    jurisdictionId: string,
    filters?: {
      status?: 'open' | 'closed' | 'acknowledged';
      perPage?: number;
      page?: number;
    }
  ): Promise<{ issues: OperationalIssue[]; metadata: { total: number; page: number; per_page: number } }> {
    const params = new URLSearchParams();
    if (filters?.status) params.append('status', filters.status);
    if (filters?.perPage) params.append('per_page', filters.perPage.toString());
    if (filters?.page) params.append('page', filters.page.toString());

    const url = `${this.baseURL}/api/operational-issues/${jurisdictionId}${params.toString() ? '?' + params.toString() : ''}`;
    const response = await fetch(url, {
      headers: this.getAuthHeaders()
    });

    if (!response.ok) {
      throw new Error(`Failed to fetch operational issues: ${response.statusText}`);
    }

    return response.json();
  }

  /**
   * Get all complaints for a user
   * GET /api/issues?user_id={user}
   *
   * Backend: routers/:772-849
   */
  async getComplaints(user_id: string | null): Promise<Issue[]> {
    const url = user_id
      ? `${this.baseURL}/api/issues?user_id=${encodeURIComponent(user_id)}`
      : `${this.baseURL}/api/issues`;
    const response = await fetch(url, {
      headers: this.getAuthHeaders()
    });
    if (!response.ok) {
      throw new Error(`Failed to fetch complaints: ${response.statusText}`);
    }
    const data: IssuesResponse = await response.json();

    // DEBUG: Log first complaint's related_complaints
    if (data.issues.length > 0) {
      console.log('[API] Sample complaint data:', {
        id: data.issues[0].id,
        issue_type: data.issues[0].issue_type,
        related_complaints: data.issues[0].related_issues,
        related_count: data.issues[0].related_issues?.length || 0
      });
    }

    return data.issues;
  }

  /**
   * File a new complaint with automatic event matching
   * POST /api/issues
   *
   * Backend: routers/:901-1035
   */
  async fileComplaint(request: FileIssueRequest): Promise<FileIssueResponse> {
    const response = await fetch(`${this.baseURL}/api/issues`, {
      method: 'POST',
      headers: this.getAuthHeaders(),
      body: JSON.stringify(request)
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ error: response.statusText }));
      throw new Error(error.error || 'Failed to file complaint');
    }

    return response.json();
  }

  /**
   * Send a message to the conversational AI
   * POST /api/conversation
   *
   * Backend: routers/ (existing endpoint)
   */
  async sendMessage(request: ConversationRequest): Promise<ConversationResponse> {
    const response = await fetch(`${this.baseURL}/api/conversation`, {
      method: 'POST',
      headers: this.getAuthHeaders(),
      body: JSON.stringify(request)
    });

    if (!response.ok) {
      throw new Error(`Failed to send message: ${response.statusText}`);
    }

    return response.json();
  }

  /**
   * Set user location via geocoding
   * POST /api/user/location
   *
   * Backend: routers/:1790-1903
   */
  async setUserLocation(userId: string, address: string): Promise<SetLocationResponse> {
    const response = await fetch(`${this.baseURL}/api/user/location`, {
      method: 'POST',
      headers: this.getAuthHeaders(),
      body: JSON.stringify({ user_id: userId, address })
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ error: response.statusText }));
      throw new Error(error.error || 'Failed to set location');
    }

    return response.json();
  }

  /**
   * Get user location
   * GET /api/user/location?user_id={user_id}
   *
   * Backend: routers/:1905-1936
   */
  async getUserLocation(userId: string): Promise<SetLocationResponse> {
    const response = await fetch(`${this.baseURL}/api/user/location?user_id=${encodeURIComponent(userId)}`, {
      headers: this.getAuthHeaders()
    });

    if (!response.ok) {
      throw new Error(`Failed to get user location: ${response.statusText}`);
    }

    return response.json();
  }

  /**
   * Get user profile with demographics and preferences (Session 39)
   * GET /api/user/profile
   *
   * Backend: routers/:3247-3289
   */
  async getUserProfile(): Promise<{
    user_id: string;
    display_name?: string;
    jurisdiction_id?: string;
    stakes?: string[];
    years_in_area?: number;
    district?: string;
    expertise?: string;
    civic_interests?: string[];
    profile_completeness?: number;
  }> {
    const response = await fetch(`${this.baseURL}/api/user/profile`, {
      headers: this.getAuthHeaders()
    });

    if (!response.ok) {
      // Profile not found is okay - user may not have created one yet
      if (response.status === 404) {
        return { user_id: '', stakes: [], civic_interests: [] };
      }
      throw new Error(`Failed to get user profile: ${response.statusText}`);
    }

    return response.json();
  }

  /**
   * Get state bills by topic
   * GET /api/legislation/state/{topic}
   *
   * Backend: src/civic_services/servers/routers/legislative.py
   */
  async getStateBills(topic: string): Promise<{ bills: StateBill[]; metadata: any }> {
    const response = await fetch(`${this.baseURL}/api/legislation/state/${encodeURIComponent(topic)}`, {
      headers: this.getAuthHeaders()
    });

    if (!response.ok) {
      throw new Error(`Failed to fetch state bills: ${response.statusText}`);
    }

    return response.json();
  }

  /**
   * Get federal programs by topic
   * GET /api/legislation/federal/{topic}
   *
   * Backend: src/civic_services/servers/routers/legislative.py
   */
  async getFederalPrograms(topic: string): Promise<{ programs: FederalProgram[]; metadata: any }> {
    const response = await fetch(`${this.baseURL}/api/legislation/federal/${encodeURIComponent(topic)}`, {
      headers: this.getAuthHeaders()
    });

    if (!response.ok) {
      throw new Error(`Failed to fetch federal programs: ${response.statusText}`);
    }

    return response.json();
  }

  /**
   * Get timeline for a complaint
   * GET /api/issues/{id}/timeline
   *
   * Backend: routers/:1084-1126
   */
  async getComplaintTimeline(issueId: string): Promise<IssueTimelineEntry[]> {
    const response = await fetch(`${this.baseURL}/api/issues/${issueId}/timeline`, {
      headers: this.getAuthHeaders()
    });

    if (!response.ok) {
      throw new Error(`Failed to fetch complaint timeline: ${response.statusText}`);
    }

    const data = await response.json();
    return data.timeline;
  }

  /**
   * Get issue status history (filed + status changes only)
   * GET /api/issues/{id}/status-history
   *
   * Backend: routers/:1584-1629
   */
  async getIssueStatusHistory(issueId: string): Promise<IssueTimelineEntry[]> {
    const response = await fetch(`${this.baseURL}/api/issues/${issueId}/status-history`, {
      headers: this.getAuthHeaders()
    });

    if (!response.ok) {
      throw new Error(`Failed to fetch issue status history: ${response.statusText}`);
    }

    const data = await response.json();
    return data.history;
  }

  /**
   * Update issue status
   * PUT /api/issues/{id}/status
   *
   * Backend: routers/:1639-1738
   */
  async updateComplaintStatus(
    issueId: string,
    status: 'open' | 'closed',
    note?: string,
    closed_reason?: 'resolved' | 'duplicate' | 'not-actionable' | 'abandoned'
  ): Promise<{ success: boolean; issue_id: string; new_status: string; closed_reason?: string; message: string }> {
    const body: { status: string; note?: string; closed_reason?: string } = { status };
    if (note) body.note = note;
    if (closed_reason) body.closed_reason = closed_reason;

    const response = await fetch(`${this.baseURL}/api/issues/${issueId}/status`, {
      method: 'PUT',
      headers: this.getAuthHeaders(),
      body: JSON.stringify(body)
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ error: response.statusText }));
      throw new Error(error.error || 'Failed to update issue status');
    }

    return response.json();
  }

  /**
   * Manually link complaint to events (Phase 2 - Task 1)
   * POST /api/issues/{id}/link-events
   *
   * Backend: routers/:1218-1308
   */
  async linkComplaintToEvents(
    issueId: string,
    eventIds: string[]
  ): Promise<{ success: boolean; issue_id: string; linked_count: number; invalid_event_ids: string[]; message: string; complaint: Issue }> {
    const response = await fetch(`${this.baseURL}/api/issues/${issueId}/link-events`, {
      method: 'POST',
      headers: this.getAuthHeaders(),
      body: JSON.stringify({ event_ids: eventIds })
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ error: response.statusText }));
      throw new Error(error.error || 'Failed to link events to complaint');
    }

    return response.json();
  }

  /**
   * Get follow information for a focal point (Phase 2 - Task 2)
   * GET /api/follows/{focal_type}/{focal_id}?user_id={user_id}
   *
   * Backend: routers/:1400-1439
   */
  async getFollowInfo(
    focalType: 'issue' | 'event',
    focalId: string,
    userId?: string
  ): Promise<FollowInfoResponse> {
    const params = userId ? `?user_id=${encodeURIComponent(userId)}` : '';
    const response = await fetch(`${this.baseURL}/api/follows/${focalType}/${focalId}${params}`, {
      headers: this.getAuthHeaders()
    });

    if (!response.ok) {
      throw new Error(`Failed to fetch follow info: ${response.statusText}`);
    }

    return response.json();
  }

  /**
   * Create a follow (Phase 2 - Task 2)
   * POST /api/follows
   *
   * Backend: routers/:1441-1517
   */
  async createFollow(
    userId: string,
    focalType: 'issue' | 'event',
    focalId: string,
    jurisdictionId?: string
  ): Promise<{ follower_count: number; thread_id: string; your_following: boolean }> {
    const response = await fetch(`${this.baseURL}/api/follows`, {
      method: 'POST',
      headers: this.getAuthHeaders(),
      body: JSON.stringify({
        user_id: userId,
        focal_type: focalType,
        focal_id: focalId,
        jurisdiction_id: jurisdictionId
      })
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ error: response.statusText }));
      throw new Error(error.error || 'Failed to create follow');
    }

    return response.json();
  }

  /**
   * Delete a follow / unfollow (Phase 2 - Task 2)
   * DELETE /api/follows/{focal_type}/{focal_id}?user_id={user_id}
   *
   * Backend: routers/:1519-1559
   */
  async deleteFollow(
    userId: string,
    focalType: 'issue' | 'event',
    focalId: string
  ): Promise<{ follower_count: number; your_following: boolean }> {
    const response = await fetch(
      `${this.baseURL}/api/follows/${focalType}/${focalId}?user_id=${encodeURIComponent(userId)}`,
      {
        method: 'DELETE',
        headers: this.getAuthHeaders()
      }
    );

    if (!response.ok) {
      const error = await response.json().catch(() => ({ error: response.statusText }));
      throw new Error(error.error || 'Failed to delete follow');
    }

    return response.json();
  }

  /**
   * Get all follows for a user (Phase 2 - Task 2)
   * GET /api/follows?user_id={user_id}
   *
   * Backend: routers/:1937-2013
   */
  async getUserFollows(userId: string): Promise<UserFollowsResponse> {
    const response = await fetch(
      `${this.baseURL}/api/follows?user_id=${encodeURIComponent(userId)}`,
      {
        headers: this.getAuthHeaders()
      }
    );

    if (!response.ok) {
      const error = await response.json().catch(() => ({ error: response.statusText }));
      throw new Error(error.error || 'Failed to get user follows');
    }

    return response.json();
  }

  // ============================================================================
  // Coordination Messaging (Phase 2 - Task 3)
  // ============================================================================

  /**
   * Get messages for a coordination thread
   * @param threadId - Thread ID
   * @param userId - Current user ID (for authentication)
   * @returns Thread messages and participants
   */
  async getThreadMessages(threadId: string, userId: string): Promise<ThreadMessagesResponse> {
    const response = await fetch(
      `${this.baseURL}/api/threads/${threadId}/messages?user_id=${userId}`,
      {
        headers: {
          'Authorization': `Bearer ${this.apiKey}`,
          'Content-Type': 'application/json'
        }
      }
    );

    if (!response.ok) {
      const error = await response.json().catch(() => ({ error: response.statusText }));
      throw new Error(error.error || 'Failed to fetch thread messages');
    }

    return response.json();
  }

  /**
   * Send a message to a coordination thread
   * @param threadId - Thread ID
   * @param request - Message request (user_id, content)
   * @returns Created message
   */
  async sendThreadMessage(threadId: string, request: SendMessageRequest): Promise<ThreadMessage> {
    const response = await fetch(
      `${this.baseURL}/api/threads/${threadId}/messages`,
      {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${this.apiKey}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(request)
      }
    );

    if (!response.ok) {
      const error = await response.json().catch(() => ({ error: response.statusText }));
      throw new Error(error.error || 'Failed to send message');
    }

    return response.json();
  }

  /**
   * Update user's last_seen timestamp for a thread (mark messages as read)
   * @param focalType - Type of focal point (issue/event)
   * @param focalId - ID of focal point
   * @param userId - Current user ID
   */
  async markThreadAsRead(focalType: 'issue' | 'event', focalId: string, userId: string): Promise<void> {
    const response = await fetch(
      `${this.baseURL}/api/follows/${focalType}/${focalId}/mark-read`,
      {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${this.apiKey}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ user_id: userId })
      }
    );

    if (!response.ok) {
      const error = await response.json().catch(() => ({ error: response.statusText }));
      throw new Error(error.error || 'Failed to mark thread as read');
    }
  }

  /**
   * Get a single complaint by ID
   * GET /api/issues/{id}
   *
   * Backend: routers/:1259-1326
   */
  async getIssue(issueId: string): Promise<Issue> {
    const response = await fetch(`${this.baseURL}/api/issues/${issueId}`, {
      headers: this.getAuthHeaders()
    });
    if (!response.ok) {
      if (response.status === 404) {
        throw new Error(`Issue ${issueId} not found`);
      }
      throw new Error(`Failed to fetch complaint: ${response.statusText}`);
    }
    return response.json();
  }

  /**
   * Get all coordination threads
   * GET /api/threads?jurisdiction={jurisdiction_id}
   *
   * Backend: routers/:1811-1858
   */
  async getThreads(options?: { jurisdictionId?: string; limit?: number }): Promise<{
    threads: Array<{
      thread_id: string;
      focal_type: 'issue' | 'event';
      focal_id: string;
      focal_point_title: string;
      participant_count: number;
      message_count: number;
      created_at: string;
      last_message_at: string | null;
    }>;
    count: number;
  }> {
    const params = new URLSearchParams();
    if (options?.jurisdictionId) {
      params.append('jurisdiction', options.jurisdictionId);
    }
    if (options?.limit) {
      params.append('limit', options.limit.toString());
    }

    const url = `${this.baseURL}/api/threads${params.toString() ? '?' + params.toString() : ''}`;

    const response = await fetch(url, {
      headers: this.getAuthHeaders()
    });

    if (!response.ok) {
      throw new Error(`Failed to fetch threads: ${response.statusText}`);
    }

    return response.json();
  }

  /**
   * Get thread info by ID
   * GET /api/threads/{thread_id}
   *
   * Backend: routers/:1860-1902
   */
  async getThreadInfo(threadId: string): Promise<{
    thread_id: string;
    focal_type: 'issue' | 'event';
    focal_id: string;
    participant_count: number;
    message_count: number;
    created_at: string;
    last_message_at: string | null;
  }> {
    const response = await fetch(`${this.baseURL}/api/threads/${threadId}`, {
      headers: this.getAuthHeaders()
    });

    if (!response.ok) {
      if (response.status === 404) {
        throw new Error('Thread not found');
      }
      throw new Error(`Failed to fetch thread info: ${response.statusText}`);
    }

    return response.json();
  }

  // ============================================================================
  // Configuration (Public endpoints - no auth required)
  // ============================================================================

  /**
   * Get Google Maps API key for frontend
   * GET /api/config/google-maps-key (public endpoint)
   *
   * Backend: routers/:2141-2165
   */
  async getGoogleMapsApiKey(): Promise<string> {
    const response = await fetch(`${this.baseURL}/api/config/google-maps-key`, {
      headers: {
        'Content-Type': 'application/json'
      }
      // No Authorization header - this is a public endpoint
    });

    if (!response.ok) {
      throw new Error(`Failed to fetch Google Maps API key: ${response.statusText}`);
    }

    const data = await response.json();
    return data.api_key;
  }

  /**
   * Create or update user profile
   * POST /api/user/profile
   *
   * Backend: routers/ (PersonalizationService Phase 2)
   */
  async createOrUpdateProfile(data: any): Promise<any> {
    const response = await fetch(`${this.baseURL}/api/user/profile`, {
      method: 'POST',
      headers: this.getAuthHeaders(),
      body: JSON.stringify(data)
    });

    if (!response.ok) {
      throw new Error(`Failed to save profile: ${response.statusText}`);
    }

    return response.json();
  }

  /**
   * Delete user account
   * DELETE /api/user
   *
   * Backend: routers/ (PersonalizationService Phase 2 - GDPR)
   */
  async deleteUserAccount(): Promise<void> {
    const response = await fetch(`${this.baseURL}/api/user`, {
      method: 'DELETE',
      headers: this.getAuthHeaders()
    });

    if (!response.ok) {
      throw new Error(`Failed to delete account: ${response.statusText}`);
    }
  }

  /**
   * Export user data (GDPR)
   * GET /api/user/export
   *
   * Backend: routers/ (PersonalizationService Phase 2 - GDPR)
   */
  async exportUserData(): Promise<any> {
    const response = await fetch(`${this.baseURL}/api/user/export`, {
      headers: this.getAuthHeaders()
    });

    if (!response.ok) {
      throw new Error(`Failed to export data: ${response.statusText}`);
    }

    return response.json();
  }

  // ============================================================================
  // Onboarding (Phase 2.5 - Tinder-style swipe onboarding)
  // ============================================================================

  /**
   * Get personalized onboarding card deck
   * GET /api/onboarding/cards
   *
   * Backend: routers/ (Phase 2.5 - Swipe Onboarding)
   */
  async getOnboardingCards(): Promise<{ cards: any[] }> {
    const response = await fetch(`${this.baseURL}/api/onboarding/cards`, {
      headers: this.getAuthHeaders()
    });

    if (!response.ok) {
      throw new Error(`Failed to fetch onboarding cards: ${response.statusText}`);
    }

    return response.json();
  }

  /**
   * Record swipe action during onboarding
   * POST /api/onboarding/swipe
   *
   * Backend: routers/ (Phase 2.5 - Swipe Onboarding)
   */
  async recordOnboardingSwipe(data: {
    card_id: string;
    card_type: string;
    swipe_direction: 'left' | 'right';
    metadata?: any;
  }): Promise<void> {
    const response = await fetch(`${this.baseURL}/api/onboarding/swipe`, {
      method: 'POST',
      headers: this.getAuthHeaders(),
      body: JSON.stringify(data)
    });

    if (!response.ok) {
      throw new Error(`Failed to record swipe: ${response.statusText}`);
    }
  }

  /**
   * Mark onboarding as complete
   * POST /api/onboarding/complete
   *
   * Backend: routers/ (Phase 2.5 - Swipe Onboarding)
   */
  async completeOnboarding(): Promise<void> {
    const response = await fetch(`${this.baseURL}/api/onboarding/complete`, {
      method: 'POST',
      headers: this.getAuthHeaders()
    });

    if (!response.ok) {
      throw new Error(`Failed to complete onboarding: ${response.statusText}`);
    }
  }

  // ============================================================================
  // Admin (Pilot Phase - Ingestion Visibility)
  // ============================================================================

  /**
   * Get admin status (pipeline health, database stats, ChromaDB stats)
   * GET /api/admin/status?jurisdiction={jurisdiction}&include_sources={bool}&refresh_sources={bool}
   *
   * Backend: src/civic_services/servers/routers/admin.py
   */
  async getAdminStatus(
    jurisdiction: string = 'san-rafael',
    options?: { includeSources?: boolean; refreshSources?: boolean; includeSamples?: boolean }
  ): Promise<AdminStatusResponse> {
    const params = new URLSearchParams({
      jurisdiction: jurisdiction
    });

    if (options?.includeSources) {
      params.set('include_sources', 'true');
    }
    if (options?.refreshSources) {
      params.set('refresh_sources', 'true');
    }
    if (options?.includeSamples) {
      params.set('include_samples', 'true');
    }

    const response = await fetch(
      `${this.baseURL}/api/admin/status?${params.toString()}`,
      {
        headers: this.getAuthHeaders()
      }
    );

    if (!response.ok) {
      throw new Error(`Failed to fetch admin status: ${response.statusText}`);
    }

    return response.json();
  }

  /**
   * Trigger fetch meetings operation
   * POST /api/admin/trigger with operation: "fetch_meetings"
   *
   * Backend: src/civic_services/servers/civic_api_integrated.py:7516-7653
   */
  async triggerFetchMeetings(jurisdiction: string = 'san-rafael'): Promise<AdminTriggerResponse> {
    const response = await fetch(
      `${this.baseURL}/api/admin/trigger`,
      {
        method: 'POST',
        headers: this.getAuthHeaders(),
        body: JSON.stringify({
          operation: 'fetch_meetings',
          jurisdiction: jurisdiction
        })
      }
    );

    if (!response.ok) {
      const errorData = await response.json().catch(() => null);
      throw new Error(errorData?.error || `Failed to trigger fetch meetings: ${response.statusText}`);
    }

    return response.json();
  }

  /**
   * Trigger discover videos operation
   * POST /api/admin/trigger with operation: "discover_videos"
   *
   * Scans meetings for YouTube video URLs and returns video counts.
   * Backend: src/civic_services/servers/civic_api_integrated.py:7659-7730
   */
  async triggerDiscoverVideos(jurisdiction: string = 'san-rafael'): Promise<AdminTriggerResponse> {
    const response = await fetch(
      `${this.baseURL}/api/admin/trigger`,
      {
        method: 'POST',
        headers: this.getAuthHeaders(),
        body: JSON.stringify({
          operation: 'discover_videos',
          jurisdiction: jurisdiction
        })
      }
    );

    if (!response.ok) {
      const errorData = await response.json().catch(() => null);
      throw new Error(errorData?.error || `Failed to trigger discover videos: ${response.statusText}`);
    }

    return response.json();
  }

  /**
   * Trigger download audio operation
   * POST /api/admin/trigger with operation: "download_audio"
   *
   * Downloads YouTube audio files from discovered meeting videos.
   * Backend: src/civic_services/servers/civic_api_integrated.py:7807-7938
   */
  async triggerDownloadAudio(jurisdiction: string = 'san-rafael'): Promise<AdminTriggerResponse> {
    const response = await fetch(
      `${this.baseURL}/api/admin/trigger`,
      {
        method: 'POST',
        headers: this.getAuthHeaders(),
        body: JSON.stringify({
          operation: 'download_audio',
          jurisdiction: jurisdiction
        })
      }
    );

    if (!response.ok) {
      const errorData = await response.json().catch(() => null);
      throw new Error(errorData?.error || `Failed to trigger download audio: ${response.statusText}`);
    }

    return response.json();
  }

  /**
   * Trigger transcribe videos operation
   * POST /api/admin/trigger with operation: "transcribe_videos"
   *
   * Transcribes YouTube videos that have audio downloaded but no transcript.
   * Backend: src/civic_services/servers/civic_api_integrated.py
   */
  async triggerTranscribeVideos(jurisdiction: string = 'san-rafael'): Promise<AdminTriggerResponse> {
    const response = await fetch(
      `${this.baseURL}/api/admin/trigger`,
      {
        method: 'POST',
        headers: this.getAuthHeaders(),
        body: JSON.stringify({
          operation: 'transcribe_videos',
          jurisdiction: jurisdiction
        })
      }
    );

    if (!response.ok) {
      const errorData = await response.json().catch(() => null);
      throw new Error(errorData?.error || `Failed to trigger transcribe videos: ${response.statusText}`);
    }

    return response.json();
  }

  /**
   * Trigger refresh SeeClickFix operation
   * POST /api/admin/trigger with operation: "refresh_seeclickfix"
   *
   * Fetches latest 311 issues from SeeClickFix API.
   * Backend: src/civic_services/servers/civic_api_integrated.py
   */
  async triggerRefreshSeeClickFix(jurisdiction: string = 'san-rafael'): Promise<AdminTriggerResponse> {
    const response = await fetch(
      `${this.baseURL}/api/admin/trigger`,
      {
        method: 'POST',
        headers: this.getAuthHeaders(),
        body: JSON.stringify({
          operation: 'refresh_seeclickfix',
          jurisdiction: jurisdiction
        })
      }
    );

    if (!response.ok) {
      const errorData = await response.json().catch(() => null);
      throw new Error(errorData?.error || `Failed to trigger refresh SeeClickFix: ${response.statusText}`);
    }

    return response.json();
  }

  // =========================================================================
  // Operation Status API (SESSION 341)
  // =========================================================================

  /**
   * Get status of a specific operation
   * GET /api/admin/operations/{operation_id}
   *
   * SESSION 341: Poll this endpoint to track operation progress.
   * Backend: src/civic_services/servers/civic_api_integrated.py:serve_operation_status
   */
  async getOperationStatus(operationId: string): Promise<OperationStatus> {
    const response = await fetch(
      `${this.baseURL}/api/admin/operations/${operationId}`,
      {
        method: 'GET',
        headers: this.getAuthHeaders()
      }
    );

    if (!response.ok) {
      const errorData = await response.json().catch(() => null);
      throw new Error(errorData?.error || `Failed to fetch operation status: ${response.statusText}`);
    }

    return response.json();
  }

  /**
   * List operations with optional filters
   * GET /api/admin/operations?jurisdiction=san-rafael&status=running&limit=20
   *
   * SESSION 341: Get operation history and currently running operations.
   * Backend: src/civic_services/servers/civic_api_integrated.py:serve_operations_list
   */
  async getOperations(options?: {
    jurisdiction?: string;
    status?: 'pending' | 'running' | 'completed' | 'failed';
    limit?: number;
  }): Promise<OperationsListResponse> {
    const params = new URLSearchParams();
    if (options?.jurisdiction) params.append('jurisdiction', options.jurisdiction);
    if (options?.status) params.append('status', options.status);
    if (options?.limit) params.append('limit', options.limit.toString());

    const queryString = params.toString();
    const url = `${this.baseURL}/api/admin/operations${queryString ? `?${queryString}` : ''}`;

    const response = await fetch(url, {
      method: 'GET',
      headers: this.getAuthHeaders()
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => null);
      throw new Error(errorData?.error || `Failed to fetch operations: ${response.statusText}`);
    }

    return response.json();
  }

  /**
   * Get currently running operation for a jurisdiction
   * Convenience method that filters by status=running
   *
   * SESSION 341: Use on page load to restore operation state after browser refresh.
   */
  async getCurrentOperation(jurisdiction: string = 'san-rafael'): Promise<OperationStatus | null> {
    try {
      const response = await this.getOperations({
        jurisdiction,
        status: 'running',
        limit: 1
      });

      if (response.operations.length > 0) {
        // Get full operation details
        return this.getOperationStatus(response.operations[0].operation_id);
      }

      // Also check pending operations
      const pendingResponse = await this.getOperations({
        jurisdiction,
        status: 'pending',
        limit: 1
      });

      if (pendingResponse.operations.length > 0) {
        return this.getOperationStatus(pendingResponse.operations[0].operation_id);
      }

      return null;
    } catch {
      return null;
    }
  }

  // =========================================================================
  // Data Browser API (SESSION 359)
  // =========================================================================

  /**
   * Get paginated data for schema exploration
   * GET /api/admin/data/{data_type}?page=1&per_page=10&jurisdiction=san-rafael
   *
   * SESSION 359: Full schema-faithful data browser for SaaS architect view.
   * SESSION 360: Added filter_column/filter_value for FK navigation.
   * Supports: meetings, agenda_items, decisions, issues
   */
  async getDataBrowser(
    dataType: 'meetings' | 'agenda_items' | 'decisions' | 'issues',
    options?: {
      page?: number;
      perPage?: number;
      jurisdiction?: string;
      filterColumn?: string;
      filterValue?: string;
    }
  ): Promise<DataBrowserResponse> {
    const params = new URLSearchParams();
    if (options?.page) params.append('page', options.page.toString());
    if (options?.perPage) params.append('per_page', options.perPage.toString());
    if (options?.jurisdiction) params.append('jurisdiction', options.jurisdiction);
    if (options?.filterColumn) params.append('filter_column', options.filterColumn);
    if (options?.filterValue) params.append('filter_value', options.filterValue);

    const queryString = params.toString();
    const url = `${this.baseURL}/api/admin/data/${dataType}${queryString ? `?${queryString}` : ''}`;

    const response = await fetch(url, {
      method: 'GET',
      headers: this.getAuthHeaders()
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => null);
      throw new Error(errorData?.error || `Failed to fetch ${dataType} data: ${response.statusText}`);
    }

    return response.json();
  }

  // =========================================================================
  // Vector Stats API (SESSION 362)
  // =========================================================================

  /**
   * Get vector collection statistics for ERD visualization
   * GET /api/admin/vector-stats?jurisdiction=san-rafael
   *
   * SESSION 362: Vector collection stats with coverage metrics.
   * SESSION 367: Returns dynamic corpus types from UnifiedSearch.get_available_corpora()
   * Returns document counts, source record counts, and coverage percentages.
   */
  async getVectorStats(jurisdiction: string = 'san-rafael'): Promise<VectorStatsResponse> {
    const params = new URLSearchParams();
    params.append('jurisdiction', jurisdiction);

    const url = `${this.baseURL}/api/admin/vector-stats?${params.toString()}`;

    const response = await fetch(url, {
      method: 'GET',
      headers: this.getAuthHeaders()
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => null);
      throw new Error(errorData?.error || `Failed to fetch vector stats: ${response.statusText}`);
    }

    return response.json();
  }
}

// Export singleton instance
export const api = new CivicAPI();
