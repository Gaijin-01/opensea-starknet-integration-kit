// starknet/clients/typescript/src/ark.ts
/**
 * Ark Project integration using @ark-project/core v2.1.2
 *
 * Fully on-chain NFT marketplace on Starknet.
 * All operations are DIRECT ON-CHAIN via the Ark Executor contract.
 * NO off-chain SNIP-12 signing — all state changes go through Starknet L1/L2.
 *
 * Ground truth sources (confirmed from contracts.json + @ark-project/core source):
 *   Executor Sepolia:  0xb86ab357c15c12fb78f9b0a19fa974c730fcbab96f17881827dde871665f0b
 *   Executor Mainnet:  0x7b42945bc47001db92fe1b9739d753925263f2f1036c2ae1f87536c916ee6a
 *   Orderbook Sepolia: 0x795b605fa3144afd6f11a4499f71b9cf373bcba3f1b2835d51f65ab59392261
 *   Orderbook Mainnet: 0x5add3084bb8664eb2a641cf26a28f60588c3ccd63af0632aafefcbb2332c345
 *
 * Arkchain RPC (Solis): sepolia = https://sepolia.solis.arkproject.dev
 *                       mainnet = https://production.solis.arkproject.dev
 *
 * This module wraps @ark-project/core with the confirmed contract addresses
 * and provides both the SDK interface and direct calldata builders.
 */

import {
  createConfig,
  createListing,
  fulfillListing,
  cancelOrder,
  type Config,
  type ListingV1,
  type RouteType,
} from "@ark-project/core";

import { Account, Call } from "starknet";

// ---------------------------------------------------------------------------
// Contract addresses (compile-time constants, confirmed from contracts.json)
// ---------------------------------------------------------------------------

export const ARK_CONTRACTS = {
  sepolia: {
    executor: "0xb86ab357c15c12fb78f9b0a19fa974c730fcbab96f17881827dde871665f0b",
    orderbook: "0x795b605fa3144afd6f11a4499f71b9cf373bcba3f1b2835d51f65ab59392261",
    messaging: "0x74f13f1dffb5ad3c051d535ba03514e653b6dcac68e30b2db66a0aa0217c815",
  },
  mainnet: {
    executor: "0x7b42945bc47001db92fe1b9739d753925263f2f1036c2ae1f87536c916ee6a",
    orderbook: "0x5add3084bb8664eb2a641cf26a28f60588c3ccd63af0632aafefcbb2332c345",
    messaging: "0x0",
  },
} as const;

export const ARKCHAIN_RPC = {
  sepolia: "https://sepolia.solis.arkproject.dev",
  mainnet: "https://production.solis.arkproject.dev",
} as const;

// RouteType enum (confirmed from @ark-project/core types)
export const ROUTE_TYPE = {
  Erc721ToErc20: 1,
  Erc1155ToErc20: 2,
} as const;

// ---------------------------------------------------------------------------
// Config factory
// ---------------------------------------------------------------------------

/**
 * Create an Ark SDK Config for the given network.
 *
 * @param network - "sepolia" | "mainnet"
 * @param starknetRpcUrl - Override the default RPC URL
 * @param starknetAccount - Optional Account for write operations
 */
export function createArkConfig(
  network: "sepolia" | "mainnet",
  starknetRpcUrl?: string
): Config {
  const rpcUrl =
    starknetRpcUrl ||
    (network === "mainnet"
      ? "https://starknet-mainnet.public.blastapi.io/rpc/v0_6"
      : "https://starknet-sepolia.public.blastapi.io/rpc/v0_6");

  return createConfig({
    starknetNetwork: network,
    starknetRpcUrl: rpcUrl,
    starknetExecutorContract: ARK_CONTRACTS[network].executor,
    starknetCurrencyContract:
      "0x049d36570d4e46f48e99674bd3fcc84644ddd6b96f7c741b1562b82f9e004dc7", // ETH Sepolia
    arkchainNetwork: network,
    arkchainRpcUrl: ARKCHAIN_RPC[network],
  });
}

// ---------------------------------------------------------------------------
// High-level SDK wrappers
// ---------------------------------------------------------------------------

/**
 * Create a listing on Ark using the @ark-project/core SDK.
 *
 * @param config - Ark SDK Config
 * @param account - Starknet Account (signer)
 * @param order - ListingV1 order parameters
 * @param approveInfo - NFT approval info (which NFT to approve for the executor)
 * @returns Order hash as bigint (Arkchain order ID)
 */
export async function arkCreateListing(
  config: Config,
  account: Account,
  order: ListingV1,
  approveInfo: { tokenAddress: string; tokenId: bigint }
): Promise<bigint> {
  return createListing(config, {
    // @ts-ignore — starknet.js type gap: Account lacks getSuggestedFee declared in AccountInterface
    starknetAccount: account,
    order,
    approveInfo,
  });
}

/**
 * Fulfill a listing on Ark using the @ark-project/core SDK.
 *
 * @param config - Ark SDK Config
 * @param account - Starknet Account (fulfiller)
 * @param fulfillListingInfo - { orderHash: bigint, currencyAmount: string }
 * @param approveInfo - Currency approval info
 * @returns Transaction hash
 */
export async function arkFulfillListing(
  config: Config,
  account: Account,
  fulfillListingInfo: { orderHash: bigint; tokenAddress: string; tokenId: bigint; brokerId: string },
  approveInfo: { currencyAddress: string; amount: bigint }
): Promise<void> {
  return fulfillListing(config, {
    // @ts-ignore — starknet.js type gap: Account lacks getSuggestedFee declared in AccountInterface
    starknetAccount: account,
    fulfillListingInfo,
    approveInfo,
  });
}

/**
 * Cancel an order on Ark using the @ark-project/core SDK.
 *
 * @param config - Ark SDK Config
 * @param account - Starknet Account (canceller, must be the offerer)
 * @param orderHash - Order hash to cancel
 * @returns Transaction hash
 */
export async function arkCancelOrder(
  config: Config,
  account: Account,
  cancelInfo: { orderHash: bigint; tokenAddress: string; tokenId: bigint }
): Promise<void> {
  return cancelOrder(config, {
    // @ts-ignore — starknet.js type gap: Account lacks getSuggestedFee declared in AccountInterface
    starknetAccount: account,
    cancelInfo,
  });
}

// ---------------------------------------------------------------------------
// Direct calldata builders (no SDK dependency)
// ---------------------------------------------------------------------------

/**
 * Build the ERC-721 approve call for Ark executor approval.
 */
export function buildApproveNftCall(
  nftContract: string,
  tokenId: string | number,
  network: "sepolia" | "mainnet" = "sepolia"
): Call {
  return {
    contractAddress: nftContract,
    entrypoint: "approve",
    calldata: [
      ARK_CONTRACTS[network].executor, // operator
      tokenId.toString(), // token_id
    ],
  };
}

/**
 * Build the ERC-20 approve call for currency.
 */
export function buildApproveErc20Call(
  currencyContract: string,
  amount: string | number,
  network: "sepolia" | "mainnet" = "sepolia"
): Call {
  return {
    contractAddress: currencyContract,
    entrypoint: "approve",
    calldata: [
      ARK_CONTRACTS[network].executor, // spender
      amount.toString(), // amount (uint256 low + high if needed)
    ],
  };
}

/**
 * Build the createListing call for direct executor invocation.
 *
 * OrderV1 fields (confirmed from @ark-project/core types):
 *   route_type: RouteType (1 = ERC721→ERC20, 2 = ERC1155→ERC20)
 *   collection: NFT contract address
 *   token_id: token ID as string
 *   start_amount: price (string)
 *   end_amount: optional end price for TWAMPs (string, 0 = fixed)
 *   currency: ERC-20 contract address ("0" = ETH/STRK native)
 *   start_date: Unix timestamp
 *   end_date: Unix timestamp
 *   broker_id: royalties recipient (0 = none)
 *   zone: execution zone (0 = default)
 *   salt: salt for order hash (0 = auto)
 *   expired_for_tokens: expired token IDs list
 */
export function buildCreateListingCall(
  order: {
    collection: string;
    tokenId: string | number;
    startAmount: string | number;
    currency?: string;
    startDate?: number;
    endDate?: number;
    brokerId?: string;
    /** RouteType: 1 = ERC721→ERC20, 2 = ERC1155→ERC20 (not yet in @ark-project/core RouteType enum) */
    routeType?: 1 | 2;
  },
  network: "sepolia" | "mainnet" = "sepolia"
): Call {
  const now = Math.floor(Date.now() / 1000);
  return {
    contractAddress: ARK_CONTRACTS[network].executor,
    entrypoint: "createListing",
    calldata: [
      (order.routeType ?? ROUTE_TYPE.Erc721ToErc20).toString(),
      order.collection,
      order.tokenId.toString(),
      order.startAmount.toString(),
      "0", // end_amount (fixed price)
      order.currency ?? "0", // currency (0 = ETH)
      (order.startDate ?? now).toString(),
      (order.endDate ?? now + 30 * 86400).toString(),
      order.brokerId ?? "0", // broker_id
      "0", // zone
    ],
  };
}

/**
 * Build the fulfillListing call for direct executor invocation.
 */
export function buildFulfillListingCall(
  orderHash: bigint | string,
  currencyAmount: string | number,
  network: "sepolia" | "mainnet" = "sepolia"
): Call {
  return {
    contractAddress: ARK_CONTRACTS[network].executor,
    entrypoint: "fulfillListing",
    calldata: [orderHash.toString(), currencyAmount.toString()],
  };
}

/**
 * Build the cancelOrder call for direct executor invocation.
 */
export function buildCancelOrderCall(
  orderHash: bigint | string,
  network: "sepolia" | "mainnet" = "sepolia"
): Call {
  return {
    contractAddress: ARK_CONTRACTS[network].executor,
    entrypoint: "cancelOrder",
    calldata: [orderHash.toString()],
  };
}
