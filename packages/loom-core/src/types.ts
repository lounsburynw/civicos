export interface KeyPair {
  privateKey: Uint8Array;
  /** 64-char hex x-only public key */
  publicKey: string;
}

export interface KeyStore {
  load(): Promise<string | null>;
  save(hex: string): Promise<void>;
}
