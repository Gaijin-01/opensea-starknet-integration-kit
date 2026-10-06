# Ark Project Venue Adapter

## Protocol Overview

Ark Project is a fully on-chain NFT marketplace on Starknet:
- All order state lives on Starknet L2
- No off-chain intent layer — direct contract calls via the Ark Executor
- No SNIP-12 signing required — all state changes go through `account.execute()`

## Contract Addresses (Verified)

### Sepolia

| Contract | Address |
|----------|---------|
| Executor | `0xb86ab357c15c12fb78f9b0a19fa974c730fcbab96f17881827dde871665f0b` |
| Orderbook | `0x795b605fa3144afd6f11a4499f71b9cf373bcba3f1b2835d51f65ab59392261` |

### Mainnet

| Contract | Address |
|----------|---------|
| Executor | `0x7b42945bc47001db92fe1b9739d753925263f2f1036c2ae1f87536c916ee6a` |
| Orderbook | `0x5add3084bb8664eb2a641cf26a28f60588c3ccd63af0632aafefcbb2332c345` |

## Arkchain RPC

Arkchain (Solis) is used for orderbook queries:

| Network | RPC URL |
|---------|---------|
| Sepolia | `https://sepolia.solis.arkproject.dev` |
| Mainnet | `https://production.solis.arkproject.dev` |

## SDK Usage

```ts
import { ArkAdapter } from '@storm/venue-ark';
import { createArkConfig, ROUTE_TYPE } from '@storm/venue-ark/sdk';

const adapter = new ArkAdapter({ network: 'sepolia' });

// Create a listing
const result = await adapter.createListing({
  venue: 'ark',
  asset: {
    contractAddress: '0x...nft...',
    tokenId: '123',
    standard: 'ERC721',
  },
  price: {
    amount: '1000000000000000000', // wei
    currency: 'ETH',
    decimals: 18,
  },
  validUntil: Math.floor(Date.now() / 1000) + 86400 * 30,
}, account);

// Fulfill a listing
const fulfillResult = await adapter.fulfillListing({
  venue: 'ark',
  listingId: '0x...orderHash...',
  amount: '1',
}, account);

// Cancel a listing
const cancelResult = await adapter.cancelListing({
  venue: 'ark',
  listingId: '0x...orderHash...',
}, account);
```

## Direct Calldata Builders

For more control, use the direct calldata builders:

```ts
import { buildApproveNftCall, buildCreateListingCall, buildFulfillListingCall, buildCancelOrderCall } from '@storm/venue-ark/sdk';

// Build calls manually
const approveCall = buildApproveNftCall(nftContract, tokenId, 'sepolia');
const listingCall = buildCreateListingCall({
  collection: nftContract,
  tokenId: tokenId,
  startAmount: price,
  currency: '0', // ETH
}, 'sepolia');

// Execute both in one transaction
const { transaction_hash } = await account.execute([approveCall, listingCall]);
```

## Route Types

Ark supports two route types:
- `ROUTE_TYPE.Erc721ToErc20 = 1` — ERC-721 → ERC-20 (most common)
- `ROUTE_TYPE.Erc1155ToErc20 = 2` — ERC-1155 → ERC-20 (partial fills)

## @ark-project/core SDK

The adapter also wraps `@ark-project/core` for a higher-level API:

```ts
import { createArkConfig, arkCreateListing } from '@storm/venue-ark/sdk';

const config = createArkConfig('sepolia');
const orderHash = await arkCreateListing(config, account, order, { tokenAddress, tokenId });
```
