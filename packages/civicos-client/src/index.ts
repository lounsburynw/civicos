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

// AI — manager, providers, storage, prompts
export { AIManager } from './ai/manager.js';
export type { AIProvider, AITier, AICompletionResult, AIProviderConfig, AIPreferences } from './ai/types.js';
export type { AICredentialStorage } from './ai/storage.js';
export { MemoryAICredentialStorage } from './ai/storage.js';
export { ClaudeProvider } from './ai/providers/claude.js';
export { OpenAIProvider } from './ai/providers/openai.js';
export { GeminiProvider } from './ai/providers/gemini.js';
export { composeDraftPrompt, composeEnrichPrompt, SYSTEM_PROMPT, QA_SYSTEM_PROMPT } from './ai/prompts.js';
