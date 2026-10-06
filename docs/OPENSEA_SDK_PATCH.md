# OpenSea SDK Patch Assessment

**Upstream**: `ProjectOpenSea/opensea-js`, commit `304a76bc120024419917a191b5c53a0365e17766`
**Goal**: Assess what the OpenSea SDK's public interfaces can and cannot do for Starknet

## Current State

The OpenSea SDK (`v12.11.2`) provides:
- `OpenSeaSDK` — main entry point using ethers Signer/Provider
- `OpenSeaAPI` — REST API client with a `Chain` enum
- `@opensea/seaport-js` — EVM order execution (Seaport 1.6)
- **Abstract interfaces**: `OpenSeaSigner`, `OpenSeaProvider`, `OpenSeaWallet`

## What the Abstract Interfaces Can Express for Starknet

The SDK's abstract interfaces are **chain-agnostic** by design. Each method maps cleanly to Starknet:

### `OpenSeaProvider`

```ts
interface OpenSeaProvider {
  waitForTransaction(hash: string): Promise<void>
}
```

Starknet: `starknet.RpcProvider.waitForTransaction()` — **identical semantics, no adaptation needed**.

### `OpenSeaSigner`

```ts
interface OpenSeaSigner {
  getAddress(): Promise<string>
  sendTransaction(tx: {
    to: string
    data?: string
    value?: bigint
    from?: string
    overrides?: Record<string, unknown>
  }): Promise<TransactionResponse>
  signTypedData(
    domain: { chainId, name, version, verifyingContract },
    types: Record<string, Array<{ name: string; type: string }>>,
    value: Record<string, unknown>,
  ): Promise<string>
}
```

Starknet mapping:
- `getAddress()` → `account.address` (felt252, 0x-prefixed hex) ✓
- `sendTransaction()` → `account.execute(calls)` → `{ transaction_hash, wait() }` ✓
- `signTypedData()` → SNIP-12 signing (different typed-data format) — requires EIP-712→SNIP-12 mapping

### `OpenSeaWallet`

```ts
type OpenSeaWallet =
  | { signer: OpenSeaSigner; provider: OpenSeaProvider }
  | { provider: OpenSeaProvider }
```

Composable for Starknet: `{ signer: StarknetOpenSeaSigner, provider: StarknetOpenSeaProvider }` ✓

## What Cannot Work Without Upstream Changes

1. **Chain enum** — `Chain.Starknet = 'starknet'` requires OpenSea REST API backend to recognize `"starknet"` as a valid chain identifier. TypeScript change alone is insufficient.

2. **Seaport settlement** — Seaport is EVM-only (keccak256, EIP-712 signing, EVM calldata). Starknet settlement requires Medialane or Ark. Seaport cannot be reused.

3. **NFT API queries** — `api.getTokens({ chain: 'starknet' })` requires OpenSea backend to index Starknet NFT Transfer events.

4. **Order lifecycle** — Listings with Starknet accounts as maker/taker require backend support for:
   - Starknet address format (felt252)
   - SNIP-12 signature validation
   - Starknet transaction receipts

## Minimum Upstream Change Needed

A **single TypeScript file** added to the SDK, with **no modifications to existing code**:

```
src/provider/starknet-adapter.ts  (NEW — additive only)
```

This implements `StarknetOpenSeaSigner` and `StarknetOpenSeaProvider` against the existing abstract interfaces. The SDK's base layer already handles the composition — no changes needed there.

Beyond the TypeScript adapter, the following **upstream OpenSea infrastructure** must change:
- REST API chain registry must accept `"starknet"`
- NFT ingestion pipeline must process Starknet Transfer events
- Order storage must support felt252 address format
- Settlement layer must delegate to Starknet venues (Medialane/Ark)
- Gas/fee model must account for Starknet L2 execution costs

## Patch Files in This Directory

- `starknet-signer-adapter.ts` — Standalone TypeScript file implementing `StarknetOpenSeaSigner` + `StarknetOpenSeaProvider` + `createStarknetWallet()`. Drop this into `@opensea/sdk/src/provider/` to enable Starknet as a signer/provider.
- `README.md` — This document.
