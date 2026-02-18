import { RegistryClient, ApiClient } from '@civicos/client';
import { ChromeStorageAdapter } from './adapters/chrome-storage.js';
import { ExtensionSigner } from './adapters/extension-signer.js';

const storage = new ChromeStorageAdapter();
export const signer = new ExtensionSigner();
export const registry = new RegistryClient(storage);
export const api = new ApiClient(registry, signer);
