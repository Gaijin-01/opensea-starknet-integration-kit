// packages/core/src/index.ts
// Starknet core types — canonical for the integration kit

export type StarknetAddress = string;
export type StarknetTokenId = string;
export type StarknetChainId = string;
export type StarknetSelector = string;
export type StarknetFelt = string;
export type StarknetContractAddress = string;
export type StarknetNetwork = "mainnet" | "sepolia" | string;
export type TokenStandard = "ERC721" | "ERC1155";

export const CHAIN_IDS = {
  SN_MAIN: "0x534e5f4d41494e",
  SN_SEPOLIA: "0x534e5f5345504f4c4941",
} as const;

export const NETWORK_CHAIN_IDS: Record<StarknetNetwork, StarknetChainId> = {
  mainnet: CHAIN_IDS.SN_MAIN,
  sepolia: CHAIN_IDS.SN_SEPOLIA,
} as const;

export function normalizeAddress(addr: string): StarknetAddress {
  const hex = addr.startsWith("0x") ? addr : `0x${addr}`;
  return hex.toLowerCase();
}

export function parseAddress(raw: string): StarknetAddress {
  const hex = raw.replace(/^0x/i, "").toLowerCase();
  return `0x${hex}`;
}

export function isValidStarknetAddress(addr: string): boolean {
  return /^0x[0-9a-f]{1,64}$/i.test(addr);
}

export function normalizeTokenId(tokenId: string | number | bigint): StarknetTokenId {
  if (typeof tokenId === "number") return tokenId.toString();
  if (typeof tokenId === "bigint") return tokenId.toString();
  return tokenId;
}

export interface StarknetAsset {
  chain: "starknet";
  network: StarknetNetwork;
  contractAddress: StarknetContractAddress;
  tokenId: StarknetTokenId;
  standard: TokenStandard;
  owner?: StarknetAddress;
  balance?: string;
  metadata?: StarknetMetadata;
}

export interface StarknetMetadata {
  name?: string;
  description?: string;
  image?: string;
  externalUrl?: string;
  attributes?: unknown[];
  raw?: Record<string, unknown>;
}

export interface StarknetNFTContract {
  address: StarknetContractAddress;
  standard: TokenStandard;
  name?: string;
  symbol?: string;
  totalSupply?: string;
  contractUri?: string;
}

export interface StarknetTransferEvent {
  blockNumber: number;
  transactionHash: string;
  contractAddress: StarknetContractAddress;
  from: StarknetAddress;
  to: StarknetAddress;
  tokenId: StarknetTokenId;
  standard: TokenStandard;
}

// SRC5 interface IDs (OZ Cairo v2.2.0 verified)
export const SRC5_ID = "0x3f918d17e5ee77373b56385708f855659a07f75997f365cf87748628532a055";
export const IERC721_ID = "0x33eb2f84c309543403fd69f0d0f363781ef06ef6faeb0131ff16ea3175bd943";
export const IERC1155_ID = "0x6114a8f75559e1b39fcba08ce02961a1aa082d9256a158dd3e64964e4b1b52";
export const IERC721_METADATA_ID = "0xabbcd595a99c10485ee78aaf2a7585ef21f81c0ba6e7e4f4791bf98b88a20e";

// Known Sepolia contracts (verified via Infura Sepolia getClassAt)
export const KNOWN_SEPOLIA_CONTRACTS = {
  eth: "0x049d36570d4e46f48e99674bd3fcc84644ddd6b96f7c741b1562b82f9e004dc7",
  strk: "0x04718f5a0fc34cc1af16a1cdee98ffb20c31f5cd61d6ab07201858f4287c938d",
} as const;

// Ark Project contracts (verified from contracts.json in ark-project repo)
export const ARK_CONTRACTS = {
  sepolia: {
    executor: "0xb86ab357c15c12fb78f9b0a19fa974c730fcbab96f17881827dde871665f0b",
    orderbook: "0x795b605fa3144afd6f11a4499f71b9cf373bcba3f1b2835d51f65ab59392261",
  },
  mainnet: {
    executor: "0x7b42945bc47001db92fe1b9739d753925263f2f1036c2ae1f87536c916ee6a",
    orderbook: "0x5add3084bb8664eb2a641cf26a28f60588c3ccd63af0632aafefcbb2332c345",
  },
} as const;

export const ARKCHAIN_RPC = {
  sepolia: "https://sepolia.solis.arkproject.dev",
  mainnet: "https://production.solis.arkproject.dev",
} as const;
