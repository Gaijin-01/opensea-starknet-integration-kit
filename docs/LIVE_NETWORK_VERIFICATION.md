# Live Network Verification — Sepolia

## Date

Verified September 2024.

## What Was Tested

### Contracts Deployed (Sepolia)

| Contract | Address | Status |
|----------|---------|--------|
| ETH (native) | `0x049d36570d4e46f48e99674bd3fcc84644ddd6b96f7c741b1562b82f9e004dc7` | ✓ Verified |
| STRK | `0x04718f5a0fc34cc1af16a1cdee98ffb20c31f5cd61d6ab07201858f4287c938d` | ✓ Verified |
| Ark Executor | `0xb86ab357c15c12fb78f9b0a19fa974c730fcbab96f17881827dde871665f0b` | ✓ Verified |
| Ark Orderbook | `0x795b605fa3144afd6f11a4499f71b9cf373bcba3f1b2835d51f65ab59392261` | ✓ Verified |

### RPC Endpoints Tested

| Provider | URL | Status |
|----------|-----|--------|
| Blast API Sepolia | `https://starknet-sepolia.infura.io/v3/YOUR_INFURA_KEY` | ✓ Working |
| Arkchain (Solis) Sepolia | `https://sepolia.solis.arkproject.dev` | ✓ Working |

### Operations Tested

| Operation | Venue | Status |
|-----------|-------|--------|
| NFT Transfer events (ERC-721) | Indexer | ✓ Working |
| getNFTsForOwner | Indexer | ✓ Working |
| getOwnerOf | Indexer | ✓ Working |
| Ark createListing (SDK) | Ark | ✓ Working |
| Ark fulfillListing (SDK) | Ark | ✓ Working |
| Ark cancelOrder (SDK) | Ark | ✓ Working |
| Medialane API (orders list) | Medialane | ✓ Working |
| SNIP-12 signing | Wallet | ✓ Working |

### NOT Tested (Requires Live API Key)

- Medialane create listing flow (requires API key + funds)
- Medialane fulfill listing flow
- Medialane cancel listing flow

## What Works Today

1. **Read operations** — Indexer, Medialane API (with key), Arkchain RPC
2. **Wallet connection** — get-starknet, WalletAccountV6, SNIP-12 signing
3. **Ark on-chain operations** — createListing, fulfillListing, cancelOrder (fully on-chain)
4. **Reference server** — static serving, Medialane proxying

## What Requires More Work

1. **Medialane write flows** — create/fulfill/cancel with SNIP-12 + server-side submit
2. **Indexer completeness** — ERC-1155 balance tracking, metadata ingestion
3. **Demo UI** — full NFT portfolio view, listing form with wallet signing

## Chain IDs

- Starknet Mainnet: `0x534e5f4d41494e` ("SN MAIN")
- Starknet Sepolia: `0x534e5f5345504f4c4941` ("SN SEPOLIA")
