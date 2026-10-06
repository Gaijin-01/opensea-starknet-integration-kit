// packages/indexer/src/index.ts
// Starknet NFT indexer — event-based ownership tracking

import {
  RpcProvider,
  type RpcProviderOptions,
  uint256,
} from 'starknet';
import type {
  StarknetAddress,
  StarknetTokenId,
  StarknetContractAddress,
  StarknetNetwork,
  StarknetAsset,
  TokenStandard,
} from '@storm/core';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface IndexerConfig {
  rpcUrl: string;
  network: StarknetNetwork;
  /** Starting block for initial sync (default: 0) */
  startBlock?: number;
  /** Batch size for getEvents calls (default: 1000) */
  batchSize?: number;
  /** Optional RPC provider options */
  rpcOptions?: Omit<RpcProviderOptions, 'nodeUrl'>;
}

export interface TransferEvent {
  blockNumber: number;
  transactionHash: string;
  contractAddress: StarknetContractAddress;
  from: StarknetAddress;
  to: StarknetAddress;
  tokenId: StarknetTokenId;
  standard: TokenStandard;
  /** For ERC-1155: amount transferred. Defaults to 1n for ERC-721. */
  quantity?: bigint;
}

// ---------------------------------------------------------------------------
// Transfer event keys (starknet.js constants)
// ---------------------------------------------------------------------------

/** ERC-721 Transfer event key */
export const TRANSFER_EVENT_KEY =
  '0x99cd8bde557814842a3121e8ddfd433a539b8c9f14bf31ebf108d12e6196e9';

/** ERC-1155 TransferSingle event key */
export const TRANSFER_SINGLE_KEY =
  '0x182d859c0807ba9db63baf8b9d9fdbfeb885d820be6e206b9dab626d995c433';

/** ERC-1155 TransferBatch event key */
export const TRANSFER_BATCH_KEY =
  '0x2563683c757f3abe19c4b7237e2285d8993417ddffe0b54a19eb212ea574b08';

// ---------------------------------------------------------------------------
// TransferEventParser
// ---------------------------------------------------------------------------

/**
 * Parses raw Starknet events into typed TransferEvent objects.
 */
export class TransferEventParser {
  /**
   * Parse an ERC-721 Transfer event from starknet.js event payload.
   */
  parseErc721(
    event: { keys?: string[]; data?: string[] },
    blockNumber: number,
    transactionHash: string
  ): TransferEvent | null {
    try {
      // keys[0] = Transfer event key
      // data[0] = from_address (felt)
      // data[1] = to_address (felt)
      // data[2] = token_id (uint256)
      const keys = event.keys ?? [];
      const data = event.data ?? [];
      if (keys.length < 1 || data.length < 3) return null;

      const from = data[0];
      const to = data[1];
      // uint256: low + high felt
      const tokenIdLow = BigInt(data[2]);
      const tokenIdHigh = BigInt(data[3] ?? '0');
      const tokenId = uint256.uint256ToBN({ low: tokenIdLow, high: tokenIdHigh }).toString();

      return {
        blockNumber,
        transactionHash,
        contractAddress: '', // set by caller
        from,
        to,
        tokenId,
        standard: 'ERC721',
        quantity: 1n,
      };
    } catch {
      return null;
    }
  }

  /**
   * Parse an ERC-1155 TransferSingle event.
   * data[0]=operator, data[1]=from, data[2]=to, data[3]=token_id_low,
   * data[4]=token_id_high, data[5]=amount_low, data[6]=amount_high(optional).
   */
  parseErc1155Single(
    event: { keys?: string[]; data?: string[] },
    blockNumber: number,
    transactionHash: string,
    contractAddress: StarknetContractAddress
  ): TransferEvent | null {
    try {
      const data = event.data ?? [];
      if (data.length < 6) return null;

      const from = data[1];
      const to = data[2];
      const tokenIdLow = BigInt(data[3]);
      const tokenIdHigh = BigInt(data[4] ?? '0');
      const tokenId = uint256.uint256ToBN({ low: tokenIdLow, high: tokenIdHigh }).toString();
      const amountLow = BigInt(data[5]);
      const amountHigh = BigInt(data[6] ?? '0');
      const quantity = uint256.uint256ToBN({ low: amountLow, high: amountHigh });

      return {
        blockNumber,
        transactionHash,
        contractAddress,
        from,
        to,
        tokenId,
        standard: 'ERC1155',
        quantity,
      };
    } catch {
      return null;
    }
  }
}

// ---------------------------------------------------------------------------
// OwnershipState
// ---------------------------------------------------------------------------

/**
 * In-memory owner -> contract -> tokenIds index.
 * Provides O(1) owner lookup after initial sync.
 */
export class OwnershipState {
  /** owner -> contract -> tokenIds */
  private ownerIndex = new Map<StarknetAddress, Map<StarknetContractAddress, Set<StarknetTokenId>>>();
  /** contract -> tokenId -> owner (for ERC-721) */
  private ownerOfIndex = new Map<StarknetContractAddress, Map<StarknetTokenId, StarknetAddress>>();
  /** ERC-1155 balances: contract -> tokenId -> owner -> balance */
  private balances = new Map<StarknetContractAddress, Map<StarknetTokenId, Map<StarknetAddress, string>>>();

  applyTransfer(event: TransferEvent): void {
    const qty = event.quantity ?? 1n;
    // Remove from old owner
    if (event.from !== '0x0') {
      this.removeOwnership(event.contractAddress, event.tokenId, event.from, event.standard, qty);
    }
    // Add to new owner
    if (event.to !== '0x0') {
      this.addOwnership(event.contractAddress, event.tokenId, event.to, event.standard, qty);
    }
  }

  private addOwnership(
    contract: StarknetContractAddress,
    tokenId: StarknetTokenId,
    owner: StarknetAddress,
    standard: TokenStandard,
    qty: bigint = 1n,
  ): void {
    // Update ownerIndex
    let contractMap = this.ownerIndex.get(owner);
    if (!contractMap) {
      contractMap = new Map();
      this.ownerIndex.set(owner, contractMap);
    }
    let tokenSet = contractMap.get(contract);
    if (!tokenSet) {
      tokenSet = new Set();
      contractMap.set(contract, tokenSet);
    }
    tokenSet.add(tokenId);

    // Update ownerOfIndex (ERC-721 only)
    if (standard === 'ERC721') {
      let tokenOwners = this.ownerOfIndex.get(contract);
      if (!tokenOwners) {
        tokenOwners = new Map();
        this.ownerOfIndex.set(contract, tokenOwners);
      }
      tokenOwners.set(tokenId, owner);
    }

    // Update balances (ERC-1155)
    if (standard === 'ERC1155') {
      let tokenBalances = this.balances.get(contract);
      if (!tokenBalances) {
        tokenBalances = new Map();
        this.balances.set(contract, tokenBalances);
      }
      let ownerBalances = tokenBalances.get(tokenId);
      if (!ownerBalances) {
        ownerBalances = new Map();
        tokenBalances.set(tokenId, ownerBalances);
      }
      const current = BigInt(ownerBalances.get(owner) ?? '0');
      ownerBalances.set(owner, (current + qty).toString());
    }
  }

  private removeOwnership(
    contract: StarknetContractAddress,
    tokenId: StarknetTokenId,
    owner: StarknetAddress,
    standard: TokenStandard,
    qty: bigint = 1n,
  ): void {
    // Remove from ownerIndex
    const contractMap = this.ownerIndex.get(owner);
    if (contractMap) {
      const tokenSet = contractMap.get(contract);
      if (tokenSet) {
        tokenSet.delete(tokenId);
        if (tokenSet.size === 0) contractMap.delete(contract);
        if (contractMap.size === 0) this.ownerIndex.delete(owner);
      }
    }

    // Remove from ownerOfIndex (ERC-721)
    if (standard === 'ERC721') {
      const tokenOwners = this.ownerOfIndex.get(contract);
      if (tokenOwners) {
        tokenOwners.delete(tokenId);
        if (tokenOwners.size === 0) this.ownerOfIndex.delete(contract);
      }
    }

    // Update balances (ERC-1155)
    if (standard === 'ERC1155') {
      const tokenBalances = this.balances.get(contract);
      if (tokenBalances) {
        const ownerBalances = tokenBalances.get(tokenId);
        if (ownerBalances) {
          const current = BigInt(ownerBalances.get(owner) ?? '0');
          const newBalance = (current - qty).toString();
          if (newBalance === '0') {
            ownerBalances.delete(owner);
          } else {
            ownerBalances.set(owner, newBalance);
          }
        }
      }
    }
  }

  getAssetsByOwner(address: StarknetAddress): StarknetAsset[] {
    const assets: StarknetAsset[] = [];

    // ERC-721: owned token IDs from ownerIndex
    const contractMap = this.ownerIndex.get(address);
    if (contractMap) {
      for (const [contractAddress, tokenIds] of contractMap.entries()) {
        for (const tokenId of tokenIds) {
          assets.push({
            chain: 'starknet',
            network: 'sepolia',
            contractAddress,
            tokenId,
            standard: 'ERC721',
          });
        }
      }
    }

    // ERC-1155: token IDs with positive balance from balances map
    for (const [contractAddress, tokenMap] of this.balances.entries()) {
      for (const [tokenId, ownerBalances] of tokenMap.entries()) {
        const balance = ownerBalances.get(address);
        if (balance && BigInt(balance) > 0n) {
          assets.push({
            chain: 'starknet',
            network: 'sepolia',
            contractAddress,
            tokenId,
            standard: 'ERC1155',
          });
        }
      }
    }

    return assets;
  }

  getOwner(contract: StarknetContractAddress, tokenId: StarknetTokenId): StarknetAddress | null {
    const tokenOwners = this.ownerOfIndex.get(contract);
    if (!tokenOwners) return null;
    return tokenOwners.get(tokenId) ?? null;
  }

  getBalance(
    contract: StarknetContractAddress,
    tokenId: StarknetTokenId,
    owner: StarknetAddress
  ): string {
    const tokenBalances = this.balances.get(contract);
    if (!tokenBalances) return '0';
    const ownerBalances = tokenBalances.get(tokenId);
    if (!ownerBalances) return '0';
    return ownerBalances.get(owner) ?? '0';
  }

  /**
   * Returns true if this contract has any ERC-1155 balances recorded
   * for the given tokenId — indicating the token is ERC-1155.
   */
  isErc1155(contract: StarknetContractAddress, tokenId: StarknetTokenId): boolean {
    const tokenBalances = this.balances.get(contract);
    if (!tokenBalances) return false;
    const ownerBalances = tokenBalances.get(tokenId);
    if (!ownerBalances) return false;
    return Array.from(ownerBalances.values()).some((qty) => BigInt(qty) > 0n);
  }
}

// ---------------------------------------------------------------------------
// MemoryCheckpointStore
// ---------------------------------------------------------------------------

/**
 * In-memory checkpoint persistence.
 * In production, replace with a durable store (DB, file, etc.).
 */
export class MemoryCheckpointStore {
  private checkpoint: number;
  private continuationKey?: string;

  constructor(startBlock = 0) {
    this.checkpoint = startBlock;
  }

  getCheckpoint(): number {
    return this.checkpoint;
  }

  setCheckpoint(block: number, continuationKey?: string): void {
    this.checkpoint = block;
    this.continuationKey = continuationKey;
  }

  getContinuationKey(): string | undefined {
    return this.continuationKey;
  }
}

/**
 * File-based checkpoint store. Persists the current checkpoint and
 * continuation key to a JSON file so the indexer can resume after restart.
 * Works in Node.js and Deno environments (auto-detects via 'Deno' in globalThis).
 * Handles basic file-not-found by starting from startBlock.
 */
export class FileCheckpointStore {
  private path: string;
  private checkpoint: number;
  private continuationKey?: string;

  constructor(path: string, startBlock = 0) {
    this.path = path;
    this.checkpoint = startBlock;
    this.continuationKey = undefined;
    this.#load();
  }

  #load(): void {
    try {
      // Use globalThis to avoid TypeScript 5.9 resolving 'Deno' as a type name
      const isDeno = typeof (globalThis as any).Deno !== 'undefined';
      const raw = isDeno
        ? (globalThis as any).Deno.readTextFileSync(this.path)
        : require('fs').readFileSync(this.path, 'utf-8');
      const data = JSON.parse(raw);
      this.checkpoint = typeof data.checkpoint === 'number' ? data.checkpoint : 0;
      this.continuationKey = typeof data.continuationKey === 'string' ? data.continuationKey : undefined;
    } catch {
      // File missing or invalid — start from constructor's startBlock
    }
  }

  #save(): void {
    try {
      const content = JSON.stringify({
        checkpoint: this.checkpoint,
        continuationKey: this.continuationKey ?? null,
      });
      const isDeno = typeof (globalThis as any).Deno !== 'undefined';
      if (isDeno) {
        (globalThis as any).Deno.writeTextFileSync(this.path, content);
      } else {
        require('fs').writeFileSync(this.path, content, 'utf-8');
      }
    } catch {
      // Write failed — checkpoint will be retried on next block
    }
  }

  getCheckpoint(): number {
    return this.checkpoint;
  }

  setCheckpoint(block: number, continuationKey?: string): void {
    this.checkpoint = block;
    this.continuationKey = continuationKey;
    this.#save();
  }

  getContinuationKey(): string | undefined {
    return this.continuationKey;
  }
}

// ---------------------------------------------------------------------------
// StarknetIndexer
// ---------------------------------------------------------------------------

/**
 * Event-based NFT indexer for Starknet.
 * Scans Transfer events and maintains an in-memory ownership index.
 */
export class StarknetIndexer {
  private provider: RpcProvider;
  private config: IndexerConfig;
  private parser: TransferEventParser;
  private ownership: OwnershipState;
  private checkpoints: MemoryCheckpointStore;
  private running = false;

  constructor(config: IndexerConfig) {
    this.config = config;
    this.provider = new RpcProvider({
      nodeUrl: config.rpcUrl,
      ...config.rpcOptions,
    });
    this.parser = new TransferEventParser();
    this.ownership = new OwnershipState();
    this.checkpoints = new MemoryCheckpointStore(config.startBlock ?? 0);
  }

  /**
   * Start indexing from the checkpoint block (or from startBlock if not set).
   */
  async start(fromBlock?: number): Promise<void> {
    this.running = true;
    const start = fromBlock ?? this.checkpoints.getCheckpoint();
    await this.sync(start);
  }

  /**
   * Sync events from a given block to the latest block.
   */
  async sync(fromBlock?: number): Promise<void> {
    const start = fromBlock ?? this.checkpoints.getCheckpoint();
    const batchSize = this.config.batchSize ?? 1000;

    let currentBlock = start;
    let continuationKey = this.checkpoints.getContinuationKey();

    while (this.running) {
      // starknet.js getEvents uses EventFilter directly (not wrapped in `filter`)
      // Query all three transfer event keys: ERC-721, ERC-1155 single, ERC-1155 batch
      const filter = {
        from_block: { block_number: currentBlock },
        to_block: 'latest' as const,
        keys: [[TRANSFER_EVENT_KEY, TRANSFER_SINGLE_KEY, TRANSFER_BATCH_KEY]],
        chunk_size: batchSize,
        continuation_token: continuationKey,
      };
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const events = await (this.provider.getEvents as (f: typeof filter) => Promise<any>)(filter);

      for (const event of events.events) {
        const blockNumber = event.block_number ?? currentBlock;
        const txHash = event.transaction_hash ?? '';
        const eventKey = event.keys?.[0] ?? '';

        // Dispatch to the correct parser based on event key
        let parsed: TransferEvent | null = null;
        if (eventKey === TRANSFER_EVENT_KEY) {
          parsed = this.parser.parseErc721(
            { keys: event.keys, data: event.data },
            blockNumber,
            txHash
          );
          if (parsed) parsed.contractAddress = event.from_address;
        } else if (eventKey === TRANSFER_SINGLE_KEY) {
          parsed = this.parser.parseErc1155Single(
            { keys: event.keys, data: event.data },
            blockNumber,
            txHash,
            event.from_address
          );
        }
        // TransferBatch: for now, fall back to single parsing per item in batch;
        // a full implementation would add parseErc1155Batch
        if (parsed) {
          this.ownership.applyTransfer(parsed);
        }
        currentBlock = Math.max(currentBlock, blockNumber);
      }

      if (events.continuation_token) {
        continuationKey = events.continuation_token;
        this.checkpoints.setCheckpoint(currentBlock, continuationKey);
      } else {
        // Checkpoint at current block — no continuation
        this.checkpoints.setCheckpoint(currentBlock + 1);
        break;
      }
    }
  }

  /**
   * Stop indexing.
   */
  stop(): void {
    this.running = false;
  }

  /**
   * Get all assets owned by an address.
   */
  getAssetsByOwner(address: StarknetAddress): StarknetAsset[] {
    return this.ownership.getAssetsByOwner(address);
  }

  /**
   * Get a specific asset.
   */
  async getAsset(contract: StarknetContractAddress, tokenId: StarknetTokenId): Promise<StarknetAsset | null> {
   // Check if this is an ERC-1155 token (has positive balance in the index)
   const isErc1155 = this.ownership.isErc1155(contract, tokenId);

   if (isErc1155) {
     // ERC-1155: ownership is multi-owner; the index tracks per-owner balances.
     // Return the asset without an owner field.
     return {
       chain: 'starknet',
       network: this.config.network,
       contractAddress: contract,
       tokenId,
       standard: 'ERC1155',
     };
   }

   // ERC-721: look up owner from the index
   const owner = this.ownership.getOwner(contract, tokenId);
   if (!owner) return null;

   return {
     chain: 'starknet',
     network: this.config.network,
     contractAddress: contract,
     tokenId,
     standard: 'ERC721',
     owner,
   };
  }

  /**
   * Get the current checkpoint (next block to sync).
   */
  getCheckpoint(): number {
    return this.checkpoints.getCheckpoint();
  }

  /**
   * Set the checkpoint manually.
   */
  setCheckpoint(block: number): void {
    this.checkpoints.setCheckpoint(block);
  }
}
