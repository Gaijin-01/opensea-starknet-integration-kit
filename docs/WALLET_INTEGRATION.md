# Wallet Integration

## Overview

The `@storm/wallet` package provides wallet connection and signing for browser applications. It wraps `@starknet-io/get-starknet` and `starknet.js` with a unified interface.

## Getting Started

```ts
import { connectWallet } from '@storm/wallet';

const result = await connectWallet();
if (!result) {
  console.log('No wallet installed');
  return;
}

const { account, address, chainId } = result;
console.log('Connected:', address);
```

## get-starknet

`getStarknet()` is the canonical way to get the browser Starknet wallet (Argent X, Braavos, etc.):

```ts
import getStarknet from '@starknet-io/get-starknet';

const starknet = await getStarknet();
const { account } = starknet;
```

The `@storm/wallet` package wraps this with:
- Connection state management
- Chain/network detection
- Disconnect handling

## Account Types

### WalletAccountV6

The standard starknet.js account type that works with browser wallets:

```ts
import { WalletAccountV6, RpcProvider } from 'starknet';

const provider = new RpcProvider({ nodeUrl: '...' });
const account = new WalletAccountV6(provider, address);
```

### SNIP-12 Signing

SNIP-12 (Starknet Signed Typed Data) is used for listing and cancel operations:

```ts
// Sign a SNIP-12 typed data structure
const signature = await account.signTypedData(domain, types, message);

// Verify
const isValid = await account.verifyMessage(typedData, { r, s });
```

### Transaction Execution

```ts
const { transaction_hash } = await account.execute([
  {
    contractAddress: nftContract,
    entrypoint: 'approve',
    calldata: [executorAddress, tokenId],
  },
  {
    contractAddress: executorAddress,
    entrypoint: 'createListing',
    calldata: [...],
  },
], undefined, { maxFee: '0x...' });
```

## Network Detection

```ts
import { NETWORK_CHAIN_IDS } from '@storm/core';

const isMainnet = chainId === NETWORK_CHAIN_IDS.mainnet; // '0x534e5f4d41494e'
const isSepolia = chainId === NETWORK_CHAIN_IDS.sepolia; // '0x534e5f5345504f4c4941'
```

## Error Handling

```ts
try {
  const result = await account.execute(calls);
} catch (err) {
  if (err.message.includes(' insufficient funds')) {
    console.log('Not enough ETH for gas');
  } else if (err.message.includes('nonce mismatch')) {
    console.log('Transaction conflict, retry');
  } else {
    throw err;
  }
}
```

## Browser Environment

Wallet connection only works in browser environments (not Node.js). Use dynamic imports to avoid SSR issues:

```ts
async function connect() {
  const { connectWallet } = await import('@storm/wallet');
  return connectWallet();
}
```
