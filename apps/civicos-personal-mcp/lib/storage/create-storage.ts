/**
 * Factory for creating PersonalStorage instances.
 *
 * Defaults to FileSystemPersonalStorage (~/.civicos/) in Node.js.
 * Respects CIVICOS_DATA_DIR env var for custom data location.
 */

import type { PersonalStorage } from './personal-storage.js';
import { FileSystemPersonalStorage, getDefaultBaseDir } from './filesystem-storage.js';
import { MemoryPersonalStorage } from './memory-storage.js';

export interface CreateStorageOptions {
  /** Override the base directory (default: ~/.civicos or CIVICOS_DATA_DIR) */
  baseDir?: string;
  /** Force a specific storage type */
  forceType?: 'filesystem' | 'memory';
}

/**
 * Create a PersonalStorage instance.
 *
 * In Node.js, defaults to filesystem storage at ~/.civicos.
 * Use forceType: 'memory' for testing.
 */
export function createPersonalStorage(options?: CreateStorageOptions): PersonalStorage {
  const storageType = options?.forceType ?? 'filesystem';

  if (storageType === 'memory') {
    return new MemoryPersonalStorage();
  }

  const baseDir = options?.baseDir ?? getDefaultBaseDir();
  return new FileSystemPersonalStorage(baseDir);
}
