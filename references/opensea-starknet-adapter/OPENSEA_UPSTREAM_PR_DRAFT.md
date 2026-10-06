# Draft PR: Add Starknet Support via Chain Adapter

**Upstream**: `ProjectOpenSea/opensea-js`, commit `304a76bc120024419917a191b5c53a0365e17766`
**Goal**: Demonstrate minimum changes needed to support `Chain.Starknet` in the OpenSea SDK

## Summary

This PR adds a `StarknetOpenSeaSigner` and `StarknetOpenSeaProvider` implementation to the OpenSea SDK, demonstrating that the SDK's abstract interfaces (`OpenSeaSigner`, `OpenSeaProvider`, `OpenSeaWallet`) are chain-agnostic and can be implemented for Starknet without modifying existing code.

## Changes

### New File: `src/provider/starknet-adapter.ts`

A standalone TypeScript file implementing the OpenSea SDK's abstract interfaces for Starknet:

```ts
// src/provider/starknet-adapter.ts

export class StarknetOpenSeaSigner implements OpenSeaSigner {
  constructor(private account: StarknetAccount) {}

  async getAddress(): Promise<string> {
    return this.account.address;
  }

  async sendTransaction(tx: {
    to: string;
    data?: string;
    value?: bigint;
    from?: string;
    overrides?: Record<string, unknown>;
  }): Promise<TransactionResponse> {
    // Maps EVM-style sendTransaction to starknet account.execute(calls)
    const calls = [{ contractAddress: tx.to, entrypoint: 'invoke', calldata: [] }];
    const result = await this.account.execute(calls, tx.overrides as { maxFee?: bigint });
    return {
      hash: result.transaction_hash,
      async wait() {
        // Uses RpcProvider.waitForTransaction
      },
    };
  }

  async signTypedData(
    domain: { chainId: string | number; name: string; version: string; verifyingContract: string },
    types: Record<string, Array<{ name: string; type: string }>>,
    value: Record<string, unknown>
  ): Promise<string> {
    // EIP-712 → SNIP-12 mapping
    const snip12Message = { ... };
    const result = await this.account.signMessage(snip12Message);
    return result.signature.join(',');
  }
}

export class StarknetOpenSeaProvider implements OpenSeaProvider {
  constructor(private rpcProvider: RpcProvider) {}

  async waitForTransaction(hash: string): Promise<void> {
    await this.rpcProvider.waitForTransaction(hash);
  }
}

export function createStarknetOpenSeaWallet(
  account: StarknetAccount,
  rpcProvider?: RpcProvider
): OpenSeaWallet {
  const provider = rpcProvider ?? account.provider;
  return {
    signer: new StarknetOpenSeaSigner(account),
    provider: new StarknetOpenSeaProvider(provider),
  };
}
```

## What This PR Does NOT Include

This PR is intentionally **minimal** — it only adds the adapter implementation. The following require separate upstream (backend + SDK) changes:

### 1. `Chain.Starknet` enum value

```ts
// src/types.ts
export enum Chain {
  Mainnet = "ethereum",
  Polygon = "polygon",
  Starknet = "starknet",  // ADD THIS
  // ...
}
```

But TypeScript change alone is insufficient — the OpenSea REST API backend must also recognize `"starknet"` as a valid chain.

### 2. REST API chain registry

The OpenSea REST API must accept `chain=starknet` in queries and return Starknet NFT data. This requires backend changes.

### 3. Seaport → Starknet settlement

Seaport is EVM-only. Starknet settlement must delegate to Starknet-native venues (Medialane, Ark).

## Why This Approach Works

1. **No existing code changes** — the new file is purely additive
2. **Chain-agnostic interfaces** — `OpenSeaSigner`/`OpenSeaProvider` have identical semantics on Starknet
3. **Composable** — the SDK's composition logic (`OpenSeaSDK` constructor) already accepts any object matching these interfaces

## Testing

```ts
import { createStarknetOpenSeaWallet } from './src/provider/starknet-adapter';
import { OpenSeaSDK, Chain } from './src';

const wallet = await createStarknetOpenSeaWallet(account, provider);
const sdk = new OpenSeaSDK(wallet, { chain: 'starknet' as Chain });
```

## Future Work

1. OpenSea backend: add `starknet` to chain registry
2. OpenSea backend: add Starknet NFT indexer (Transfer events)
3. OpenSea backend: add SNIP-12 signature verification
4. OpenSea backend: add Medialane/Ark settlement venues
5. OpenSea frontend: add Starknet chain UI

## References

- [SNIP-12: Starknet Signed Typed Data](https://github.com/starknet-io/SNIPs/blob/main/SNIPS/snip-12.md)
- [starknet.js documentation](https://www.starknet-react.com/docs/starknetjs)
- [OpenSea SDK types](https://github.com/ProjectOpenSea/opensea-js)
