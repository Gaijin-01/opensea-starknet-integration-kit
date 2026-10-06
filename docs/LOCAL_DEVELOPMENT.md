# Local Development Setup

## Prerequisites

- **Node.js** 20+ (LTS recommended)
- **npm** 10+
- A **Starknet wallet** (Argent X or Braavos) installed in your browser
- **Sepolia ETH** for testing (faucet: https://faucet.starknet.io/)

## Bootstrap

```bash
cd starknet
./scripts/bootstrap.sh
```

This runs: `npm install` → `npm run build` → `npm run typecheck`

## Environment Variables

Create a `.env` file at `starknet/.env`:

```env
# Required for Medialane reads
MEDIALANE_API_KEY=your_medialane_api_key

# Optional: starknet RPC override
STARKNET_RPC=https://starknet-sepolia.infura.io/v3/YOUR_INFURA_KEY
```

## Running the Demo

```bash
cd apps/demo
MEDIALANE_API_KEY=your_key node server.js
# Open http://localhost:3000
```

## Running Tests

```bash
npm test
```

## Building

```bash
npm run build       # Build all packages
npm run typecheck   # TypeScript check only
npm run clean       # Clean build artifacts
```

## Project Structure

```
starknet/
├── packages/
│   ├── core/              # Shared types
│   ├── venue-core/        # VenueAdapter interface
│   ├── venue-medialane/   # Medialane adapter
│   ├── venue-ark/         # Ark adapter
│   ├── opensea-adapter/   # OpenSea SDK adapter
│   ├── wallet/            # Wallet connection
│   ├── indexer/           # NFT indexer
│   ├── auth/              # SNIP-12 auth
│   └── reference-server/  # Demo HTTP server
├── apps/
│   └── demo/              # Demo HTML + server
├── docs/                  # Documentation
├── scripts/               # Build scripts
└── patches/
    └── opensea-sdk/       # OpenSea SDK patches
```

## Common Issues

### `Cannot find module '@storm/...'`

Run `npm install` from the `starknet/` root to ensure workspace links are set up.

### Wallet not connecting

Ensure your browser wallet is installed and unlocked. Refresh the page and try again.

### Transaction failing with "insufficient funds"

You need Sepolia ETH for gas. Use a faucet to get funds.

### Medialane API errors

Verify your `MEDIALANE_API_KEY` is correct and has not expired.
