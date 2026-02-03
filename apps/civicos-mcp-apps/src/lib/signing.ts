/**
 * Signing utilities for voice casting.
 *
 * Supports two modes:
 * - Verified: Uses WebAuthn/Passkey for persistent, verifiable identity
 * - Anonymous: Uses ephemeral ECDSA keys for privacy-preserving voices
 *
 * In both cases, voices are cryptographically signed - the relay can verify
 * authenticity without needing to trust the MCP Apps server.
 */

export interface SignedVoice {
  publicKey: string; // Hex-encoded
  signature: string; // Hex-encoded
  message: string; // The signed message
  mode: "verified" | "anonymous";
}

/**
 * Sign a voice with the user's identity.
 */
export async function signVoice(
  entity: string,
  stance: "support" | "oppose" | "watching",
  mode: "verified" | "anonymous"
): Promise<SignedVoice> {
  const timestamp = Date.now();
  const message = `voice:${entity}:${stance}:${timestamp}`;
  const messageBytes = new TextEncoder().encode(message);

  if (mode === "verified") {
    try {
      return await signWithWebAuthn(message, messageBytes);
    } catch (e) {
      console.warn("WebAuthn failed, falling back to ephemeral:", e);
      // Fall through to ephemeral
    }
  }

  return await signWithEphemeralKey(message, messageBytes);
}

/**
 * Sign using WebAuthn/Passkey.
 *
 * This creates a verifiable, persistent identity. The same passkey
 * will produce signatures that can be linked together.
 */
async function signWithWebAuthn(
  message: string,
  messageBytes: Uint8Array
): Promise<SignedVoice> {
  const credential = (await navigator.credentials.get({
    publicKey: {
      challenge: messageBytes,
      timeout: 60000,
      userVerification: "preferred",
      rpId: window.location.hostname,
    },
  })) as PublicKeyCredential;

  if (!credential) {
    throw new Error("No credential returned from WebAuthn");
  }

  const response = credential.response as AuthenticatorAssertionResponse;

  return {
    publicKey: bufferToHex(response.authenticatorData),
    signature: bufferToHex(response.signature),
    message,
    mode: "verified",
  };
}

/**
 * Sign using an ephemeral ECDSA key.
 *
 * This creates a one-time identity. Each voice gets a new keypair,
 * so voices cannot be linked to each other or to the user.
 */
async function signWithEphemeralKey(
  message: string,
  messageBytes: Uint8Array
): Promise<SignedVoice> {
  // Generate ephemeral keypair
  const keyPair = await crypto.subtle.generateKey(
    { name: "ECDSA", namedCurve: "P-256" },
    true,
    ["sign"]
  );

  // Sign the message
  const signature = await crypto.subtle.sign(
    { name: "ECDSA", hash: "SHA-256" },
    keyPair.privateKey,
    messageBytes
  );

  // Export public key
  const publicKeyRaw = await crypto.subtle.exportKey("raw", keyPair.publicKey);

  return {
    publicKey: bufferToHex(publicKeyRaw),
    signature: bufferToHex(signature),
    message,
    mode: "anonymous",
  };
}

/**
 * Convert ArrayBuffer to hex string.
 */
function bufferToHex(buffer: ArrayBuffer): string {
  return Array.from(new Uint8Array(buffer))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

/**
 * Verify a signature (for testing/debugging).
 */
export async function verifySignature(
  publicKeyHex: string,
  signatureHex: string,
  message: string
): Promise<boolean> {
  try {
    const publicKeyBytes = hexToBuffer(publicKeyHex);
    const signatureBytes = hexToBuffer(signatureHex);
    const messageBytes = new TextEncoder().encode(message);

    const publicKey = await crypto.subtle.importKey(
      "raw",
      publicKeyBytes,
      { name: "ECDSA", namedCurve: "P-256" },
      false,
      ["verify"]
    );

    return await crypto.subtle.verify(
      { name: "ECDSA", hash: "SHA-256" },
      publicKey,
      signatureBytes,
      messageBytes
    );
  } catch (e) {
    console.error("Signature verification failed:", e);
    return false;
  }
}

function hexToBuffer(hex: string): ArrayBuffer {
  const bytes = new Uint8Array(hex.length / 2);
  for (let i = 0; i < hex.length; i += 2) {
    bytes[i / 2] = parseInt(hex.substr(i, 2), 16);
  }
  return bytes.buffer;
}
