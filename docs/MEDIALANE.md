# Medialane Venue Adapter

## Protocol Overview

Medialane is a hybrid marketplace protocol for Starknet:
- **Off-chain intent layer**: REST API for order discovery and intent creation
- **On-chain settlement**: SNIP-12 signed messages submitted to Medialane's backend
- **No custom smart contracts required**: Listings are settled off-chain, with on-chain settlement triggered by signed messages

## API Endpoints

Base URL: `https://api.medialane.io`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/v1/orders` | x-api-key | Query orders with filters |
| GET | `/v1/tokens/:owner` | x-api-key | Get NFTs owned by address |
| POST | `/v1/intents/listing` | x-api-key | Create listing intent (returns typedData) |
| POST | `/v1/intents/fulfill` | x-api-key | Create fulfill intent (returns executable calls) |
| POST | `/v1/intents/cancel` | x-api-key | Create cancel intent (returns typedData) |

## Contract Addresses

Medialane does not deploy contracts on Starknet — settlement is handled off-chain via their backend. NFT custody is transferred via the signed calls returned from fulfill intents.

## SNIP-12 Flow

### Create Listing

```
1. client.medialaneCreateListingIntent({ offerer, nftContract, tokenId, price, currency })
   → returns { intentId, requiresSignature: true, typedData, submitUrl }

2. account.signTypedData(typedData)  ← SNIP-12 signature from wallet

3. client.medialaneSubmitSignedCalls(submitUrl, signature)
   → returns { transactionHash?, calls[] }

4. account.execute(calls)  ← execute received calls on-chain
```

### Fulfill Listing (NO signature required)

```
1. client.medialaneCreateFulfillIntent({ fulfiller, orderHash, amount })
   → returns { intentId, requiresSignature: false, executableCalls[] }

2. account.execute(executableCalls)  ← execute calls directly
```

### Cancel Listing

```
1. client.medialaneCreateCancelIntent({ seller, orderHash, tokenAddress, tokenId })
   → returns { intentId, requiresSignature: true, typedData, submitUrl }

2. account.signTypedData(typedData)  ← SNIP-12 signature

3. client.medialaneSubmitSignedCalls(submitUrl, signature)
   → returns { transactionHash?, calls[] }

4. account.execute(calls)  ← execute cancel calls on-chain
```

## Usage

```ts
import { MedialaneAdapter } from '@storm/venue-medialane';

const adapter = new MedialaneAdapter({ apiKey: process.env.MEDIALANE_API_KEY });

// Get listings for an asset
const listings = await adapter.getListingsForAsset(
  '0x...nftContract...',
  '123',
  { network: 'sepolia' }
);

// Create a listing (requires wallet)
const result = await adapter.createListing({
  venue: 'medialane',
  asset: { contractAddress: '0x...', tokenId: '123', standard: 'ERC721' },
  price: { amount: '1000000000000000000', currency: 'ETH', decimals: 18 },
  validUntil: Math.floor(Date.now() / 1000) + 86400 * 30,
}, account);

console.log('Tx:', result.transactionHash);
```

## API Key

**IMPORTANT**: The Medialane API key must NOT be exposed to browser code. Use the reference server or your own backend to proxy requests. Never include `MEDIALANE_API_KEY` in browser bundles.
