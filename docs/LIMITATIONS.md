# Kit Limitations — OpenSea Integration

This document describes what the **@storm kit** cannot do without upstream OpenSea changes.

## OpenSea Does Not Support Starknet Natively

OpenSea (`opensea.com`, the OpenSea API, and the `@opensea/sdk` package) does not currently support Starknet as a chain. This is a fundamental limitation that no amount of kit code can work around.

## Specific Limitations

### OpenSea SDK (`@opensea/sdk`)

**Cannot do**: Use `Chain.Starknet` with the OpenSea SDK
- The SDK's `Chain` enum only includes EVM chains: Ethereum, Polygon, Arbitrum, etc.
- Even if TypeScript allowed adding `Starknet`, the REST API calls would fail
- No OpenSea backend endpoint recognizes `"starknet"` as a chain identifier

**Cannot do**: Use Seaport for Starknet orders
- Seaport is EVM-only: it uses keccak256 for order hashing and EVM calldata for execution
- Starknet has its own settlement layer (Medialane, Ark)
- Seaport cannot be used for Starknet NFT trading — a different protocol is needed

**Cannot do**: Use OpenSea API for Starknet NFT data
- `api.getTokens({ chain: 'starknet' })` returns no results
- OpenSea has not indexed Starknet NFT contracts
- OpenSea does not store Starknet metadata

**Cannot do**: Use OpenSea auth for Starknet accounts
- OpenSea's EIP-712 signed message auth does not verify SNIP-12 signatures
- A separate auth flow is needed for Starknet accounts

### OpenSea Backend

**Cannot do**: Index Starknet NFT transfers
- OpenSea's backend NFT indexer only processes EVM Transfer events
- Starknet Transfer events use a different event key format (starknet hash vs keccak256)
- Building a Starknet indexer requires separate infrastructure

**Cannot do**: Validate SNIP-12 signatures
- OpenSea's signature verification only handles EIP-191 (personal_sign) and EIP-712
- SNIP-12 is a different signature scheme (Starknet pedersen hash based)
- Backend must add SNIP-12 signature verification

**Cannot do**: Store Starknet orders
- OpenSea's order storage schema uses EVM address format (0x...)
- Starknet addresses (felt252) are different: 0x-prefixed but 64 hex chars (31 bytes)
- Order lifecycle (create, fill, cancel) requires Starknet-specific backend changes

**Cannot do**: Settle orders on Starknet
- OpenSea's settlement layer calls EVM contracts
- Starknet L2 settlement is completely different
- Medialane and Ark are the settlement venues for Starknet NFTs

### What This Kit CAN Do

The kit provides:
- `StarknetOpenSeaSigner` + `StarknetOpenSeaProvider` implementing OpenSea's abstract interfaces
- `createStarknetOpenSeaWallet()` factory for creating OpenSea-compatible wallets
- Venue packages (Medialane, Ark) for order creation, fulfillment, and cancellation
- Indexer package for tracking Starknet NFT ownership
- Reference server showing the API contract a backend must implement

### What Requires Upstream OpenSea

1. OpenSea backend must add `"starknet"` to its chain registry
2. OpenSea backend must run a Starknet indexer for NFT data
3. OpenSea backend must add SNIP-12 signature verification
4. OpenSea backend must add Medialane/Ark as settlement venues
5. OpenSea frontend must add Starknet chain UI

## Workarounds This Kit Provides

The kit can act as a **standalone marketplace** without OpenSea:
- Indexer tracks Starknet NFT ownership
- Venue packages handle order lifecycle (create, fulfill, cancel)
- Reference server demonstrates the API contract

This allows building a **Starknet NFT marketplace** that:
- Uses OpenSea-style API patterns
- Could integrate with OpenSea if/when OpenSea adds Starknet support
- Uses the same abstract interfaces OpenSea SDK uses (for future compatibility)

## Summary Table

| Feature | OpenSea Support | Kit Workaround |
|---------|----------------|----------------|
| Starknet wallet connect | ✗ | ✓ `@storm/wallet` |
| Starknet NFT ownership | ✗ | ✓ `@storm/indexer` |
| Starknet order lifecycle | ✗ | ✓ `@storm/venue-core`, `@storm/venue-medialane`, `@storm/venue-ark` |
| OpenSea API for Starknet | ✗ | None — requires OpenSea backend |
| Seaport on Starknet | ✗ | None — requires different settlement |
| OpenSea auth for Starknet | ✗ | None — requires OpenSea backend SNIP-12 |
| Starknet on OpenSea.com | ✗ | None — requires OpenSea frontend |
