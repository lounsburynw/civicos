// Interfaces
export type { StorageAdapter, Signer, UnsignedCivicEvent, SignedCivicEvent } from './interfaces.js';

// Adapters — portable implementations
export { MemoryStorageAdapter } from './adapters/memory-storage.js';

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
  WriteResult,
  CommentPeriod,
  LegislativeHearing,
  GovernorsDeskBill,
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
} from './events.js';

// NIP-13 proof-of-work mining
export { minePoW, countLeadingZeroBits } from './pow.js';
export type { MinableEvent } from './pow.js';

// Session — high-level orchestration
export { CivicSession } from './session.js';
export type { PulseBundle, CommentThread, InitiativeDetail } from './session.js';

// AI — manager, providers, storage, prompts
export { AIManager } from './ai/manager.js';
export type { AIProvider, AITier, AICompletionResult, AIChatResult, AIProviderConfig, AIPreferences, ChatUserContext } from './ai/types.js';
export type { AICredentialStorage } from './ai/storage.js';
export { MemoryAICredentialStorage } from './ai/storage.js';
export { ClaudeProvider } from './ai/providers/claude.js';
export { OpenAIProvider } from './ai/providers/openai.js';
export { GeminiProvider } from './ai/providers/gemini.js';
export { OllamaProvider } from './ai/providers/ollama.js';
export { composeDraftPrompt, composeEnrichPrompt, SYSTEM_PROMPT, QA_SYSTEM_PROMPT } from './ai/prompts.js';
export type { DraftUserContext } from './ai/prompts.js';

// AI chat tools — local tool routing for Ollama
export { CHAT_TOOL_DEFS, createMcpToolExecutor } from './ai/tools/chat-tools.js';
export type { ChatToolDef, ChatToolExecutor } from './ai/tools/chat-tools.js';
