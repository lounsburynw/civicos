import { RegistryClient, ApiClient } from '@civicos/client';
import { ChromeStorageAdapter } from './adapters/chrome-storage.js';

const storage = new ChromeStorageAdapter();
export const registry = new RegistryClient(storage);
export const api = new ApiClient(registry);
