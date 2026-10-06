# RFC: OpenSea Starknet Account Authentication

**Goal**: Define how OpenSea would add Starknet account authentication using SNIP-12.

## Current OpenSea Auth (EVM)

OpenSea uses EIP-712 signed messages for account authentication:

1. User signs an EIP-712 challenge with their wallet (ethers/Metamask)
2. Client sends the signature to OpenSea backend
3. Backend verifies against the user's connected address
4. Session is established

The EIP-712 challenge schema includes:
```ts
{
  domain: { chainId, name, version, verifyingContract }
  types: { Person: [{name, type}], Mail: [{name, type}], ... }
  value: { from: { name, wallet }, contents: string }
  primaryType: 'Mail'
}
```

## Proposed Starknet Extension

### SNIP-12 Overview

SNIP-12 (Starknet Signed Typed Data) is Starknet's equivalent of EIP-712:

- Uses `felt` types instead of EVM types (`address` → `felt`, `uint256` → `Uint256`)
- Domain struct includes `name`, `version`, `chain_id`, `verifying_contract`
- Signing is performed via `starknet.account.signMessage()`

### Challenge Schema (SNIP-12)

```ts
{
  domain: {
    name: "OpenSea",
    version: "1",
    chain_id: "0x534e5f4d41494e",  // Starknet mainnet (SN IP)
    verifying_contract: "0x..."    // OpenSea's Starknet verifier contract
  },
  types: {
    StarknetDomain: [
      { name: "name", type: "felt" },
      { name: "version", type: "felt" },
      { name: "chain_id", type: "felt" },
      { name: "verifying_contract", type: "felt" }
    ],
    Main: [
      { name: "address", type: "felt" },
      { name: "nonce", type: "felt" }
    ]
  },
  primaryType: "Main",
  message: {
    address: "0x1234...",  // user's Starknet address
    nonce: "0x1"          // anti-replay nonce
  }
}
```

### Nonce Management

- Each Starknet account maintains a nonce in the challenge to prevent replay attacks
- Backend tracks `last_auth_nonce` per Starknet address
- Nonce is incremented on each successful authentication
- Nonce overflow (wrapping to 0) should trigger a new session

### Signature Verification

Backend verification (pseudocode):

```python
def verify_starknet_signature(challenge, signature, address):
    # 1. Split signature into r,s (Starknet uses r, s as felts)
    r, s = split(signature)
    
    # 2. Verify using Starknet verifier contract or library
    # Uses Starknet's pedersen hash + StarkNet.js verify()
    is_valid = starknet_verify(
        challenge=challenge,
        signature=[r, s],
        address=address
    )
    
    # 3. Check nonce
    expected_nonce = get_expected_nonce(address)
    assert challenge.message.nonce == expected_nonce
    
    # 4. Create session
    create_session(address=address, nonce=expected_nonce + 1)
```

### Chain ID Handling

Starknet chain IDs (felt):
- Mainnet: `0x534e5f4d41494e` ("SN MAIN")
- Testnet: `0x534e5f4d474f45524c` ("SN GOERLI")
- Sepolia: `0x534e5f5345504f4c4941` ("SN SEPOLIA")

Backend must validate the `chain_id` in the domain matches the expected chain.

### Backend Changes Required

1. **New auth endpoint** `POST /v2/starknet/auth/challenge`
   - Input: `{ address: string }`
   - Output: `{ challenge: SNIP12Challenge, nonce: string }`

2. **New verify endpoint** `POST /v2/starknet/auth/verify`
   - Input: `{ address, signature: string, challenge: SNIP12Challenge }`
   - Output: `{ session_token: string }` or `401`

3. **Nonce storage** — Redis or DB table keyed by Starknet address

4. **SNIP-12 verifier** — Library or on-chain contract to verify signatures

5. **Session management** — Existing OpenSea session infrastructure extended

### What Works Today

- `starknet.account.signMessage()` produces valid SNIP-12 signatures ✓
- starknet.js `verifyMessage()` can verify signatures client-side ✓
- The `@storm/auth` package can issue and validate challenges locally ✓

### What Requires OpenSea Backend

- Public `/auth/challenge` endpoint with SNIP-12 challenges
- Persistent nonce tracking per Starknet address
- On-chain or off-chain SNIP-12 verification
- Session token issuance

### Client Integration

```ts
// Client-side (browser with get-starknet)
import { connectWallet } from '@storm/wallet'
import { signSNIP12Challenge } from '@storm/auth'

const { account } = await connectWallet()

// Get challenge from OpenSea
const { challenge, nonce } = await fetch('/v2/starknet/auth/challenge', {
  method: 'POST',
  body: JSON.stringify({ address: account.address })
}).then(r => r.json())

// Sign the challenge
const signature = await signSNIP12Challenge(account, challenge)

// Verify with OpenSea
const { session_token } = await fetch('/v2/starknet/auth/verify', {
  method: 'POST',
  body: JSON.stringify({ address: account.address, signature, challenge, nonce })
}).then(r => r.json())
```
