// Interfaces
export type { StorageAdapter, Signer, UnsignedCivicEvent, SignedCivicEvent } from './interfaces.js';

// Registry
export { RegistryClient } from './registry.js';
export type { RegistryServer, JurisdictionLevel } from './registry.js';

// API
export { ApiClient } from './api.js';

// Types — re-export all data types
export type {
  CityPulseData,
  PulseMeeting,
  PulseAgendaItem,
  PulseOutcome,
  CommunityPulse,
  DecisionDetailData,
  TestimonyComment,
  DataProvenance,
  CorpusInfo,
  VoiceCounts,
  Initiative,
  CivicAction,
  CivicActionProgress,
  IssuePoint,
  IssueGeography,
  BudgetCategory,
  BudgetSummary,
  Comment,
  CommentCounts,
  CommentSynthesis,
  ContextBundle,
  ContextItem,
  ContextSections,
  HistorySection,
  RelatedDecision,
  RegulatorySection,
  ApplicableCode,
  TestimonySection,
  ContextMetadata,
  ToolResponse,
} from './types.js';

// Civic events — kinds and construction helpers
export {
  CivicEventKinds,
  createVoiceContent,
  createVoiceTags,
  createRevokeContent,
  createCommentTags,
  createCommitmentContent,
  createCommitmentTags,
  createCompletionContent,
  createCompletionTags,
  createWithdrawalContent,
  createWithdrawalTags,
  createInitiativeContent,
  createInitiativeTags,
  createCivicActionContent,
  createCivicActionTags,
  createAttestationContent,
  createAttestationTags,
} from './events.js';
