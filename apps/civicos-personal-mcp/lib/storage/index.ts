/**
 * Storage module for Personal MCP.
 *
 * Provides file-based and in-memory storage backends for
 * profile, preferences, jurisdictions, identity, context, and history.
 */

// Interface and types
export type {
  PersonalStorage,
  UserProfile,
  UserPreferences,
  HistoryEntry,
  HistoryQueryOptions,
  StorageInfo,
} from './personal-storage.js';

// Implementations
export { FileSystemPersonalStorage, FileSystemContextStorage, FileSystemWalletStorage, FileSystemPasskeyStorage, getDefaultBaseDir } from './filesystem-storage.js';
export { MemoryPersonalStorage } from './memory-storage.js';

// Factory
export { createPersonalStorage, type CreateStorageOptions } from './create-storage.js';

// Markdown parser utilities
export { parseMarkdown, renderMarkdown, parseOrderedList, renderOrderedList, type ParsedMarkdown } from './markdown-parser.js';
