# Security Policy

**This project is an unofficial open-source reference implementation. It is not affiliated with or endorsed by OpenSea.**

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

## Reporting a Vulnerability

If you discover a security vulnerability, please report it responsibly.

### How to Report

1. **Do not** open a public GitHub issue for security vulnerabilities.
2. Email the maintainer directly at the GitHub profile contact URL.
3. Include:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)

### What to Expect

- Acknowledgment within 48 hours
- Regular updates on progress
- Credit in the security advisory (if desired)

## Security Model

### Reference Implementation Disclaimer

This is a **reference implementation** for educational and integration purposes. The following are NOT included in this kit and must be added before production use:

- **SNIP-12 signature verification** — The `requireWalletSignature` middleware in the reference server performs header-level identity checks only. Production deployments must implement actual SNIP-12 cryptographic signature verification.
- **Rate limiting** — The reference server does not implement rate limiting.
- **Input sanitization** — All inputs should be validated and sanitized before on-chain use.
- **Admin keys** — Never deploy with real account private keys or production API keys in environment variables.
- **TLS** — Always serve the reference server over HTTPS in production.

### On-Chain Considerations

- Always validate executable state against the latest chain state before fulfillment.
- Use nonce replay protection for all transactions.
- Verify contract addresses are deployed and correct before use.
- Test thoroughly on Starknet Sepolia before mainnet deployment.
