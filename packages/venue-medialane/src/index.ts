// packages/venue-medialane/src/index.ts
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
import { MedialaneClient } from './client';

export class MedialaneAdapter implements VenueAdapter {
  readonly name = 'medialane';
  readonly requiresApiKey = false; // Core works without hosted API

  private client: MedialaneClient;

  constructor(options: { apiKey?: string; rpcUrl?: string; network?: StarknetNetwork } = {}) {
    this.client = new MedialaneClient({
      apiKey: options.apiKey ?? '',
      rpcUrl: options.rpcUrl,
      network: (options.network ?? 'sepolia') as 'sepolia' | 'mainnet',
    });
  }

  private mapOrderToVenueListing(
    order: import('./client').MedialaneOrder,
    network: StarknetNetwork
  ): VenueListing {
    return {
      id: order.orderHash,
      venue: 'medialane',
      chain: 'starknet',
      network,
      side: 'listing',
      asset: {
        contractAddress: order.nftContract as StarknetAddress,
        tokenId: order.tokenId as StarknetTokenId,
        standard: 'ERC721',
        quantity: order.remainingAmount ?? '1',
      },
      maker: order.offerer as StarknetAddress,
      price: {
        amount: order.price,
        currency: order.currency as StarknetAddress,
        decimals: 18,
      },
      quantity: order.remainingAmount ?? '1',
      status:
        order.status === 'ACTIVE'
          ? 'active'
          : order.status === 'FULFILLED'
            ? 'filled'
            : order.status === 'CANCELLED'
              ? 'cancelled'
              : order.status === 'EXPIRED'
                ? 'expired'
                : 'unknown',
      validFrom: order.startDate,
      validUntil: order.endDate,
      rawVenueData: order,
    };
  }

  async getListingsForAsset(
    contractAddress: StarknetAddress,
    tokenId: StarknetTokenId,
    options?: { network?: string }
  ): Promise<VenueListing[]> {
    const orders = await this.client.medialaneGetOrders(contractAddress, tokenId, 'ACTIVE');
    const network = (options?.network ?? 'sepolia') as StarknetNetwork;
    return orders.map((o) => this.mapOrderToVenueListing(o, network));
  }

  async getListingsForAccount(
    address: StarknetAddress,
    options?: { network?: string }
  ): Promise<VenueListing[]> {
    const orders = await this.client.medialaneGetOrders(undefined, undefined, 'ACTIVE');
    const network = (options?.network ?? 'sepolia') as StarknetNetwork;
    return orders
      .filter((o) => o.offerer.toLowerCase() === address.toLowerCase())
      .map((o) => this.mapOrderToVenueListing(o, network));
  }

  async getListings(options?: {
    network?: string;
    limit?: number;
    continuation?: string;
  }): Promise<VenueListing[]> {
    const network = (options?.network ?? 'sepolia') as StarknetNetwork;
    const orders = await this.client.medialaneGetOrders(undefined, undefined, 'ACTIVE');
    return orders.map((o) => this.mapOrderToVenueListing(o, network));
  }

  async createListing(
    request: CreateListingRequest,
    account: VenueAccount
  ): Promise<ExecutionResult> {
    try {
      const intentResult = await this.client.medialaneCreateListingIntent({
        offerer: account.address,
        nftContract: request.asset.contractAddress,
        tokenId: request.asset.tokenId,
        price: request.price.amount,
        currency: request.price.currency,
        endTime: request.validUntil,
      });

      if (!intentResult.requiresSignature) {
        if (intentResult.executableCalls && intentResult.executableCalls.length > 0) {
          const result = await account.execute(intentResult.executableCalls as unknown as unknown[]);
          return { transactionHash: (result as { transaction_hash: string }).transaction_hash, status: 'pending' };
        }
        return { status: 'failed', error: 'No executable calls returned' };
      }

      if (!intentResult.typedData) {
        return { status: 'failed', error: 'No typedData returned for signing' };
      }

      const signature = await account.signTypedData(intentResult.typedData, {}, {});

      if (!intentResult.submitUrl) {
        return { status: 'failed', error: 'No submitUrl returned' };
      }

      const submitResult = await this.client.medialaneSubmitSignedCalls(
        intentResult.submitUrl,
        signature as unknown as import('starknet').Signature
      );

      if (submitResult.calls && submitResult.calls.length > 0) {
        const result = await account.execute(submitResult.calls as unknown as unknown[]);
        return { transactionHash: (result as { transaction_hash: string }).transaction_hash, status: 'pending' };
      }

      return {
        transactionHash: submitResult.transactionHash,
        status: submitResult.transactionHash ? 'pending' : 'failed',
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
      const intentResult = await this.client.medialaneCreateFulfillIntent({
        fulfiller: account.address,
        orderHash: request.listingId,
        amount: request.amount ?? '1',
      });

      if (intentResult.executableCalls && intentResult.executableCalls.length > 0) {
        const result = await account.execute(intentResult.executableCalls as unknown as unknown[]);
        return { transactionHash: (result as { transaction_hash: string }).transaction_hash, status: 'pending' };
      }

      return { status: 'failed', error: 'No executable calls returned from fulfill intent' };
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
      const intentResult = await this.client.medialaneCreateCancelIntent({
        seller: account.address,
        orderHash: request.listingId,
        tokenAddress: request.asset?.contractAddress ?? '0x0',
        tokenId: request.asset?.tokenId ?? '0',
      });

      if (!intentResult.requiresSignature) {
        if (intentResult.executableCalls && intentResult.executableCalls.length > 0) {
          const result = await account.execute(intentResult.executableCalls as unknown as unknown[]);
          return { transactionHash: (result as { transaction_hash: string }).transaction_hash, status: 'pending' };
        }
        return { status: 'failed', error: 'No executable calls returned' };
      }

      if (!intentResult.typedData) {
        return { status: 'failed', error: 'No typedData returned for signing' };
      }

      const signature = await account.signTypedData(intentResult.typedData, {}, {});

      if (!intentResult.submitUrl) {
        return { status: 'failed', error: 'No submitUrl returned' };
      }

      const submitResult = await this.client.medialaneSubmitSignedCalls(
        intentResult.submitUrl,
        signature as unknown as import('starknet').Signature
      );

      if (submitResult.calls && submitResult.calls.length > 0) {
        const result = await account.execute(submitResult.calls as unknown as unknown[]);
        return { transactionHash: (result as { transaction_hash: string }).transaction_hash, status: 'pending' };
      }

      return {
        transactionHash: submitResult.transactionHash,
        status: submitResult.transactionHash ? 'pending' : 'failed',
      };
    } catch (err) {
      return {
        status: 'failed',
        error: err instanceof Error ? err.message : String(err),
      };
    }
  }
}

export { MedialaneClient, MedialaneApiError } from './client';
export type {
  MedialaneOrder,
  OwnedToken,
  IntentResult,
  Call,
  MedialaneListingRequest,
  MedialaneCancelRequest,
} from './client';
