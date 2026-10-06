// starknet/clients/typescript/src/wallet.ts
/**
 * Browser wallet integration using starknet.js v10.8.0
 *
 * Supports: Braavos, Argent X, Argent Mobile, Cartridge, Xverse, MetaMask Snap
 * via the window.starknet Starknet Window Object (SWO).
 *
 * Normal users: NEVER provide a private key.
 * Only the disposable test account (backend-only) bypasses browser signing.
 *
 * Key classes (starknet.js v10.8.0):
 *   connectV6()  — factory function for wallet connection
 *   WalletAccountV6  — latest wallet account (V6 API)
 *   RpcProvider      — JSON-RPC provider
 *   TypedData        — SNIP-12 typed data
 *
 * @example
 * // Browser: connect wallet
 * const wallet = await connectBrowserWallet();
 * const address = wallet.account.address;
 *
 * // SNIP-12 signing
 * const signature = await wallet.account.signMessage(typedData);
 *
 * // Execute transaction
 * const { transaction_hash } = await wallet.account.execute(calls);
 */

import {
  RpcProvider,
  walletV6,
  WalletAccountV6,
  Account,
  Call,
  TypedData,
  type Signature,
} from "starknet";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface DiscoveredWallet {
  id: string;
  name: string;
  icon: string;
  account: Account;
  provider: RpcProvider;
  chainId: string;
}

export interface WalletInfo {
  id: string;
  name: string;
  icon: string;
  downloadUrl: string;
}

export const KNOWN_WALLETS: WalletInfo[] = [
  { id: "braavos", name: "Braavos", icon: "🦁", downloadUrl: "https://braavos.app" },
  { id: "argentx", name: "Argent X", icon: "🔷", downloadUrl: "https://www.argent.xyz/argent-x/" },
  { id: "argent", name: "Argent", icon: "🔷", downloadUrl: "https://www.argent.xyz/wallet/" },
  { id: "cartridge", name: "Cartridge", icon: "🎮", downloadUrl: "https://cartridge.gg" },
  { id: "xverse", name: "Xverse", icon: "📱", downloadUrl: "https://www.xverse.web" },
  { id: "metamask", name: "MetaMask Snap", icon: "🦊", downloadUrl: "https://metamask.io" },
];

// Starknet Window Object (SWO) — the window.starknet interface
declare global {
  interface Window {
    starknet?: {
      enable(options?: { starknetWallet?: string }): Promise<string[]>;
      disconnect(): Promise<void>;
      isPreauthorized(): Promise<boolean>;
      requestAccounts(options?: { silentMode?: boolean }): Promise<string[]>;
      getPermissions(): Promise<{ resource: string; proof: unknown }[]>;
      chainId(): Promise<string>;
      switchStarknetChain(chainId: string): Promise<boolean>;
      account: string;
      selectedAddress: string;
    };
  }
}

// ---------------------------------------------------------------------------
// Wallet connection state
// ---------------------------------------------------------------------------

export type WalletConnectionState =
  | { status: 'disconnected' }
  | { status: 'connecting' }
  | { status: 'connected'; wallet: DiscoveredWallet }
  | { status: 'error'; error: string };

export const STARKNET_WALLET_EVENTS = {
  ACCOUNTS_CHANGED: 'accountsChanged',
  CHAIN_CHANGED: 'chainChanged',
  DISCONNECT: 'disconnect',
} as const;

// ---------------------------------------------------------------------------
// Provider factory
// ---------------------------------------------------------------------------

export const DEFAULT_RPC =
  (typeof import.meta !== "undefined"
    ? (import.meta as { env?: Record<string, string> }).env?.VITE_STARKNET_RPC
    : undefined) ||
  (typeof process !== "undefined" ? process.env?.STARKNET_RPC_URL : undefined) ||
  (typeof process !== "undefined" ? process.env?.STARKNET_RPC : undefined) ||
  "https://starknet-sepolia.infura.io/v3/YOUR_INFURA_KEY";

export function createProvider(rpcUrl?: string): RpcProvider {
  return new RpcProvider({ nodeUrl: rpcUrl || DEFAULT_RPC });
}

// ---------------------------------------------------------------------------
// Browser wallet connection
// ---------------------------------------------------------------------------

/**
 * Connect to the browser wallet via window.starknet.
 *
 * Uses walletV6.standardConnect() from starknet.js v10.8.0 which handles
 * wallet discovery and WalletAccountV6 creation automatically.
 *
 * Does NOT take a private key — signing is handled by the browser wallet.
 */
export async function connectWallet(
  rpcUrl?: string
): Promise<DiscoveredWallet | null> {
  if (typeof window === "undefined" || !window.starknet) return null;

  try {
    // walletV6.standardConnect() takes the window.starknet SWO object
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const swo = window.starknet as any;
    const result = await walletV6.standardConnect(swo);
    const accounts = result.accounts;
    if (!accounts?.length) return null;

    const accountAddress = accounts[0].address;
    const chainId = (await walletV6.requestChainId(swo)) as string;
    const provider = createProvider(rpcUrl);

    // Create WalletAccountV6 from the SWO
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const account = new WalletAccountV6({
      provider,
      walletProvider: window.starknet as any,
      address: accountAddress,
    });

    return {
      id: "browser",
      name: "Browser Wallet",
      icon: "🌐",
      account,
      provider,
      chainId,
    };
  } catch {
    return null;
  }
}

/**
 * Connect to a specific wallet type (braavos, argentx, etc.).
 * Passes the walletId to window.starknet.enable({ starknetWallet: id }).
 */
export async function connectNamedWallet(
  walletId: string,
  rpcUrl?: string
): Promise<DiscoveredWallet | null> {
  if (typeof window === "undefined" || !window.starknet) return null;

  try {
    const addresses = await window.starknet.enable({ starknetWallet: walletId });
    if (!addresses?.length) return null;

    const accountAddress = addresses[0];
    const chainId = (await window.starknet.chainId()) as string;
    const provider = createProvider(rpcUrl);

    // Use WalletAccountV6 constructor directly with the SWO
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const account = new WalletAccountV6({
      provider,
      walletProvider: window.starknet as any,
      address: accountAddress,
    });

    return {
      id: walletId,
      name: walletId,
      icon: "🌐",
      account,
      provider,
      chainId,
    };
  } catch {
    return null;
  }
}

/**
 * Disconnect the currently connected wallet.
 */
export async function disconnectWallet(): Promise<void> {
  if (typeof window !== "undefined" && window.starknet) {
    await window.starknet.disconnect();
  }
}

/**
 * Get the connected account if one exists.
 */
export function getConnectedAccount(wallet: DiscoveredWallet): Account {
  return wallet.account;
}

/**
 * Get the chain ID for a connected wallet.
 */
export function getChainId(wallet: DiscoveredWallet): string {
  return wallet.chainId;
}

/**
 * Get the list of known wallet types available for download.
 */
export function getKnownWallets(): WalletInfo[] {
  return [...KNOWN_WALLETS];
}

// ---------------------------------------------------------------------------
// SNIP-12 signing via browser wallet
// ---------------------------------------------------------------------------

/**
 * Sign a SNIP-12 typed data structure using the browser wallet.
 *
 * Uses Account.signMessage(typedData) which implements the SNIP-12
 * signing flow for the connected wallet (SNIP-12 revision 1).
 *
 * @param wallet - The connected browser wallet
 * @param typedData - SNIP-12 domain + message definition
 * @returns Signature as string[] (r, s values as hex strings)
 */
export async function signTypedData(
  wallet: DiscoveredWallet,
  typedData: TypedData
): Promise<Signature> {
  return wallet.account.signMessage(typedData);
}

// ---------------------------------------------------------------------------
// Transaction execution
// ---------------------------------------------------------------------------

export interface ExecutionResult {
  transaction_hash: string;
}

export interface TransactionReceipt {
  finality_status: string;
  block_number: number;
  status: string;
}

/**
 * Execute contract calls through the browser wallet.
 *
 * The wallet will prompt the user to sign and confirm the transaction.
 *
 * @param wallet - Connected browser wallet
 * @param calls - Array of Starknet contract calls
 * @returns Transaction hash
 */
export async function execute(
  wallet: DiscoveredWallet,
  calls: Call | Call[]
): Promise<ExecutionResult> {
  const result = await wallet.account.execute(calls);
  return { transaction_hash: result.transaction_hash };
}

/**
 * Wait for a transaction to reach a final state.
 */
export async function waitForTransaction(
  wallet: DiscoveredWallet,
  txHash: string
): Promise<TransactionReceipt> {
  const receipt = await wallet.provider.waitForTransaction(txHash, {
    successStates: ["ACCEPTED_ON_L2", "ACCEPTED_ON_L1"],
  });
  // v10: GetTransactionReceiptResponse has block_number + status fields
  const r = receipt as unknown as {
    block_number?: number;
    finality_status?: string;
    status?: string;
  };
  return {
    finality_status: r.finality_status ?? r.status ?? "UNKNOWN",
    block_number: r.block_number ?? 0,
    status: r.status ?? r.finality_status ?? "UNKNOWN",
  };
}

/**
 * Estimate the fee for a set of calls.
 * Returns overall_fee (bigint) and resource bounds.
 */
export async function estimateInvokeFee(
  wallet: DiscoveredWallet,
  calls: Call | Call[]
): Promise<{ overall_fee: bigint; unit: string }> {
  const est = await wallet.account.estimateInvokeFee(calls);
  return {
    overall_fee: est.overall_fee,
    unit: est.unit,
  };
}

// ---------------------------------------------------------------------------
// Chain constants
// ---------------------------------------------------------------------------

export const CHAIN_IDS: Record<string, string> = {
  "0x534e5f5345504f4c4941": "SN_SEPOLIA",
  "0x534e5f4d41494e": "SN_MAIN",
};

export function chainName(chainId: string): string {
  return CHAIN_IDS[chainId] ?? chainId;
}
