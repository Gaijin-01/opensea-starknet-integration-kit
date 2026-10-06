# OpenSea × Starknet Integration Kit

[![CI](https://github.com/Gaijin-01/opensea-starknet-integration-kit/actions/workflows/ci.yml/badge.svg)](https://github.com/Gaijin-01/opensea-starknet-integration-kit/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.x-blue)](https://www.typescriptlang.org/)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-blue)](https://www.python.org/)

An unofficial open-source reference implementation for adding native Starknet NFT support to OpenSea-style marketplace infrastructure.

**This project is a community reference implementation. It is not affiliated with or endorsed by OpenSea, StarkWare, or the Starknet Foundation.**

---

## Why This Exists

Building NFT marketplaces on Starknet requires integrating venue adapters (Medialane, Ark), indexers, wallet connections, SNIP-12 authentication, and OpenSea API compatibility. This kit provides working reference implementations for each layer, allowing teams to integrate Starknet support without starting from Cairo.

## What This Is

- **Venue adapters** for Medialane and Ark Project (on-chain NFT marketplaces on Starknet)
- **Reference server** with SNIP-12 authentication middleware
- **TypeScript browser SDK** for wallet connection and order management
- **Python indexer** for ERC-721 and ERC-1155 transfer events
- **End-to-end test suite** with real Starknet Sepolia RPC
- **Upstream integration reference** for the OpenSea SDK

## What This Is NOT

- An OpenSea product or plugin
- A production-ready deployed service
- A complete orderbook or matching engine
- A Starknet wallet (uses existing browser wallets)
- An endorsement of any specific venue protocol

---

## Architecture

```mermaid
graph LR
    subgraph Browser
        W[Wallet]
        S[Storefront UI]
    end

    subgraph TypeScript Packages
        WA[@storm/wallet]
        VC[@storm/venue-core]
        VA[@storm/venue-ark]
        VM[@storm/venue-medialane]
        OA[@storm/opensea-adapter]
    end

    subgraph Python Suite ["starknet/"]
        IX[indexer/]
        SN[snip12/]
        EX[execution/]
        SC[standards/]
    end

    subgraph Reference Server
        RS[Reference Server]
    end

    W --> WA
    S --> WA
    S --> VC
    WA --> RS
    S --> OA
    OA --> VA
    OA --> VM
    VA --> EX
    VM --> EX
    EX --> IX
    IX --> SN
    SN --> SC
```

---

## Quick Start

### Prerequisites

- Node.js 20+
- Python 3.10+
- A Starknet Sepolia RPC endpoint (e.g., Infura)
- Optional: Medialane API key for Medialane venue

### Installation

```bash
git clone https://github.com/Gaijin-01/opensea-starknet-integration-kit.git
cd opensea-starknet-integration-kit

npm install
npm run build
npm run typecheck
```

### Python Tests

```bash
cd starknet
python3 -m pytest tests/ -q
```

### Configuration

```bash
cp .env.example .env
```

Required: `STARKNET_RPC` — Starknet RPC URL (Sepolia recommended).

### Reference Server

```bash
cd packages/reference-server && npm install && npm run dev
# http://localhost:3001
```

### Demo Storefront

```bash
cd apps/demo && npm install && npm run dev
# http://localhost:5174
```

---

## Package Overview

### TypeScript Packages (`packages/`)

| Package | Description |
|---------|-------------|
| `@storm/wallet` | Browser wallet connection (Argent X, Braavos, Cartridge, etc.) |
| `@storm/venue-core` | Core venue adapter interfaces and types |
| `@storm/venue-ark` | Ark Project venue adapter for on-chain NFT marketplace |
| `@storm/venue-medialane` | Medialane venue adapter for hybrid marketplace |
| `@storm/opensea-adapter` | OpenSea API-compatible adapter layer |
| `@storm/indexer` | TypeScript indexer utilities for NFT ownership |
| `@storm/reference-server` | Reference fulfillment server with SNIP-12 auth |
| `@storm/auth` | SNIP-12 typed data signing utilities |
| `@storm/core` | Core types and utilities |

### Python Suite (`starknet/`)

| Module | Description |
|--------|-------------|
| `starknet/rpc/` | Starknet RPC client (read-only) |
| `starknet/indexer/` | ERC-721/ERC-1155 transfer event indexer |
| `starknet/execution/` | Trading flow execution (fulfill, cancel) |
| `starknet/snip12/` | SNIP-12 domain and verifier implementation |
| `starknet/standards/` | ERC-721, ERC-1155, SRC-5 interfaces |
| `starknet/security/` | Venue security (nonce replay, executor validation) |
| `starknet/normalization/` | Order normalization and validation |
| `starknet/wallets/` | Wallet adapter definitions |

---

## Supported Starknet Capabilities

### Wallet Connection
- Argent X, Argent Mobile, Braavos, Cartridge, Xverse, MetaMask Snap
- Via `window.starknet` (Starknet Window Object)

### Venue Adapters
- **Medialane** — Hybrid marketplace (REST API + on-chain intents)
- **Ark Project** — Fully on-chain marketplace (on-chain orderbook)

### Token Standards
- ERC-721 (NFT)
- ERC-1155 (Multi-Token)
- SRC-5 (Interface detection)

### Authentication
- SNIP-12 (Starknet Identity standard) — Reference server middleware

### Indexing
- Transfer event watching via Starknet RPC
- ERC-721 and ERC-1155 support
- Ownership mapping

---

## Implementation Status

| Component | Status | Notes |
|-----------|--------|-------|
| Wallet connection | ✅ Implemented | V6 API, all major wallets |
| Medialane venue | ✅ Implemented | REST API adapter |
| Ark venue | ✅ Implemented | On-chain orderbook adapter |
| Reference server | ✅ Implemented | SNIP-12 middleware, REST endpoints |
| Python indexer | ✅ Implemented | Transfer events, ERC-721/ERC-1155 |
| SNIP-12 verifier | ✅ Implemented | Reference implementation |
| OpenSea adapter | ✅ Implemented | API-compatible layer |
| Python test suite | ✅ 148 passed | Starknet Sepolia RPC |
| Live E2E tests | ⚠️ Partial | Requires Medialane API key |
| Production SNIP-12 crypto | ⚠️ Reference only | See SECURITY.md |

---

## OpenSea Integration Boundary

This kit provides the **Starknet-side** infrastructure for an OpenSea-style marketplace. Integration with OpenSea's backend requires:

1. Using this kit's reference server as a fulfillment backend
2. Adapting OpenSea's frontend SDK via the `@storm/opensea-adapter`
3. Coordinating with OpenSea for order listing and settlement

**This kit does not require OpenSea's approval to use.** It implements open standards (SNIP-12, ERC-721, ERC-1155) and documented venue protocols.

---

## Documentation

| Guide | Description |
|-------|-------------|
| `docs/LOCAL_DEVELOPMENT.md` | Setup and configuration |
| `docs/ARCHITECTURE.md` | System architecture overview |
| `docs/WALLET_INTEGRATION.md` | Browser wallet integration |
| `docs/ARK.md` | Ark Project venue adapter |
| `docs/MEDIALANE.md` | Medialane venue adapter |
| `docs/STARKNET_INDEXING.md` | Indexer design |
| `docs/LIMITATIONS.md` | Known limitations |
| `references/opensea-starknet-adapter/` | OpenSea SDK integration reference |
| `SECURITY.md` | Security model and reporting |

---

## Security

See [SECURITY.md](SECURITY.md) for:
- Vulnerability reporting process
- Reference implementation disclaimers
- Production hardening requirements

**Key:** Never deploy with real private keys or production API keys in environment variables. Always validate on-chain state before fulfillment.

---

## Contributing

Contributions are welcome. See [SECURITY.md](SECURITY.md) before opening issues.

---

## License

MIT License. See [LICENSE](LICENSE) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for third-party attribution requirements.
