# Starknet NFT Indexer

## How It Works

The indexer package (`@storm/indexer`) watches Starknet RPC for `Transfer` events from ERC-721 and ERC-1155 contracts, building an ownership index that maps addresses to their NFTs.

## RPC Requirements

The indexer uses `starknet_specVersion` and `starknet_getEvents` RPC calls. It requires:

- A Starknet RPC endpoint that supports `getEvents` (most public RPCs do)
- Event filtering by event key (ERC-721 `Transfer` event key: `0x...`)
- Full block history for complete ownership tracking

## Data Model

```ts
interface IndexedNFT {
  chain: 'starknet';
  network: 'mainnet' | 'sepolia';
  contractAddress: string;  // NFT contract
  tokenId: string;          // Token ID
  owner: string;            // Current owner address
  standard: 'ERC721' | 'ERC1155';
  lastTransferBlock: number;
  lastTransferTxHash: string;
  metadata?: {
    name?: string;
    image?: string;
  };
}
```

## Checkpointing

The indexer stores a checkpoint (last indexed block) to avoid re-processing historical events on restart. Checkpoint storage is left to the consumer (file, DB, etc.).

## Ownership State

The indexer builds inverted indices:
- `owner → NFT[]` (all NFTs owned by an address)
- `contract + tokenId → owner` (current owner of a specific NFT)

This enables the `getListingsForAsset` and `getListingsForAccount` queries used by venue adapters.

## Usage

```ts
import { Indexer } from '@storm/indexer';

const indexer = new Indexer({ rpcUrl: 'https://starknet-sepolia.infura.io/v3/YOUR_INFURA_KEY' });

// Start indexing from a specific block
await indexer.start({ fromBlock: 500000 });

// Query ownership
const nfts = await indexer.getNFTsForOwner('0x...address...');
const owner = await indexer.getOwnerOf('0x...contract...', '123');
```

## Limitations

- The indexer only tracks Transfer events — it does not ingest NFT metadata (names, images). That requires a separate metadata fetcher.
- ERC-1155 balance tracking is simplified — only current owner is tracked, not per-balance amounts.
- Very large NFT holders (thousands of NFTs) may return large result sets.
