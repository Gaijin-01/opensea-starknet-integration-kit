// packages/venue-core/src/index.ts
// Venue adapter interface — uniform abstraction for marketplace venues

import type { StarknetAddress, StarknetTokenId, StarknetNetwork } from '@storm/core';

export interface VenueListing {
  id: string;
  venue: string;
  chain: 'starknet';
  network: StarknetNetwork;
  side: 'listing' | 'offer';
  asset: {
    contractAddress: StarknetAddress;
    tokenId: StarknetTokenId;
    standard: 'ERC721' | 'ERC1155';
    quantity?: string;
  };
  maker: StarknetAddress;
  taker?: StarknetAddress;
  price: {
    amount: string;
    currency: StarknetAddress;
    decimals: number;
  };
  quantity: string;
  status: 'active' | 'filled' | 'cancelled' | 'expired' | 'unknown';
  validFrom?: number;
  validUntil?: number;
  rawVenueData?: unknown;
}

export interface CreateListingRequest {
  venue: string;
  asset: {
    contractAddress: StarknetAddress;
    tokenId: StarknetTokenId;
    standard: 'ERC721' | 'ERC1155';
    quantity?: string;
  };
  price: {
    amount: string;
    currency: StarknetAddress;
    decimals: number;
  };
  validFrom?: number;
  validUntil?: number;
}

export interface FulfilListingRequest {
  venue: string;
  listingId: string;
  amount?: string;
  quantity?: string;
}

export interface CancelListingRequest {
  venue: string;
  listingId: string;
  asset?: {
    contractAddress: string;
    tokenId: string;
  };
}

export interface ExecutionResult {
  transactionHash?: string;
  status: 'pending' | 'confirmed' | 'failed';
  error?: string;
}

/**
 * Account interface for venue operations.
 * Abstracts over wallet-connected accounts.
 */
export interface VenueAccount {
  address: StarknetAddress;
  signTypedData: (domain: unknown, types: unknown, value: unknown) => Promise<string[]>;
  execute: (calls: unknown[]) => Promise<{ transaction_hash: string }>;
}

export interface VenueAdapter {
  readonly name: string;
  readonly requiresApiKey: boolean;

  getListingsForAsset(
    contractAddress: StarknetAddress,
    tokenId: StarknetTokenId,
    options?: { network?: string }
  ): Promise<VenueListing[]>;

  getListingsForAccount(
    address: StarknetAddress,
    options?: { network?: string }
  ): Promise<VenueListing[]>;

  getListings(options?: {
    network?: string;
    limit?: number;
    continuation?: string;
  }): Promise<VenueListing[]>;

  createListing(
    request: CreateListingRequest,
    account: VenueAccount
  ): Promise<ExecutionResult>;

  fulfillListing(
    request: FulfilListingRequest,
    account: VenueAccount
  ): Promise<ExecutionResult>;

  cancelListing(
    request: CancelListingRequest,
    account: VenueAccount
  ): Promise<ExecutionResult>;
}


