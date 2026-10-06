# OpenSea SDK Public Architecture Map

**Source:** `https://github.com/ProjectOpenSea/opensea-js`, commit `304a76bc` (v12.11.2)
**OPENSEA_UPSTREAM_BASE_SHA=304a76bc**

---

## 1. Chain Abstraction

### `Chain` Enum Definition

**File:** `src/types.ts`, lines 184–215

```ts
export enum Chain {
  Mainnet = "ethereum",
  Polygon = "polygon",
  Base = "base",
  Blast = "blast",
  Arbitrum = "arbitrum",
  Avalanche = "avalanche",
  Optimism = "optimism",
  Solana = "solana",
  Zora = "zora",
  Sei = "sei",
  B3 = "b3",
  BeraChain = "bera_chain",
  ApeChain = "ape_chain",
  Flow = "flow",
  Ronin = "ronin",
  Abstract = "abstract",
  Shape = "shape",
  Unichain = "unichain",
  Gunzilla = "gunzilla",
  HyperEVM = "hyperevm",
  Somnia = "somnia",
  Monad = "monad",
  MegaETH = "megaeth",
  Soneium = "soneium",
  Hyperliquid = "hyperliquid",
  AnimeChain = "animechain",
  Ink = "ink",
  Robinhood = "robinhood",
  StableChain = "stablechain",
  Arc = "arc",
}
```

**Key property:** `Chain` is a string-valued TypeScript enum. Each member's value is the chain's slug identifier (e.g., `"ethereum"`, `"polygon"`). This means `Chain` values are plain strings at runtime — they can be compared with `===` against string literals.

### Compile-Time Check: `_AssertAPIChainsCovered`

**File:** `src/types.ts`, lines 217–222

```ts
// Compile-time check: every ChainIdentifier from the API spec must be assignable to Chain.
// If the API adds a new chain, this will error — add it to the Chain enum above.
// The SDK may have chains not yet in the API spec (e.g. testnets, upcoming chains).
type _AssertAPIChainsCovered = ChainIdentifier extends `${Chain}` ? true : never

const _assertAPIChainsCovered: _AssertAPIChainsCovered = true
```

This is a TypeScript conditional type that produces a **compile-time error** if `@opensea/api-types` defines a `ChainIdentifier` that is not a member of the `Chain` enum. Adding Starknet (as a string value) to the enum would pass this check, but only if `ChainIdentifier` from the API types package includes it. If Starknet is not yet in `@opensea/api-types`, this check would not catch its absence — it only guards against the API spec having a chain the SDK does not.

**Implication for Starknet:** Adding `Starknet = "starknet"` to the enum is mechanically trivial. The check would pass at compile time if `"starknet"` is already a valid `ChainIdentifier` in the installed version of `@opensea/api-types`.

### Chain ID Mapping

**File:** `src/utils/chainIds.generated.ts` (auto-generated)

```ts
export const CHAIN_ID_MAP: Record<string, string> = {
  ethereum: "1",
  optimism: "10",
  unichain: "130",
  polygon: "137",
  monad: "143",
  // ...etc
}
```

Chain data sourced from `scripts/chain-data.json` (fetched by `pnpm sync-chains`). Starknet would need its chain ID added here. The function `getChainId()` (src/utils/chain.ts, lines 81–92) reads from this map:

```ts
export const getChainId = (chain: Chain): string => {
  const id = CHAIN_ID_MAP[chain]
  if (id === undefined) {
    if (Object.values(Chain).includes(chain)) {
      throw new Error(
        `Chain ${chain} has no EVM chain ID for OpenSea Seaport operations`,
      )
    }
    throw new Error(`Unknown chainId for ${chain}`)
  }
  return id
}
```

The error message explicitly says "EVM chain ID for OpenSea Seaport operations" — `getChainId` is only used for EVM chain IDs, confirming that non-EVM chains (Starknet) would need a different mechanism.

### Every Place `Chain` Is Used

| Location | Usage |
|---|---|
| `src/sdk.ts:43` | Defaults `apiConfig.chain ??= Chain.Mainnet` |
| `src/viem.ts:76` | Same default in viem entry point |
| `src/api/api.ts:232` | `this.chain = config.chain ?? Chain.Mainnet` |
| `src/utils/chain.ts:99–158` | `getOfferPaymentToken()` — switch on every Chain member |
| `src/utils/chain.ts:190–243` | `getListingPaymentToken()` — switch on every Chain member |
| `src/utils/chain.ts:250–276` | `getDefaultConduit()` — switch on every Chain member |
| `src/utils/chain.ts:283–287` | `getSeaportAddress()` — uses `usesAlternateProtocol()` |
| `src/utils/chain.ts:294–298` | `getSignedZone()` — uses `usesAlternateProtocol()` |
| `src/utils/chain.ts:305–316` | `getFeeRecipient()` — switch on Chain members with special fees |
| `src/utils/chain.ts:324–335` | `getNativeWrapTokenAddress()` — switch on every Chain member |
| `src/utils/chain.ts:28–29` | `usesAlternateProtocol()` — hardcoded set of non-standard chains |

**Hardcoded chain-specific sets** (not extensible without code changes):
- `usesAlternateProtocol()`: `Gunzilla | Somnia | MegaETH`
- `NATIVE_STABLECOIN_OFFER_TOKENS`: `Arc | StableChain` (USDC/USDT-based offers)
- `getOfferPaymentToken()` throws for `Solana | Hyperliquid` (no Seaport offers supported)

### Chain Data Generation

`scripts/chain-data.json` was not found in the repo at this commit — the `scripts/` directory only contains `check-consumer-declarations.mjs`. The `chainIds.generated.ts` is the artifact; the source `chain-data.json` may live in a private repo or be fetched from the OpenSea API. The generation command is `pnpm sync-chains`.

---

## 2. Provider/Signer Abstraction

### `OpenSeaSigner` Interface

**File:** `src/provider/types.ts`, lines 12–32

```ts
export interface OpenSeaSigner {
  getAddress(): Promise<string>
  sendTransaction(tx: {
    to: string
    data?: string
    value?: bigint
    from?: string
    overrides?: Record<string, unknown>
  }): Promise<TransactionResponse>
  signTypedData(
    domain: {
      chainId: string | number
      name: string
      version: string
      verifyingContract: string
    },
    types: Record<string, Array<{ name: string; type: string }>>,
    value: Record<string, unknown>,
  ): Promise<string>
}
```

**Assumptions baked in:**
- **EIP-712 signing:** `signTypedData` is the EIP-712 signing method. The domain separator includes `chainId`, `name`, `version`, and `verifyingContract`. This is the Seaport EIP-712 domain.
- **EVM address format:** `getAddress()` returns a hex string. For Starknet, addresses are `0x`-prefixed 66-character hex strings (Felt), which would need conversion to/from Starknet's representation.
- **`sendTransaction` calldata is EVM hex:** `data` field is a hex string of EVM bytecode. Starknet calldata is a different format (array of Felts).
- **`TransactionResponse.wait()` returns `Promise<void>`:** No return value. Starknet invocations return a transaction hash; confirmation is handled differently.

### `OpenSeaProvider` Interface

**File:** `src/provider/types.ts`, lines 34–37

```ts
export interface OpenSeaProvider {
  waitForTransaction(hash: string): Promise<void>
}
```

Minimal — only one method. Starknet's provider would need to map a Starknet transaction hash to this interface.

### `OpenSeaWallet` Type

**File:** `src/provider/types.ts`, lines 39–42

```ts
export type OpenSeaWallet =
  | { signer: OpenSeaSigner; provider: OpenSeaProvider }
  | { provider: OpenSeaProvider }
```

A wallet is either a signer+provider pair (for write operations) or provider-only (read-only). A Starknet adapter would return `{ signer: StarknetSignerAdapter, provider: StarknetProviderAdapter }`.

### `ContractCaller` Interface

**File:** `src/provider/types.ts`, lines 44–66

```ts
export interface ContractCaller {
  readContract(params: {
    address: string
    abi: readonly unknown[]
    functionName: string
    args: unknown[]
  }): Promise<unknown>
  writeContract(params: {
    address: string
    abi: readonly unknown[]
    functionName: string
    args: unknown[]
    value?: bigint
    overrides?: Record<string, unknown>
  }): Promise<TransactionResponse>
  encodeFunctionData(params: {
    abi: readonly unknown[]
    functionName: string
    args: unknown[]
  }): string
}
```

**EVM assumptions:**
- `address` is an EVM 20-byte address (hex string)
- `abi` is an EVM Solidity ABI array
- `encodeFunctionData` produces an EVM function selector + calldata hex string
- `TransactionResponse` from `writeContract` uses EVM transaction hash

### `createEthersWallet` / `createEthersProvider`

**File:** `src/provider/ethers-adapter.ts`

Key behaviors:
- `createEthersWallet` (lines 21–34): Extracts provider, wraps ethers Signer into `OpenSeaSigner`
- `createEthersSigner` (lines 39–73): Wraps `signer.sendTransaction()` and `signer.signTypedData()`. Throws if `signTypedData` is not available.
- `createEthersProvider` (lines 78–97): Wraps `provider.waitForTransaction()`
- `createEthersContractCaller` (lines 102–149): Uses ethers `Contract` for read/write/encoding. **Uses ethers `Interface.encodeFunctionData`** — EVM-only.
- `getEthersAccounts` (lines 154–176): Uses ethers account resolution methods.

### What a `StarknetSignerAdapter` Would Need to Implement

A minimal adapter to satisfy `OpenSeaSigner`:

```ts
const starknetSigner: OpenSeaSigner = {
  async getAddress(): Promise<string> {
    // Convert Starknet felt address to hex string
    return starknetAddressToHexString(await account.getAddress())
  },

  async sendTransaction(tx): Promise<TransactionResponse> {
    // Map EVM-style tx to Starknet invoke
    const hash = await account.execute({
      contractAddress: tx.to,
      entrypoint: extractSelector(tx.data), // EVM selector → Starknet selector
      calldata: parseCalldata(tx.data),
    })
    return {
      hash,
      async wait() {
        await provider.waitForTransaction(hash)
      },
    }
  },

  async signTypedData(domain, types, value): Promise<string> {
    // EIP-712 → Starknet signMessage (different message format)
    // Domain separator includes chainId (Starknet chain ID ≠ EVM chain ID)
    // For Seaport: hash the EIP-712 struct using StarknetPoseidon
    return account.signMessage(...)
  },
}
```

**Critical challenge:** Seaport's `signTypedData` uses EIP-712 digest. Starknet uses a different signing scheme (Starknet Signed Messages format, which hashes using Starknet's specific Poseidon-based hash). This is a **deep incompatibility** — Seaport will reject Starknet signatures unless a custom Starknet Seaport deployment uses Starknet-native signing.

---

## 3. Seaport Dependency

### Every File That Imports `@opensea/seaport-js`

| File | Usage |
|---|---|
| `src/sdk.ts:1` | `import { Seaport } from "@opensea/seaport-js"` — instantiation |
| `src/sdk/base.ts:3` | `import type { Seaport } from "@opensea/seaport-js"` — typed context |
| `src/sdk/context.ts:1` | `import type { Seaport }` — context interface |
| `src/viem.ts:22` | `import { Seaport } from "@opensea/seaport-js"` — instantiation |
| `src/provider/seaport-bridge.ts` | Bridges viem → seaport-js (seaport-js needs ethers internally) |
| `src/orders/types.ts:5` | `import type { OrderWithCounter } from "@opensea/seaport-js/lib/types"` |
| `src/orders/orderUseCase.ts:1–5` | `import type { CreateOrderAction, OrderComponents, OrderUseCase }` |
| `src/sdk/fulfillment.ts:1` | `import { SeaportABI } from "@opensea/seaport-js/lib/abi/Seaport"` |
| `src/sdk/fulfillment.ts:2` | `import type { OrderComponents }` |
| `src/utils/chain.ts:1` | `import { CROSS_CHAIN_SEAPORT_V1_6_ADDRESS } from "@opensea/seaport-js/lib/constants"` |
| `src/orders/utils.ts:1` | `import { CROSS_CHAIN_SEAPORT_V1_6_ADDRESS }` |

### Where Seaport Is Instantiated

**File:** `src/sdk.ts`, lines 53–61

```ts
const seaport = new Seaport(signerOrProvider, {
  conduitKeyToConduit: {
    [defaultConduit.key]: defaultConduit.address,
  },
  overrides: {
    defaultConduitKey: defaultConduit.key,
    contractAddress: seaportAddress,
  },
})
```

**File:** `src/viem.ts`, lines 92–100 — same pattern, but first passes through `createSeaportBridge` to adapt viem clients to ethers-compatible signer/provider for seaport-js.

### Seaport Assumptions Baked In

1. **EVM calldata:** Seaport produces EVM contract calldata (function selectors, ABI-encoded arguments). Starknet has a completely different calldata format (array of Felts).

2. **keccak256 order hashing:** Seaport order hashes are `keccak256` of EIP-712-encoded order components. Starknet's hash function (Poseidon) is different. A Starknet Seaport would produce different order hashes.

3. **Conduit-based token transfer:** Seaport uses the OpenSea Conduit system for ERC20 approvals. This is an EVM-specific mechanism.

4. **SeaportABI:** The fulfillment path (`src/sdk/fulfillment.ts:242`) encodes function calls using `SeaportABI`:
   ```ts
   const encodedData = this.context.contractCaller.encodeFunctionData({
     abi: SeaportABI,
     functionName,
     args: params,
   })
   ```
   This is EVM ABI encoding — no Starknet equivalent is used.

5. **`OrderWithCounter` type:** From `src/orders/types.ts`:
   ```ts
   type OrderProtocolToProtocolData = {
     seaport: OrderWithCounter
   }
   export type OrderProtocol = keyof OrderProtocolToProtocolData
   export type ProtocolData = OrderProtocolToProtocolData[keyof OrderProtocolToProtocolData]
   ```
   The `OrderProtocol` type is a closed enum — only `"seaport"` is valid. Adding Starknet would require adding a `starknet: StarknetOrderWithCounter` entry here and throughout the SDK.

### Seaport Replaceability

**Seaport is tightly coupled, not swappable.** The `BaseSDKConfig` requires a `Seaport` instance:

```ts
export interface BaseSDKConfig {
  wallet: OpenSeaWallet
  contractCaller: ContractCaller
  seaport: Seaport  // <-- required, no alternative interface
  api: OpenSeaAPI
  chain: Chain
  logger: (arg: string) => void
  getAvailableAccounts: () => Promise<string[]>
  cachedPaymentTokenDecimals: { [address: string]: number }
}
```

The `sdk/context.ts` includes `seaport: Seaport` in `SDKContext`. Managers (`OrdersManager`, `FulfillmentManager`, etc.) call `this.context.seaport` directly for `createOrder`, `createBulkOrders`, `matchOrders`, `validate`, `fulfillBasicOrder`, etc.

To support Starknet, either:
- A Starknet-native Seaport-equivalent library would need to implement the exact same `Seaport` interface (currently EVM-only)
- Or the SDK would need significant refactoring to abstract the protocol layer

---

## 4. API Client

### `OpenSeaAPI` Class

**File:** `src/api/api.ts`

**Constructor** (lines 226–265):
```ts
constructor(config: OpenSeaAPIConfig, logger?: (arg: string) => void) {
  this.fetchImpl = config.fetch
  this.apiKey = config.apiKey
  this.authToken = config.authToken
  this.chain = config.chain ?? Chain.Mainnet

  if (config.apiBaseUrl) {
    this.apiBaseUrl = config.apiBaseUrl
  } else {
    this.apiBaseUrl = API_BASE_MAINNET  // "https://api.opensea.io"
  }
  // ...sub-API clients: orders, offers, listings, collections, nfts, etc.
}
```

**REST base URL:** `https://api.opensea.io` (or override via `apiBaseUrl`)

### API Key and Auth Headers

**File:** `src/api/api.ts`, lines 1756–1763

```ts
const mergedHeaders: Record<string, string> = {
  "x-app-id": "opensea-js",
  ...(this.apiKey ? { "X-API-KEY": this.apiKey } : {}),
  ...(this.authToken ? { Authorization: `Bearer ${this.authToken}` } : {}),
  ...(body != null ? { "Content-Type": "application/json" } : {}),
  ...headers,
}
```

- **API key:** Optional `X-API-KEY` header for rate limiting. Public read endpoints work without it.
- **JWT token:** Optional `Authorization: Bearer <jwt>` header for wallet-authenticated endpoints.

### Chain-Specific Behavior in the API Client

The API client itself (`OpenSeaAPI`) is **chain-agnostic at the HTTP layer** — it sends requests to a single `apiBaseUrl`. Chain-specific data is carried via:

1. **URL query parameters:** Many endpoints accept `chain` as a query param (e.g., `api.nfts.getNFTsByContract(address, limit, next, chain)`)
2. **Request body fields:** `chain` appears in request bodies (e.g., fulfillment data requests)
3. **Sub-API clients pass chain:** e.g., `new NFTsAPI(fetcher, this.chain)` — the `NFTsAPI` stores `this.chain` and threads it through

The API **does not switch base URLs per chain** — all chains are served from `https://api.opensea.io`.

### NFT API Models — Chain-Agnostic?

Models in `src/api/types.ts` come from `@opensea/api-types` (the OpenAPI spec package). The types themselves include a `chain` field on most entity types, making them **chain-aware but chain-agnostic in structure** — the same TypeScript type covers assets on any supported chain, with the chain identified by a string field.

---

## 5. Order Execution

### End-to-End Order Creation

**File:** `src/sdk/orders.ts`

**`createOffer`** (lines 561–596):
1. Builds Seaport order via `this.context.seaport.createOrder(...)` — returns `OrderWithCounter` (EIP-712 signed)
2. Calls `useCase.executeAllActions()` — runs approvals + EIP-712 wallet signature
3. Posts to API via `this.context.api.postOffer(order, protocolAddress)`
4. Returns `Offer` (API response)

**`createListing`** (lines 618–662): Same pattern, uses `postListing` instead.

**`createBulkListings`** / **`createBulkOffers`** (lines 686–1017): Use `seaport.createBulkOrders()` — single merkle proof signature for multiple orders, then POST each to the API.

### Seaport's Role in Order Creation

`seaport.createOrder()` (from `@opensea/seaport-js`) handles:
- Building the EIP-712 `OrderComponents` struct
- Requesting the EIP-712 signature from the wallet via `signTypedData`
- Running approval transactions (ERC20/ERC721 approve)

The SDK's `OrdersManager` orchestrates the API calls around Seaport.

### Order Fulfillment

**File:** `src/sdk/fulfillment.ts`

**`fulfillOrder`** (lines 127–269):
1. Calls API: `api.generateFulfillmentData(...)` → returns `FulfillmentDataResponse` with EVM transaction data
2. Encodes using `SeaportABI` (EVM): `contractCaller.encodeFunctionData({ abi: SeaportABI, functionName, args: params })`
3. Appends attribution suffix: `appendCalldataSuffix(encodedData, transaction.calldataSuffix)`
4. Sends via `wallet.signer.sendTransaction({ to, value, data })` — **EVM transaction**
5. Waits for confirmation: `wallet.provider.waitForTransaction(hash)`

**`fulfillPrivateOrder`** (lines 51–106): Uses `seaport.matchOrders(...)` → `.transact()` → EVM transaction.

### What Seaport Does That Would Need a Starknet Equivalent

| Seaport Behavior | Starknet Equivalent Needed |
|---|---|
| `createOrder()` — builds EIP-712 OrderComponents | Starknet order struct + Starknet-native signing |
| `createBulkOrders()` — merkle bulk signature | Starknet pedersen/poseidon merkle tree |
| `matchOrders()` — atomic swap transaction | Starknet `invoke` call to Starknet Seaport contract |
| `validate()` — onchain order validation | Starknet contract view call |
| `fulfillBasicOrder()` — optimized fulfillment | Starknet contract function |
| Order hashing via `keccak256(EIP712.encode(order))` | Starknet Poseidon hash |
| Conduit-based ERC20 approval | Starknet account abstraction + allowance mechanism |

---

## 6. Auth

### Current Auth Model

**File:** `src/auth/types.ts`

```ts
export interface AuthToken {
  accessToken: string   // JWT
  refreshToken: string  // Scoped PAT
  expiresAt: Date
  scopes: string[]
}
```

**File:** `src/api/api.ts`, line 1760:
```ts
...(this.authToken ? { Authorization: `Bearer ${this.authToken}` } : {}),
```

### Auth Flows

**SIWx (Sign-In-With-Anything):** `src/auth/siwx.ts` — wallet signing challenge/response

**OAuth:** `src/auth/oauth.ts` — third-party OAuth flows

**JWT Bearer token:** Set via `OpenSeaAPIConfig.authToken`, sent as `Authorization: Bearer <token>` header on every request.

### Auth Chain-Agnostic?

Auth is **chain-agnostic** — JWT tokens issued by the OpenSea auth server are independent of the blockchain. A Starknet wallet would use the same SIWx flow with Starknet signing (different signature scheme).

---

## 7. Conclusion

### What CAN Be Done Today with the Public SDK (Chain-Agnostic Parts)

1. **All public API read operations** — querying collections, NFTs, orders, events, tokens, listings, offers — work for any chain because the API accepts `chain` as a parameter and the SDK types are chain-agnostic.

2. **Auth flows** — SIWx, OAuth, JWT — are blockchain-signature-based but the auth server is shared.

3. **SDK configuration** — Adding a new `Chain` enum member is mechanically trivial (1 line). The `_AssertAPIChainsCovered` check would need the API types package to include the new chain first.

4. **Cross-chain fulfillment data** — `getCrossChainFulfillmentData()` already supports EVM payment chains + Solana payment chains. This is a backend feature, not a SDK constraint.

### What CANNOT Be Done Without OpenSea Backend Changes

1. **Starknet order signing** — Seaport's EIP-712 signing is incompatible with Starknet's signature scheme (different hash function, different message format). OpenSea backend would need to either:
   - Accept Starknet-native signatures for Seaport-equivalent orders, OR
   - Deploy a Starknet-native version of the Seaport contract with its own order format

2. **Starknet Seaport contract** — `@opensea/seaport-js` produces EVM calldata. A Starknet Seaport-equivalent (StarknetPort?) would need to be deployed by OpenSea and its address added to SDK configuration.

3. **Starknet-specific API endpoints** — If OpenSea's backend stores Starknet NFT data differently (different indexer, different order book), new API endpoints or modified existing ones would be needed. The SDK API client would work if the backend supports it.

4. **Starknet calldata encoding** — `ContractCaller.encodeFunctionData` uses EVM ABI encoding. For Starknet contract calls, a Starknet ABI encoder would be needed.

### Minimum Upstream Patch (Structural Description)

To add Starknet support to the public SDK, OpenSea would need to:

1. **Add `Chain.Starknet = "starknet"`** to the `Chain` enum in `src/types.ts` (and add to `@opensea/api-types`'s `ChainIdentifier` so the `_AssertAPIChainsCovered` check passes).

2. **Add chain config entries** in `src/utils/chain.ts` — `getChainId()`, `getOfferPaymentToken()`, `getListingPaymentToken()`, `getNativeWrapTokenAddress()`, `getDefaultConduit()`, `getSeaportAddress()`, `getSignedZone()`, `getFeeRecipient()` — all need Starknet entries. These are manual `switch`/`if` statements, not data-driven.

3. **Regenerate `src/utils/chainIds.generated.ts`** via `pnpm sync-chains` to include Starknet's chain ID.

4. **Deploy a Starknet Seaport contract** (StarknetPort or equivalent) and add its address to the chain config. The `Seaport` class in `@opensea/seaport-js` cannot be reused — it is EVM-specific. A new `@opensea/starknet-seaport` (hypothetical) package would be needed.

5. **Update `OrderProtocol` and `ProtocolData`** in `src/orders/types.ts` to include a Starknet variant:
   ```ts
   type OrderProtocolToProtocolData = {
     seaport: OrderWithCounter
     starknet: StarknetOrderWithCounter  // New
   }
   ```
   This propagates through every function that accepts/returns `ProtocolData`.

6. **Adapt `OpenSeaSigner`** — `signTypedData` would need to use a Starknet-compatible EIP-712 equivalent. The SDK's signer interface would either need a new method or a different interpretation.

7. **Replace `ContractCaller`** — The current implementation uses EVM ABIs. A Starknet adapter would need Starknet ABI encoding, different address formatting, and different calldata serialization.

8. **Update fulfillment path** — `src/sdk/fulfillment.ts` encodes calls with `SeaportABI`. This entire path would need a Starknet-equivalent.

**This is not a small patch** — it requires a parallel protocol implementation (Starknet Seaport), a new SDK package or significant refactoring to abstract the protocol layer, and backend support for Starknet order ingestion and matching.

---

*Document generated from `src/types.ts`, `src/sdk.ts`, `src/sdk/base.ts`, `src/provider/types.ts`, `src/provider/ethers-adapter.ts`, `src/provider/viem-adapter.ts`, `src/api/api.ts`, `src/api/types.ts`, `src/sdk/orders.ts`, `src/sdk/fulfillment.ts`, `src/sdk/context.ts`, `src/orders/types.ts`, `src/orders/orderUseCase.ts`, `src/orders/utils.ts`, `src/auth/types.ts`, `src/utils/chain.ts`, `src/utils/chainIds.generated.ts`, `src/constants.ts`, `src/viem.ts`.*
