// packages/venue-ark/src/index.ts
import type {
  VenueAdapter,
  VenueListing,
  CreateListingRequest,
  FulfilListingRequest,
  CancelListingRequest,
  ExecutionResult,
  VenueAccount,
} from '@storm/venue-core';
import type { StarknetAddress, StarknetTokenId, StarknetNetwork } from '@storm/core';
import { ARK_CONTRACTS, ARKCHAIN_RPC } from '@storm/core';
import { Call } from 'starknet';
import {
  createArkConfig,
  buildApproveNftCall,
  buildApproveErc20Call,
  buildCreateListingCall,
  buildFulfillListingCall,
  buildCancelOrderCall,
} from './sdk';

export class ArkAdapter implements VenueAdapter {
  readonly name = 'ark';
  readonly requiresApiKey = false;

  private network: 'sepolia' | 'mainnet' = 'sepolia';

  constructor(options: { network?: StarknetNetwork } = {}) {
    this.network = (options.network ?? 'sepolia') as 'sepolia' | 'mainnet';
  }

  private mapArkOrderToVenueListing(order: {
    orderHash: bigint;
    offerer: string;
    collection: string;
    tokenId: string;
    startAmount: string;
    currency: string;
    startDate?: number;
    endDate?: number;
    routeType?: number;
  }): VenueListing {
    return {
      id: order.orderHash.toString(),
      venue: 'ark',
      chain: 'starknet',
      network: this.network,
      side: 'listing',
      asset: {
        contractAddress: order.collection as StarknetAddress,
        tokenId: order.tokenId as StarknetTokenId,
        standard: order.routeType === 2 ? 'ERC1155' : 'ERC721',
      },
      maker: order.offerer as StarknetAddress,
      price: {
        amount: order.startAmount,
        currency: order.currency as StarknetAddress,
        decimals: 18,
      },
      quantity: '1',
      status: 'active',
      validFrom: order.startDate,
      validUntil: order.endDate,
      rawVenueData: order,
    };
  }

  async getListingsForAsset(
    contractAddress: StarknetAddress,
    tokenId: StarknetTokenId,
    _options?: { network?: string }
  ): Promise<VenueListing[]> {
    // Query the Starknet RPC for Ark Orderbook events for this asset.
    // This requires an indexer or direct event scanning.
    // For now, return empty — production would use the indexer package.
    // BLOCKED_EXTERNAL: requires live Ark Orderbook contract + event indexer.
    // Stub pending Ark infrastructure availability.
    return [];
  }

  async getListingsForAccount(
    address: StarknetAddress,
    _options?: { network?: string }
  ): Promise<VenueListing[]> {
    // Query the Starknet RPC for Ark Orderbook events for this account.
    return [];
  }

  async getListings(_options?: {
    network?: string;
    limit?: number;
    continuation?: string;
  }): Promise<VenueListing[]> {
    // Query the Starknet RPC for all active Ark Orderbook events.
    return [];
  }

  async createListing(
    request: CreateListingRequest,
    account: VenueAccount
  ): Promise<ExecutionResult> {
    try {
      const config = createArkConfig(this.network);
      const now = Math.floor(Date.now() / 1000);

      // Build the approve call (approve executor to take the NFT)
      const approveCall = buildApproveNftCall(
        request.asset.contractAddress,
        request.asset.tokenId,
        this.network
      );

      // Build the createListing call
      const listingCall = buildCreateListingCall(
        {
          collection: request.asset.contractAddress,
          tokenId: request.asset.tokenId,
          startAmount: request.price.amount,
          currency: request.price.currency === '0x0' ? '0' : request.price.currency,
          startDate: request.validFrom ?? now,
          endDate: request.validUntil ?? now + 30 * 86400,
          routeType: request.asset.standard === 'ERC1155' ? 2 : 1,
        },
        this.network
      );

      const calls: Call[] = [approveCall, listingCall];
      const result = await account.execute(calls as unknown as unknown[]);

      return {
        transactionHash: (result as { transaction_hash: string }).transaction_hash,
        status: 'pending',
      };
    } catch (err) {
      return {
        status: 'failed',
        error: err instanceof Error ? err.message : String(err),
      };
    }
  }

  async fulfillListing(
    request: FulfilListingRequest,
    account: VenueAccount
  ): Promise<ExecutionResult> {
    try {
      // Build the fulfillListing call
      const fulfillCall = buildFulfillListingCall(
        request.listingId,
        request.amount ?? '1',
        this.network
      );

      // NOTE: ERC-20 approval must be performed separately before calling fulfillListing.
      // The fulfiller must call buildApproveErc20Call(approveInfo) and execute it
      // (approve, fulfill) in a single account.execute batch, OR pre-approve the
      // executor for the required currency amount.
      const result = await account.execute([fulfillCall] as unknown as unknown[]);

      return {
        transactionHash: (result as { transaction_hash: string }).transaction_hash,
        status: 'pending',
      };
    } catch (err) {
      return {
        status: 'failed',
        error: err instanceof Error ? err.message : String(err),
      };
    }
  }

  async cancelListing(
    request: CancelListingRequest,
    account: VenueAccount
  ): Promise<ExecutionResult> {
    try {
      const cancelCall = buildCancelOrderCall(request.listingId, this.network);
      const result = await account.execute([cancelCall] as unknown as unknown[]);

      return {
        transactionHash: (result as { transaction_hash: string }).transaction_hash,
        status: 'pending',
      };
    } catch (err) {
      return {
        status: 'failed',
        error: err instanceof Error ? err.message : String(err),
      };
    }
  }
}

export { ARK_CONTRACTS, ARKCHAIN_RPC } from '@storm/core';
export * from './sdk';
