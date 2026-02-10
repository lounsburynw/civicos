export interface UnsignedEvent {
  pubkey: string;
  created_at: number;
  kind: number;
  tags: string[][];
  content: string;
}

export interface SignedEvent extends UnsignedEvent {
  id: string;
  sig: string;
}

export interface MessageSignature {
  messageHash: string;
  signature: string;
}
