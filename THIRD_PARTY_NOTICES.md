# Third-Party Notices

This project uses the following open-source components.

## Direct Dependencies

| Package | Version | License | Notes |
|---|---|---|---|
| starknet.js | ^10.8.0 | MIT | Starknet JavaScript SDK |
| @starknet-io/get-starknet | ^4.0.8 | MIT | Starknet wallet discovery |
| @ark-project/core | ^2.1.2 | MIT | Ark Project SDK |
| typescript | ^5.6.0 | Apache-2.0 | TypeScript compiler |
| @types/node | ^22.0.0 | MIT | Node.js type definitions |

## OpenSea SDK (Reference Only)

This project references the public OpenSea SDK (`@opensea/sdk`) for interface analysis and patch documentation.

- Repository: https://github.com/ProjectOpenSea/opensea-js
- Commit: `304a76bc` (v12.11.2)
- License: Apache-2.0
- Usage: Reference for `OpenSeaSigner`, `OpenSeaProvider`, `OpenSeaWallet` interface shapes; patch documentation in `patches/opensea-sdk/`

## OpenZeppelin Cairo Contracts (Reference Only)

OZ Cairo contract interfaces are referenced for SRC5/ERC721/ERC1155 interface ID constants.

- Repository: https://github.com/OpenZeppelin/cairo-contracts
- License: MIT
- Usage: Interface ID constants (`SRC5_ID`, `IERC721_ID`, etc.) in `@storm/core`

## Starknet Network

Starknet is a decentralized Validity Rollup. The Starknet network and its testnets are public infrastructure.

- Starknet: https://starknet.io
- Sepolia testnet: `0x534e5f5345504f4c4941`
- Mainnet: `0x534e5f4d41494e`

## Medialane

Medialane is a Starknet-native NFT marketplace protocol.

- API: https://api.medialane.io
- SDK: https://github.com/medialane-io/medialane-sdk
- License: See respective repositories

## Ark Project

Ark Project is a Starknet-native exchange protocol.

- Repository: https://github.com/ArkProjectNFTs/ark-project
- License: MIT (see repository)

## SNIP-12

SNIP-12 is a Starknet standard for typed data signing.

- Specification: https://github.com/starknet-io/SNIP-12

## Notes

- This kit is an integration reference implementation, not affiliated with OpenSea, StarkWare, Medialane, or Ark Project.
- Contract addresses and interface IDs are verified against on-chain state.
- This kit does not modify or redistribute any proprietary code.
