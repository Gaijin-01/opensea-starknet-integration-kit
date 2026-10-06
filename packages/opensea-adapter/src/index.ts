/**
 * @storm/opensea-adapter
 *
 * Demonstrates how the OpenSea SDK's abstract interfaces (OpenSeaSigner,
 * OpenSeaProvider, OpenSeaWallet) can be implemented for Starknet without
 * modifying the upstream @opensea/sdk package.
 *
 * KEY INSIGHT: The OpenSea SDK uses ethers Signer/Provider as its concrete
 * implementation, but exposes them through abstract interfaces:
 *
 *   OpenSeaSigner  → { getAddress(), sendTransaction(), signTypedData() }
 *   OpenSeaProvider → { waitForTransaction() }
 *   OpenSeaWallet  → { signer?, provider }
 *
 * These interfaces are chain-agnostic — they only describe wallet RPC semantics.
 * Starknet can satisfy every method:
 *
 *   getAddress()        → Starknet account address (felt252, 0x-prefixed)
 *   sendTransaction()   → account.execute(calls) → tx hash
 *   signTypedData()    → SNIP-12 (EIP-712 → Starknet typed data)
 *   waitForTransaction() → RpcProvider.waitForTransaction()
 *
 * WHAT WORKS TODAY (adapter-only, no upstream change needed):
 * - waitForTransaction()     ✓  RpcProvider.waitForTransaction()
 * - getAddress()             ✓  account.address
 * - sendTransaction()        ✓  account.execute() (semantic equivalent)
 * - OpenSeaWallet composition ✓  signer + provider composition
 *
 * WHAT REQUIRES OPENSEA UPSTREAM CHANGES:
 * - Chain.Starknet enum value  — "starknet" must be a recognized chain ID
 * - REST API chain queries     — backend must index Starknet NFT events
 * - Seaport settlement         — EVM-only; Starknet needs Medialane/Ark
 * - Order lifecycle           — backend must validate Starknet signatures
 *
 * WHAT REQUIRES OPENSEA PRIVATE BACKEND:
 * - NFT ingestion for Starknet contracts
 * - Starknet address format in order storage
 * - SNIP-12 signature verification endpoint
 * - Venue attribution for Medialane/Ark settlements
 */

// OpenSea SDK interface types (copied from @opensea/sdk provider/types.ts)
// These are the minimal interfaces the OpenSea SDK expects.
// They are chain-agnostic and fully implementable for Starknet.

/** Transaction receipt returned after sending a transaction. */
export interface TransactionResponse {
  hash: string
  wait(): Promise<void>
}

/** Minimal signer interface for the OpenSea SDK. */
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

/** Minimal provider interface for the OpenSea SDK. */
export interface OpenSeaProvider {
  waitForTransaction(hash: string): Promise<void>
}

/** Combined wallet: either signer+provider or provider-only. */
export type OpenSeaWallet =
  | { signer: OpenSeaSigner; provider: OpenSeaProvider }
  | { provider: OpenSeaProvider }

/**
 * Transaction receipt returned after sending a transaction.
 * Mirrors the OpenSea SDK's TransactionResponse interface.
 */
export interface StarknetTransactionResponse {
  hash: string
  wait(): Promise<void>
}

/**
 * Minimal OpenSeaProvider implementation for Starknet.
 *
 * The OpenSeaProvider interface requires only one method: waitForTransaction().
 * This is fully chain-agnostic — starknet.js RpcProvider.waitForTransaction()
 * has identical semantics to ethers Provider.waitForTransaction().
 */
export class StarknetOpenSeaProvider implements OpenSeaProvider {
  constructor(private rpcProvider: unknown) {
    if (!rpcProvider) {
      throw new Error("RpcProvider is required")
    }
  }

  async waitForTransaction(hash: string): Promise<void> {
    const provider = this.rpcProvider as {
      waitForTransaction(hash: string): Promise<unknown>
    }
    await provider.waitForTransaction(hash)
  }
}

/**
 * Minimal OpenSeaSigner implementation for Starknet.
 *
 * Implements the three methods required by OpenSeaSigner:
 * - getAddress(): Returns the Starknet account address (felt252, 0x-prefixed)
 * - sendTransaction(): Maps EVM-style tx to account.execute(calls)
 * - signTypedData(): Maps EIP-712 domain to SNIP-12 signing
 *
 * NOTE: The SNIP-12 mapping is a proof-of-concept. Production use requires
 * strict SNIP-12 struct construction per the SNIP-12 specification.
 */
export class StarknetOpenSeaSigner implements OpenSeaSigner {
  constructor(private account: unknown) {
    if (!account) {
      throw new Error("Starknet Account is required")
    }
  }

  async getAddress(): Promise<string> {
    const account = this.account as { address: string }
    return account.address
  }

  async sendTransaction(tx: {
    to: string
    data?: string
    value?: string | number | bigint
    from?: string
    overrides?: Record<string, unknown>
  }): Promise<StarknetTransactionResponse> {
    const account = this.account as {
      execute(
        calls: Array<{
          contractAddress: string
          entrypoint: string
          calldata?: unknown[]
        }>,
        options?: { maxFee?: bigint }
      ): Promise<{ transaction_hash: string }>
    }

    const calls = [
      {
        contractAddress: tx.to,
        entrypoint: "invoke",
        calldata: (tx.data ? [tx.data] : []) as unknown[],
      },
    ]

    const result = await account.execute(calls, tx.overrides as { maxFee?: bigint })

    return {
      hash: result.transaction_hash,
      async wait() {
        const provider = (account as unknown as { provider: StarknetOpenSeaProvider }).provider
        await provider.waitForTransaction(result.transaction_hash)
      },
    }
  }

  async signTypedData(
    domain: {
      chainId: string | number
      name: string
      version: string
      verifyingContract: string
    },
    types: Record<string, Array<{ name: string; type: string }>>,
    value: Record<string, unknown>,
  ): Promise<string> {
    const account = this.account as {
      signMessage(message: unknown): Promise<{ signature: string[] }>
    }

    // EIP-712 → SNIP-12 mapping:
    // SNIP-12 (Starknet signed typed data) uses felt types and a
    // StarknetDomain struct. This is a simplified mapping.
    const snip12Message = {
      domain: {
        name: domain.name,
        version: domain.version,
        chain_id: domain.chainId.toString(),
        verifying_contract: domain.verifyingContract,
      },
      types: {
        StarknetDomain: [
          { name: "name", type: "felt" },
          { name: "version", type: "felt" },
          { name: "chain_id", type: "felt" },
          { name: "verifying_contract", type: "felt" },
        ],
        ...Object.fromEntries(
          Object.entries(types).map(([key, fields]) => [
            key,
            fields.map((f) => ({
              ...f,
              type: f.type === "address" ? "felt" : f.type,
            })),
          ])
        ),
      },
      primaryType: Object.keys(types)[0],
      message: value,
    }

    const result = await account.signMessage(snip12Message)
    return result.signature.join(",")
  }
}

/**
 * Creates an OpenSeaWallet from a starknet.js Account.
 *
 * Usage:
 * ```ts
 * import { RpcProvider, Account } from 'starknet'
 * import { createStarknetOpenSeaWallet } from '@storm/opensea-adapter'
 *
 * const provider = new RpcProvider({ nodeUrl: '...' })
 * const account = new Account(provider, address, privateKey)
 * const wallet = createStarknetOpenSeaWallet(account)
 * // wallet is compatible with OpenSea SDK's OpenSeaWallet interface
 * ```
 */
export function createStarknetOpenSeaWallet(
  account: unknown,
  rpcProvider?: unknown,
): OpenSeaWallet {
  const provider = rpcProvider ?? (account as { provider?: unknown }).provider

  if (!provider) {
    throw new Error(
      "Starknet account must be connected to a provider. " +
        "Pass an RpcProvider as the second argument or use an Account with a connected provider."
    )
  }

  return {
    signer: new StarknetOpenSeaSigner(account),
    provider: new StarknetOpenSeaProvider(provider),
  }
}


