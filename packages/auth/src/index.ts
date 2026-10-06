// packages/auth/src/index.ts
// SNIP-12 auth reference implementation for Starknet account authentication
// This is a PROPOSED extension — OpenSea does not currently support it

import type { StarknetAddress } from '@storm/core';

// Medialane SNIP-12 domain (ERC-721 uses version 1, ERC-1155 uses version 3)
export interface SNIP12Domain {
  name: string;
  version: string;
  chainId: number;
  verifyingContract: StarknetAddress;
}

export interface AuthChallenge {
  domain: SNIP12Domain;
  types: Record<string, { name: string; type: string }[]>;
  message: {
    nonce: string;
    issuer: StarknetAddress;
    expiry: number;
  };
}

/**
 * Build SNIP-12 domain for Medialane.
 */
export function buildMedialaneDomain(
  network: 'mainnet' | 'sepolia',
  verifyingContract: StarknetAddress
): SNIP12Domain {
  return {
    name: 'Medialane',
    version: '1', // ERC-721 marketplace
    chainId: network === 'mainnet' ? 1 : 2,
    verifyingContract,
  };
}

/**
 * Build a challenge for wallet authentication.
 */
export function buildAuthChallenge(params: {
  address: StarknetAddress;
  nonce: string;
  expirySeconds?: number;
}): AuthChallenge {
  const expiry = Math.floor(Date.now() / 1000) + (params.expirySeconds ?? 3600);
  return {
    domain: {
      name: 'StarknetKit',
      version: '1',
      chainId: 1, // use StarknetChainId from config
      verifyingContract: params.address,
    },
    types: {
      Challenge: [
        { name: 'nonce', type: 'felt' },
        { name: 'issuer', type: 'felt' },
        { name: 'expiry', type: 'felt' },
      ],
    },
    message: {
      nonce: params.nonce,
      issuer: params.address,
      expiry,
    },
  };
}

/**
 * Verify a Starknet SNIP-12 signature against an expected address.
 * Uses starknet.js Account.verifyMessage (calls the on-chain Account interface).
 * IMPORTANT: validates against the account's stored domain — full SNIP-12 compliance
 * requires the account to have registered the same domain used at signing time.
 */
export async function verifyStarknetSignature(params: {
  address: StarknetAddress;
  message: unknown;
  signature: string[];
}): Promise<boolean> {
  try {
    const { RpcProvider, Account } = await import('starknet');
    const rpcUrl =
      typeof process !== 'undefined' && process.env?.STARKNET_RPC
        ? process.env.STARKNET_RPC
        : 'https://starknet-sepolia.infura.io/v3/YOUR_INFURA_KEY';
    const provider = new RpcProvider({ nodeUrl: rpcUrl });
    // Cast to any: Account requires a signer for write ops but verifyMessage is
    // a read-only on-chain call that does not need a private key.
    const account = new (Account as any)(provider, params.address);
    return account.verifyMessage(params.message, params.signature as any);
  } catch {
    return false;
  }
}

/**
 * Nonce management for replay protection.
 * Uses crypto.getRandomValues() for cryptographically secure random nonces.
 * In production, nonces must be stored server-side (DB, Redis, etc.) — this
 * in-memory store is for reference/demo only.
 */
export class NonceStore {
  private nonces = new Map<StarknetAddress, string>();

  get(address: StarknetAddress): string {
    let nonce = this.nonces.get(address);
    if (!nonce) {
      nonce = this.generateNonce();
      this.nonces.set(address, nonce);
    }
    return nonce;
  }

  use(address: StarknetAddress): string {
    const nonce = this.get(address);
    this.nonces.set(address, this.generateNonce());
    return nonce;
  }

  private generateNonce(): string {
    // 16 bytes of cryptographic randomness + timestamp prefix to reduce collision risk
    const buf = new Uint8Array(16);
    (globalThis as any).crypto?.getRandomValues(buf);
    const randomPart = Array.from(buf as unknown as number[])
      .map((b) => b.toString(36).padStart(2, '0'))
      .join('');
    return randomPart + Date.now().toString(36);
  }
}
