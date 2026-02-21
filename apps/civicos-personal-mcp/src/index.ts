/**
 * Personal MCP - Client-side identity, signing, and context management.
 *
 * This package provides:
 * - SigningProvider interface and implementations
 * - IdentityManager for managing user identities
 * - PersonalMCPServer for MCP integration
 *
 * See docs/critical/EDGE_INTELLIGENCE_ARCHITECTURE.md for full design.
 */

// Re-export provider types and utilities
export * from '../lib/providers/index.js';

// Export identity manager
export { IdentityManager, type IdentityManagerConfig } from './identity.js';

// Export server (for programmatic use)
export { PersonalMCPServer } from './server.js';

// Export storage module
export * from '../lib/storage/index.js';
