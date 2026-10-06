# OpenSea Backend Integration Map — Starknet

Maps each OpenSea backend component to its Starknet equivalent and current implementation status.

| Component | Status | Implementation | Notes |
|-----------|--------|----------------|-------|
| **Chain registry** | Not implemented | Requires OpenSea backend change | OpenSea REST API must recognize `"starknet"` as a chain identifier. SDK `Chain` enum can add `Starknet = 'starknet'` but backend must follow. |
| **Address validation** | Works in adapter | `@storm/opensea-adapter` | Starknet addresses (felt252, 0x-prefixed hex) are valid as strings. No backend change needed for format validation. |
| **NFT contract detection** | Not implemented | Requires backend | OpenSea backend must index Starknet contract deployments. ERC721/ERC1155 on Starknet use different ABI than EVM. |
| **ERC721/ERC1155 ingestion** | Not implemented | Requires backend | Starknet ERC721 uses `IERC721` interface with Starknetfelt keys instead of EVM `address`. Separate ingestion pipeline required. |
| **Ownership tracking** | Not implemented | `@storm/indexer` | The kit's indexer must track `Transfer` events on Starknet. OpenSea backend has no Starknet ownership data. |
| **Metadata** | Not implemented | Requires backend | Starknet NFT metadata URI points to IPFS/HTTP. OpenSea backend metadata crawler must fetch from Starknet-compatible URIs. |
| **Collection ingestion** | Not implemented | Requires backend | OpenSea backend must process Starknet contract creation events and populate collection registry. |
| **Order ingestion** | Not implemented | `@storm/venue-core` | The kit's venue packages handle order creation. OpenSea backend has no Starknet order storage. |
| **Venue attribution** | Works in kit | `@storm/venue-medialane`, `@storm/venue-ark` | Medialane and Ark are the settlement venues. OpenSea backend must attribute orders to these venues. |
| **Wallet/account identity** | Works in adapter | `@storm/opensea-adapter` | Starknet account address is a felt252. No OpenSea backend change needed for address identity. |
| **Authentication** | Not implemented | `@storm/auth` | Starknet Signed Message (SNIP-12) authentication requires OpenSea backend to verify SNIP-12 signatures. |
| **Transaction execution** | Works in adapter | `@storm/opensea-adapter` | `account.execute()` handles Starknet transactions. OpenSea backend does not execute Starknet txs. |
| **Currency support** | Partial | STRK/ETH on Starknet | OpenSea backend must support STRK and ETH as payment tokens on Starknet. ERC20 approvals work the same. |
| **Fee/gas model** | Not implemented | Requires backend | Starknet L2 gas (execution steps, pedersen, range) differs from EVM gas. OpenSea fee calculation must adapt. |
| **UI chain filters** | Not implemented | Requires OpenSea frontend | OpenSea.com UI must add Starknet as a chain filter option. |
| **Portfolio view** | Not implemented | Requires backend | OpenSea backend must query Starknet indexer for user holdings. |
| **Order lifecycle** | Works in kit | `@storm/venue-core` | Create, fulfill, cancel lifecycle is handled by venue packages. OpenSea backend integration is separate. |
| **Checkout flow** | Not implemented | Requires backend + frontend | Payment, royalty, and fee transfer on Starknet differs from EVM. OpenSea checkout must handle Starknet txs. |
| **Webhooks/events** | Not implemented | Requires backend | OpenSea webhook consumers must handle Starknet event format. |
| **API schemas** | Not implemented | Requires OpenSea backend | OpenSea API response schemas (asset, collection, order) must add Starknet fields. |

## Summary

- **Adapter-only (works today)**: Address identity, transaction execution, venue attribution, order lifecycle in the kit
- **Requires OpenSea backend**: Chain registry, NFT indexing, metadata, order storage, authentication, fee model, API schemas
- **Requires kit + OpenSea backend**: Full marketplace integration end-to-end
