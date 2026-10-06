// starknet/clients/typescript/src/medialane.ts
/**
 * Medialane REST API client for TypeScript / browser.
 *
 * API Base: https://api.medialane.io
 * Authentication: x-api-key header
 *
 * Flow (CONFIRMED from current docs):
 *   create:   POST /v1/intents/listing   → requiresSignature=true → sign SNIP-12 → submit
 *   fulfill:   POST /v1/intents/fulfill  → requiresSignature=false → execute calls directly
 *   cancel:    POST /v1/intents/cancel    → requiresSignature=true → sign SNIP-12 → submit
 *
 * IMPORTANT: The API key must NOT be exposed to browser code.
 * For browser apps: proxy through a backend that adds the x-api-key header.
 */

import type { TypedData, Signature } from "starknet";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface MedialaneOrder {
  orderHash: string;
  offerer: string;
  nftContract: string;
  tokenId: string;
  price: string;
  currency: string;
  startDate?: number;
  endDate?: number;
  status: "ACTIVE" | "FULFILLED" | "CANCELLED" | "EXPIRED";
  remainingAmount?: string; // ERC-1155 partial fills
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  [key: string]: any;
}

export interface OwnedToken {
  contractAddress: string;
  tokenId: string;
  name?: string;
  image?: string;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  [key: string]: any;
}

export interface IntentResult {
  intentId: string;
  requiresSignature: boolean;
  typedData?: object;
  submitUrl?: string;
  executableCalls?: Call[];
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  [key: string]: any;
}

export interface Call {
  contractAddress: string;
  entrypoint: string;
  calldata: string[];
}

export interface MedialaneListingRequest {
  offerer: string;
  nftContract: string;
  tokenId: string | number;
  price: string | number;
  currency: string;
  endTime?: number;
}

export interface MedialaneCancelRequest {
  seller: string;
  orderHash: string;
  tokenAddress: string;
  tokenId: string | number;
}

// ---------------------------------------------------------------------------
// Client
// ---------------------------------------------------------------------------

export interface MedialaneClientConfig {
  apiKey?: string;
  baseUrl?: string;
  network?: "sepolia" | "mainnet";
  rpcUrl?: string;
}

export class MedialaneClient {
  private readonly apiKey: string;
  private readonly baseUrl: string;
  private readonly network: "sepolia" | "mainnet";
  private readonly rpcUrl?: string;

  constructor(config: MedialaneClientConfig = {}) {
    this.apiKey = config.apiKey ?? "";
    this.baseUrl = config.baseUrl ?? "https://api.medialane.io";
    this.network = config.network ?? "sepolia";
    this.rpcUrl = config.rpcUrl;
  }

  // -------------------------------------------------------------------------
  // Private helpers
  // -------------------------------------------------------------------------

  private async request<T>(
    method: "GET" | "POST",
    path: string,
    body?: object
  ): Promise<T> {
    const url = `${this.baseUrl}${path}`;
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    };
    if (this.apiKey) {
      headers["x-api-key"] = this.apiKey;
    }

    const init: RequestInit =
      method === "GET"
        ? { method: "GET", headers }
        : { method: "POST", headers, body: JSON.stringify(body) };

    const response = await fetch(url, init);

    if (!response.ok) {
      const errorText = await response.text().catch(() => "Unknown error");
      throw new MedialaneApiError(
        `Medialane API error ${response.status}: ${errorText}`,
        response.status
      );
    }

    return response.json() as Promise<T>;
  }

  // -------------------------------------------------------------------------
  // Portfolio / ownership
  // -------------------------------------------------------------------------

  /**
   * Get all NFTs owned by an address.
   * GET /v1/tokens/{owner_address}
   */
  async medialaneGetTokensForOwner(ownerAddress: string): Promise<OwnedToken[]> {
    const data = await this.request<{ tokens: OwnedToken[] }>(
      "GET",
      `/v1/tokens/${ownerAddress}?chain=STARKNET&network=${this.network}`
    );
    return data.tokens ?? [];
  }

  // -------------------------------------------------------------------------
  // Order queries
  // -------------------------------------------------------------------------

  /**
   * Get active orders for a specific NFT.
   * GET /v1/orders?status=ACTIVE&token_address=&token_id=
   */
  async medialaneGetOrders(
    nftContract?: string,
    tokenId?: string | number,
    status?: "ACTIVE" | "FULFILLED" | "CANCELLED" | "EXPIRED"
  ): Promise<MedialaneOrder[]> {
    const params = new URLSearchParams({
      chain: "STARKNET",
      network: this.network,
    });
    if (nftContract) params.set("token_address", nftContract);
    if (tokenId !== undefined) params.set("token_id", tokenId.toString());
    if (status) params.set("status", status);
    const data = await this.request<{ orders: MedialaneOrder[] }>(
      "GET",
      `/v1/orders?${params.toString()}`
    );
    return data.orders ?? [];
  }

  /**
   * Create a listing intent.
   * POST /v1/intents/listing
   *
   * Returns requiresSignature=true. Caller must:
   *   1. Sign the typedData with their wallet
   *   2. Call submitSignature() with the signature
   */
  async medialaneCreateListingIntent(params: MedialaneListingRequest): Promise<IntentResult> {
    return this.request<IntentResult>("POST", "/v1/intents/listing", {
      offerer: params.offerer,
      token_address: params.nftContract,
      token_id: params.tokenId.toString(),
      price: params.price.toString(),
      currency: params.currency,
      end_time: params.endTime,
      chain: "STARKNET",
      network: this.network,
    });
  }

  // -------------------------------------------------------------------------
  // Fulfill intent (NO signature required)
  // -------------------------------------------------------------------------

  /**
   * Fulfill a listing.
   * POST /v1/intents/fulfill
   *
   * CONFIRMED: requiresSignature=false. Caller receives executable calls directly.
   * No SNIP-12 signing needed from the fulfiller.
   */
  async medialaneCreateFulfillIntent(params: {
    fulfiller: string;
    orderHash: string;
    amount?: string | number;
  }): Promise<IntentResult> {
    return this.request<IntentResult>("POST", "/v1/intents/fulfill", {
      fulfiller: params.fulfiller,
      order_hash: params.orderHash,
      amount: (params.amount ?? 1).toString(),
      chain: "STARKNET",
      network: this.network,
    });
  }

  // -------------------------------------------------------------------------
  // Cancel intent (requires SNIP-12 signature)
  // -------------------------------------------------------------------------

  /**
   * Cancel a listing.
   * POST /v1/intents/cancel
   *
   * Returns requiresSignature=true. Caller must:
   *   1. Sign the typedData with their wallet (offerer)
   *   2. Call submitSignature() with the signature
   */
  async medialaneCreateCancelIntent(params: MedialaneCancelRequest): Promise<IntentResult> {
    return this.request<IntentResult>("POST", "/v1/intents/cancel", {
      seller: params.seller,
      order_hash: params.orderHash,
      token_address: params.tokenAddress,
      token_id: params.tokenId.toString(),
      chain: "STARKNET",
      network: this.network,
    });
  }

  // -------------------------------------------------------------------------
  // Signature submission
  // -------------------------------------------------------------------------

  /**
   * Submit a SNIP-12 signature for a pending intent.
   * POST {submitUrl}
   */
  async medialaneSubmitSignedCalls(
    submitUrl: string,
    signature: Signature
  ): Promise<{ transactionHash?: string; calls?: Call[] }> {
    // submitUrl is returned in the intent result
    const url = submitUrl.startsWith("http")
      ? submitUrl
      : `${this.baseUrl}${submitUrl}`;
    const response = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "x-api-key": this.apiKey,
      },
      body: JSON.stringify({ signature }),
    });

    if (!response.ok) {
      const errorText = await response.text().catch(() => "Unknown error");
      throw new MedialaneApiError(
        `Signature submission failed ${response.status}: ${errorText}`,
        response.status
      );
    }

    return response.json() as Promise<{ transactionHash?: string; calls?: Call[] }>;
  }
}

// ---------------------------------------------------------------------------
// Error
// ---------------------------------------------------------------------------

export class MedialaneApiError extends Error {
  constructor(message: string, public readonly statusCode: number) {
    super(message);
    this.name = "MedialaneApiError";
  }
}

// ---------------------------------------------------------------------------
// Convenience factory (env var)
// ---------------------------------------------------------------------------

/**
 * Create a Medialane client using the MEDIALANE_API_KEY environment variable.
 *
 * For browser use, provide the key from a backend proxy.
 * NEVER expose MEDIALANE_API_KEY directly in browser bundles.
 *
 * NOTE: This client uses an API key — it must be server-side only.
 * Browser bundles should use a backend proxy to avoid exposing the key.
 */
export function createMedialaneClient(config: MedialaneClientConfig = {}): MedialaneClient {
  const apiKey = config.apiKey ?? (typeof process !== "undefined" ? process.env?.MEDIALANE_API_KEY : undefined);
  if (!apiKey) {
    throw new Error("MEDIALANE_API_KEY is not set");
  }
  return new MedialaneClient({ ...config, apiKey });
}
