# Architecture Overview

## Package Overview

```
@storm/core          — Shared types, constants, utilities (address, token, chain types)
@storm/venue-core    — VenueAdapter interface, VenueListing, ExecutionResult types
@storm/venue-medialane — Medialane REST API client + VenueAdapter implementation
@storm/venue-ark     — Ark Project SDK wrappers + direct calldata builders + VenueAdapter
@storm/opensea-adapter — OpenSeaSigner/OpenSeaProvider/OpenSeaWallet for Starknet
@storm/wallet        — Wallet connection (get-starknet, WalletAccountV6, SNIP-12 signing)
@storm/indexer       — Starknet NFT ownership indexer (RPC event scanning)
@storm/auth          — SNIP-12 authentication helpers
@storm/reference-server — Reference HTTP server (API contract demo)
```

## Dependency Graph

```
@storm/venue-core
    └── @storm/core (types)

@storm/venue-medialane
    ├── @storm/venue-core (VenueAdapter interface)
    └── @storm/core (types)

@storm/venue-ark
    ├── @storm/venue-core (VenueAdapter interface)
    ├── @storm/core (ARK_CONTRACTS, ARKCHAIN_RPC)
    └── @ark-project/core (SDK)

@storm/opensea-adapter
    └── starknet.js types

@storm/wallet
    ├── starknet.js (WalletAccountV6)
    └── @starknet-io/get-starknet

@storm/indexer
    ├── @storm/core (types)
    └── starknet.js (RpcProvider)

@storm/reference-server
    └── Medialane API proxy (no kit deps)
```

## Data Flow

### Read Operations (listings, assets)

```
Browser → GET /v1/starknet/assets/:contract/:tokenId
        → Reference Server (or direct Medialane API with server-side x-api-key)
        → Medialane REST API
        → VenueListing[] response
```

### Write Operations (list, fulfill, cancel)

```
Browser → VenueAdapter.createListing(request, account)
        → account.signTypedData(SNIP-12)     ← wallet signature
        → account.execute(calls)             ← on-chain Starknet transaction
        → transactionHash returned
```

### Venue Architecture

Each venue package implements `VenueAdapter`:

```
createListing(request, account) → ExecutionResult (tx hash)
fulfillListing(request, account) → ExecutionResult (tx hash)
cancelListing(request, account) → ExecutionResult (tx hash)
getListings(options) → VenueListing[]
getListingsForAsset(contract, tokenId) → VenueListing[]
getListingsForAccount(address) → VenueListing[]
```

Venues are protocol-agnostic — the same interface works for:
- **Medialane** (off-chain intent + on-chain settlement via SNIP-12)
- **Ark** (fully on-chain via Executor contract)
- **OpenSea** (would require OpenSea backend support for Starknet)

## Key Design Decisions

1. **API key safety**: Medialane API key is server-side only. The reference server proxies requests and adds the header. Browser bundles never see the key.

2. **SNIP-12 for Medialane**: Listing and cancel require SNIP-12 signatures. The fulfill flow does NOT require a signature per Medialane protocol.

3. **No Seaport on Starknet**: Seaport is EVM-only. Starknet venues (Medialane, Ark) handle settlement natively.

4. **Abstract VenueAdapter**: All venues implement the same interface, allowing uniform listing/fulfill/cancel APIs across different protocols.
