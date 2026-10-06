# OpenSea SDK Patches — Starknet Integration

**Upstream**: `ProjectOpenSea/opensea-js`, commit SHA: 304a76bc120024419917a191b5c53a0365e17766
**Goal**: Assess OpenSea SDK public interfaces for Starknet compatibility

## What the SDK currently supports

The SDK (v12.11.2, commit SHA above) provides:
- `OpenSeaSDK` class: ethers entry point (uses ethers Signer/Provider)
- `OpenSeaAPI`: REST API client with Chain enum
- `@opensea/seaport-js`: EVM order execution (Seaport 1.6)
- Abstract interfaces: `OpenSeaSigner`, `OpenSeaProvider`, `OpenSeaWallet`

## Abstract interfaces that COULD be adapted for Starknet

### OpenSeaProvider (chain-agnostic)
```ts
interface OpenSeaProvider {
  waitForTransaction(hash: string): Promise<void>;
}
```
Starknet equivalent: Use `starknet.RpcProvider.waitForTransaction()` — this interface is compatible.

### OpenSeaSigner (chain-specific but adaptable)
```ts
interface OpenSeaSigner {
  getAddress(): Promise<string>;
  sendTransaction(tx: { to: string; data?: string; value?: string | number; from?: string }): Promise<{ hash: string; wait(): Promise<void> }>;
  signTypedData(domain: unknown, types: unknown, value: unknown): Promise<string>;
}
```
Starknet adaptation needed:
- `getAddress()`: Starknet account address (felt252, 0x-prefixed hex) ✓
- `sendTransaction()`: Starknet account execute(calls) → tx hash ✓ (semantically compatible)
- `signTypedData()`: EIP-712 → SNIP-12 (different typed-data format) — requires mapping

### OpenSeaWallet (composition)
```ts
interface OpenSeaWallet {
  signer?: OpenSeaSigner;
  provider: OpenSeaProvider;
}
```
Composable for Starknet: `{ signer: StarknetOpenSeaSigner, provider: StarknetOpenSeaProvider }`

## What CANNOT work without OpenSea backend changes

1. **Chain.Starknet**: Chain enum is `string = 'ethereum' | 'polygon' | ...`
   Adding Starknet requires: `Chain.Starknet = 'starknet'`
   But OpenSea REST API backend must also recognize this chain identifier.
   This is NOT just a TypeScript change.

2. **Seaport settlement**: Seaport is EVM-only (keccak256, EVM calldata)
   Starknet has its own settlement layer (Medialane, Ark)
   Seaport CANNOT be reused for Starknet — a different settlement protocol is needed.

3. **NFT API chain queries**: `api.getTokens({ chain: 'starknet' })` requires
   OpenSea backend to index Starknet NFT contracts and return results.

4. **Order lifecycle**: Listings/orders with Starknet accounts as maker/taker
   require OpenSea backend to handle Starknet address format and signature validation.

## Minimum upstream patch for Starknet support

### Patch 1: Add Chain.Starknet to Chain enum
File: `src/types.ts`
```diff
  export enum Chain {
    Mainnet = "ethereum",
    Polygon = "polygon",
+   Starknet = "starknet",
    // ...
  }
```
This enables TypeScript compilation with a Starknet chain config.
But the OpenSea REST API backend must also recognize `"starknet"` as a valid chain.

### Patch 2: Add Starknet chain-data.json entry
File: `scripts/chain-data.json`
Add starknet entry with:
- `chainIdentifier`: "starknet"
- `nativeCurrency`: STRK (or ETH)
- `rpcUrl`: public Starknet RPC
- etc.

### Patch 3: Add Starknet signer/provider adapters
File: `src/provider/starknet-signer-adapter.ts` (NEW)
Implements OpenSeaSigner + OpenSeaProvider for Starknet.
Does NOT require modifying existing code — additive only.

### What still requires OpenSea backend changes

- REST API chain registry must include Starknet
- NFT ingestion pipeline must process Starknet Transfer events
- Order storage must support Starknet address format (felt252)
- Settlement layer must support Starknet venues (Medialane, Ark)
- Gas/fee model must account for Starknet execution costs

## Current patch series

This directory contains a reference TypeScript implementation of the OpenSeaSigner and OpenSeaProvider interface for Starknet:

## Not included (requires OpenSea private backend)

- No patch for OpenSea backend chain registry
- No patch for NFT Starknet indexer
- No patch for Seaport → Starknet settlement bridge
- No patch for order lifecycle with Starknet accounts

## How to apply this reference adapter

This is a **reference implementation** — a manually copied TypeScript adapter file, not a `git apply` patch series.

```bash
# 1. Locate the OpenSea JS SDK source
OPENSEA_PATH=$(npm root -g)/opensea-js  # or your local clone path

# 2. Copy the adapter into the SDK provider directory
cp /path/to/starknet/patches/opensea-sdk/starknet-signer-adapter.ts \
   $OPENSEA_PATH/src/provider/starknet-signer-adapter.ts

# 3. Register the export in the SDK entrypoint (add to index.ts or the relevant file):
#    export { createStarknetOpenSeaWallet } from './provider/starknet-signer-adapter';

# 4. Verify TypeScript compilation
cd $OPENSEA_PATH && npm run build
```

**This is not a `git apply *.patch` operation.** The adapter must be manually placed
into the SDK source tree and registered in the exports. OpenSea must also make the
public chain registry changes listed above before Starknet support is functional.

## Recording upstream base

OPENSEA_UPSTREAM_BASE_SHA=304a76bc120024419917a191b5c53a0365e17766
OPENSEA_UPSTREAM_REPO=https://github.com/ProjectOpenSea/opensea-js
OPENSEA_UPSTREAM_BRANCH=main
