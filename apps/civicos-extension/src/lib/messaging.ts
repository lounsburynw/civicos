/**
 * Chrome extension message protocol types.
 *
 * All communication between popup/side-panel/options/content-scripts
 * and the service worker goes through chrome.runtime.sendMessage
 * with these typed messages.
 */

import type { IdentityTier, IdentityInfo, NostrEvent, SignedNostrEvent } from './providers/types.js';

// ============================================================================
// Message types
// ============================================================================

export type MessageType =
  | 'GET_IDENTITY'
  | 'GET_PUBLIC_KEY'
  | 'CREATE_IDENTITY'
  | 'IMPORT_IDENTITY'
  | 'UNLOCK'
  | 'LOCK'
  | 'DELETE_IDENTITY'
  | 'SIGN_EVENT'
  | 'NIP07_GET_PUBLIC_KEY'
  | 'NIP07_SIGN_EVENT'
  | 'NIP07_GET_RELAYS';

// ============================================================================
// Request types
// ============================================================================

export interface GetIdentityRequest {
  type: 'GET_IDENTITY';
}

export interface GetPublicKeyRequest {
  type: 'GET_PUBLIC_KEY';
}

export interface CreateIdentityRequest {
  type: 'CREATE_IDENTITY';
  tier: IdentityTier;
  passwordOrEmail: string;
}

export interface ImportIdentityRequest {
  type: 'IMPORT_IDENTITY';
  tier: IdentityTier;
  passwordOrEmail: string;
  mnemonic?: string;
}

export interface UnlockRequest {
  type: 'UNLOCK';
  password: string;
}

export interface LockRequest {
  type: 'LOCK';
}

export interface DeleteIdentityRequest {
  type: 'DELETE_IDENTITY';
}

export interface SignEventRequest {
  type: 'SIGN_EVENT';
  event: NostrEvent;
}

export interface Nip07GetPublicKeyRequest {
  type: 'NIP07_GET_PUBLIC_KEY';
}

export interface Nip07SignEventRequest {
  type: 'NIP07_SIGN_EVENT';
  event: NostrEvent;
}

export interface Nip07GetRelaysRequest {
  type: 'NIP07_GET_RELAYS';
}

export type ExtensionRequest =
  | GetIdentityRequest
  | GetPublicKeyRequest
  | CreateIdentityRequest
  | ImportIdentityRequest
  | UnlockRequest
  | LockRequest
  | DeleteIdentityRequest
  | SignEventRequest
  | Nip07GetPublicKeyRequest
  | Nip07SignEventRequest
  | Nip07GetRelaysRequest;

// ============================================================================
// Response types
// ============================================================================

export interface SuccessResponse<T = unknown> {
  success: true;
  data: T;
}

export interface ErrorResponse {
  success: false;
  error: string;
}

export type ExtensionResponse<T = unknown> = SuccessResponse<T> | ErrorResponse;

// Specific response data types
export type GetIdentityResponse = ExtensionResponse<IdentityInfo | null>;
export type GetPublicKeyResponse = ExtensionResponse<string | null>;
export type CreateIdentityResponse = ExtensionResponse<{ identity: IdentityInfo; mnemonic?: string }>;
export type ImportIdentityResponse = ExtensionResponse<IdentityInfo>;
export type UnlockResponse = ExtensionResponse<boolean>;
export type LockResponse = ExtensionResponse<void>;
export type DeleteIdentityResponse = ExtensionResponse<void>;
export type SignEventResponse = ExtensionResponse<SignedNostrEvent>;
export type Nip07GetPublicKeyResponse = ExtensionResponse<string>;
export type Nip07SignEventResponse = ExtensionResponse<SignedNostrEvent>;
export type Nip07GetRelaysResponse = ExtensionResponse<Record<string, { read: boolean; write: boolean }>>;

// ============================================================================
// Helper to send typed messages
// ============================================================================

export function sendMessage<T>(message: ExtensionRequest): Promise<ExtensionResponse<T>> {
  return chrome.runtime.sendMessage(message);
}
