/**
 * Centralized Artifact ID Generation
 *
 * Prevents mismatches between openArtifact() calls and context registration
 * by providing a single source of truth for artifact ID formats.
 *
 * Session 53.5: Created to fix artifact ID mismatch bugs (bills, programs)
 *
 * Usage:
 * - When opening artifacts: `id: ArtifactIds.bill(bill)`
 * - When registering context: `artifactId: ArtifactIds.bill(props.bill)`
 * - Guaranteed to match because both use the same helper
 */

import type { CivicEvent, StateBill, FederalProgram } from '@/types/civic';

/**
 * Generate consistent artifact IDs for all artifact types.
 * Each function accepts either the full object or just the ID string.
 */
export const ArtifactIds = {
  /**
   * Event artifacts use raw event ID (no prefix)
   * @example ArtifactIds.event(event) // => "event_123"
   */
  event: (event: CivicEvent | string): string => {
    return typeof event === 'string' ? event : event.id;
  },

  /**
   * Bill artifacts use "bill-" prefix + bill number
   * @example ArtifactIds.bill(bill) // => "bill-AB 1147"
   */
  bill: (bill: StateBill | string): string => {
    const billNumber = typeof bill === 'string' ? bill : bill.bill;
    return `bill-${billNumber}`;
  },

  /**
   * Program artifacts use "program-" prefix + program name
   * @example ArtifactIds.program(program) // => "program-CDBG"
   */
  program: (program: FederalProgram | string): string => {
    const programName = typeof program === 'string' ? program : program.program_name;
    return `program-${programName}`;
  },

  /**
   * Issue artifacts use raw issue ID (no prefix)
   * @example ArtifactIds.issue("issue_456") // => "issue_456"
   */
  issue: (issueId: string): string => {
    return issueId;
  },

  /**
   * Thread artifacts use raw thread ID (no prefix)
   * @example ArtifactIds.thread("thread_789") // => "thread_789"
   */
  thread: (threadId: string): string => {
    return threadId;
  },

  /**
   * Draft artifacts use "draft-" prefix + event ID
   * @example ArtifactIds.draft("event_123") // => "draft-event_123"
   */
  draft: (eventId: string): string => {
    return `draft-${eventId}`;
  }
} as const;

/**
 * Type guard to validate artifact ID format matches expected pattern.
 * Used for runtime validation in openArtifact() to catch mismatches early.
 *
 * @param type - Artifact type (event, bill, program, etc.)
 * @param id - Artifact ID to validate
 * @returns true if ID matches expected format for type
 */
export function isValidArtifactId(type: string, id: string): boolean {
  switch (type) {
    case 'bill':
      return id.startsWith('bill-');
    case 'program':
      return id.startsWith('program-');
    case 'draft':
    case 'comment-draft':
      return id.startsWith('draft-');
    case 'event':
    case 'issue':
    case 'issue-form':
    case 'thread':
    case 'profile-form':
    case 'values-explorer':
      // These types use raw IDs (no prefix)
      return true;
    default:
      console.warn(`[artifactIds] Unknown artifact type: ${type}`);
      return true; // Allow unknown types to pass (don't break)
  }
}

/**
 * Get human-readable artifact ID format for documentation/errors.
 *
 * @param type - Artifact type
 * @returns Description of expected ID format
 */
export function getArtifactIdFormat(type: string): string {
  switch (type) {
    case 'event':
      return 'Raw event ID (e.g., "event_123")';
    case 'bill':
      return 'bill-{bill_number} (e.g., "bill-AB 1147")';
    case 'program':
      return 'program-{program_name} (e.g., "program-CDBG")';
    case 'issue':
      return 'Raw issue ID (e.g., "issue_456")';
    case 'thread':
      return 'Raw thread ID (e.g., "thread_789")';
    case 'draft':
      return 'draft-{event_id} (e.g., "draft-event_123")';
    default:
      return 'Unknown format';
  }
}
