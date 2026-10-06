/**
 * Starknet adapter for OpenSea SDK.
 *
 * Demonstrates how OpenSeaSigner + OpenSeaProvider can be implemented
 * for Starknet without modifying the upstream SDK.
 *
 * Usage:
 * ```ts
 * import { createStarknetOpenSeaWallet } from './starknet-signer-adapter';
 * import { OpenSeaSDK, Chain } from '@opensea/sdk';
 *
 * const starknetWallet = await createStarknetOpenSeaWallet();
 * const sdk = new OpenSeaSDK(starknetWallet, { chain: 'starknet' });
 * ```
 *
 * NOTE: This requires OpenSea SDK to accept 'starknet' as a chain identifier.
 */

import type {
  OpenSeaProvider,
  OpenSeaSigner,
  OpenSeaWallet,
  TransactionResponse,
} from "./types"

// Starknet types — using starknet.js v10.8.0
// import type { Account, RpcProvider } from 'starknet'

/**
 * Minimal OpenSeaProvider implementation for Starknet using RpcProvider.
 */
export class StarknetOpenSeaProvider implements OpenSeaProvider {
  constructor(private rpcProvider: unknown) {
    // rpcProvider should be a starknet.js RpcProvider instance
  }

  async waitForTransaction(hash: string): Promise<void> {
    // starknet.js RpcProvider.waitForTransaction returns a TransactionReceipt
    const provider = this.rpcProvider as {
      waitForTransaction: (hash: string) => Promise<unknown>
    }
    await provider.waitForTransaction(hash)
  }
}

/**
 * Minimal OpenSeaSigner implementation for Starknet using Account.
 */
export class StarknetOpenSeaSigner implements OpenSeaSigner {
  constructor(private account: unknown) {
    // account should be a starknet.js Account instance (WalletAccountV6)
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
  }): Promise<TransactionResponse> {
    const account = this.account as {
      execute: (
        calls: Array<{ contractAddress: string; entrypoint: string; calldata?: unknown[] }>,
        options?: { maxFee?: bigint }
      ) => Promise<{ transaction_hash: string }>
    }

    // Map EVM-style tx to Starknet account.execute(calls)
    const calls = [
      {
        contractAddress: tx.to,
        entrypoint: tx.data ? "invoke" : "transfer",
        calldata: tx.data
          ? // Calldata would need ABI encoding — simplified here
            []
          : [
              // For transfer: target is recipient, data would be empty
              // This is a simplified mapping; real implementation needs
              // proper calldata encoding based on target contract ABI
            ],
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
      signMessage: (message: unknown) => Promise<{ signature: string[] }>
    }

    // EIP-712 → SNIP-12 mapping:
    // SNIP-12 uses Starknet-specific typed data format.
    // The domain struct becomes a SNIP-12 StructType with:
    //   - chainId (felt)
    //   - name (felt)
    //   - version (felt)
    //   - verifyingContract (felt, Starknet contract address)
    //
    // This is a proof-of-concept: real SNIP-12 signing requires
    // constructing the proper SNIP-12 Message struct per:
    // https://github.com/starknet-io/SNIPs/blob/main/SNIPS/snip-12.md
    const snip12Message = {
      domain: {
        name: domain.name,
        version: domain.version,
        chain_id: domain.chainId.toString(),
        verifying_contract: domain.verifyingContract,
      },
      types: {
        // SNIP-12 requires these canonical types always present
        StarknetDomain: [
          { name: "name", type: "felt" },
          { name: "version", type: "felt" },
          { name: "chain_id", type: "felt" },
          { name: "verifying_contract", type: "felt" },
        ],
        // Map EIP-712 types to SNIP-12 felt types
        ...Object.fromEntries(
          Object.entries(types).map(([key, fields]) => [
            key,
            fields.map((f) => ({
              ...f,
              // SNIP-12 uses "felt" where EIP-712 might use address, uint256, etc.
              // This is a simplification; real mapping needs type-aware conversion
              type: f.type === "address" ? "felt" : f.type,
            })),
          ])
        ),
      },
      primaryType: Object.keys(types)[0],
      message: value,
    }

    const result = await account.signMessage(snip12Message)
    // Return as hex string array joined with comma (Starknet signature format)
    return result.signature.join(",")
  }
}

/**
 * Creates an OpenSeaWallet from a starknet.js Account.
 *
 * @param account - A starknet.js Account instance (WalletAccountV6)
 * @param rpcProvider - Optional RpcProvider; if not provided, extracted from account
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
