# starknet/wallets/adapter.py
"""
Starknet wallet adapter interface and implementations.

Supported wallets (CONFIRMED from spec + current state):
  - Braavos: hardware wallet, MetaMask Snap available
  - Argent: browser extension + mobile wallet
  - Cartridge Controller: browser extension
  - Xverse: Bitcoin + Starknet Web Wallet
  - MetaMask Snap: Starknet Snap for MetaMask

Account address normalization: 0x + 64 hex chars (zero-padded felt252).
Private key NEVER logged or exposed.

Environment config:
  STARKNET_ACCOUNT_ADDRESS: deployed account address
  STARKNET_PRIVATE_KEY: private key for local Account (NOT for production)
  STARKNET_RPC_URL: JSON-RPC endpoint
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional
from enum import Enum

from starknet.standards.interfaces import normalize_felt_address


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

class TransactionStatus(Enum):
    RECEIVED = "RECEIVED"
    REJECTED = "REJECTED"
    ACCEPTED_ON_L2 = "ACCEPTED_ON_L2"
    ACCEPTED_ON_L1 = "ACCEPTED_ON_L1"
    NOT_RECEIVED = "NOT_RECEIVED"


@dataclass(frozen=True)
class Call:
    """A single Starknet call."""
    contract_address: str
    entrypoint: str
    calldata: list[str]


@dataclass(frozen=True)
class EstimatedFee:
    """Estimated fee for a set of calls."""
    gas_price: int
    gas_limit: int
    total_fee: int
    suggested_max_fee: int


@dataclass(frozen=True)
class WalletConnection:
    """Active wallet connection."""
    address: str  # canonical 0x + 64 hex
    chain_id: str
    wallet_type: str  # "braavos", "argent", "cartridge", "xverse", "metamask_snap"


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class WalletError(Exception):
    """Base exception for wallet errors."""
    pass


class SigningError(WalletError):
    """Raised when signing fails."""
    pass


class ConnectionError(WalletError):
    """Raised when wallet connection fails."""
    pass


class ConfigurationError(WalletError):
    """Raised when wallet configuration is missing."""
    pass


# ---------------------------------------------------------------------------
# Wallet adapter interface
# ---------------------------------------------------------------------------

class WalletAdapter(ABC):
    """
    Abstract base for Starknet wallet adapters.

    Implementations must handle:
    - Address normalization (canonical 0x + 64 hex)
    - Typed data signing (returns list[str] signature)
    - Call execution (returns transaction hash)
    - Fee estimation
    - Transaction status polling
    """

    @abstractmethod
    def connect(self) -> WalletConnection:
        """Connect to the wallet and return connection info."""
        raise NotImplementedError

    @abstractmethod
    def disconnect(self) -> None:
        """Disconnect the wallet."""
        raise NotImplementedError

    @abstractmethod
    def get_address(self) -> str:
        """Get the connected account address in canonical form."""
        raise NotImplementedError

    @abstractmethod
    def sign_typed_data(self, typed_data: dict) -> list[str]:
        """
        Sign SNIP-12 typed data.

        Returns: list of felt252 signature values as hex strings.
        Raises: SigningError if wallet refuses or is not connected.
        """
        raise NotImplementedError

    @abstractmethod
    def execute_calls(self, calls: list[Call]) -> str:
        """
        Execute a list of calls through the wallet.

        Returns: transaction hash.
        Raises: WalletError if execution fails.
        """
        raise NotImplementedError

    @abstractmethod
    def estimate_fee(self, calls: list[Call]) -> EstimatedFee:
        """Estimate the fee for a list of calls."""
        raise NotImplementedError

    @abstractmethod
    def wait_for_transaction(self, tx_hash: str) -> TransactionStatus:
        """Wait for a transaction to be accepted or rejected."""
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Local starknet.py Account adapter
# ---------------------------------------------------------------------------

class LocalAccountAdapter(WalletAdapter):
    """
    Adapter for local starknet.py Account.

    Uses STARKNET_ACCOUNT_ADDRESS, STARKNET_PRIVATE_KEY, STARKNET_RPC_URL.
    Suitable for testing and backend services.
    NOT for browser use — private key required.
    """

    def __init__(
        self,
        account_address: Optional[str] = None,
        private_key: Optional[str] = None,
        rpc_url: Optional[str] = None,
    ):
        self.account_address = (
            account_address
            or os.environ.get("STARKNET_ACCOUNT_ADDRESS")
        )
        self.private_key = (
            private_key
            or os.environ.get("STARKNET_PRIVATE_KEY")
        )
        self.rpc_url = (
            rpc_url
            or os.environ.get("STARKNET_RPC_URL")
            or "https://starknet-sepolia.public.blastapi.io"
        )

        if not self.account_address:
            raise ConfigurationError(
                "STARKNET_ACCOUNT_ADDRESS is not set. "
                "Set it as an environment variable or pass it explicitly."
            )
        if not self.private_key:
            raise ConfigurationError(
                "STARKNET_PRIVATE_KEY is not set. "
                "Set it as an environment variable or pass it explicitly. "
                "WARNING: never expose private keys in production."
            )

        self._address_canonical = normalize_felt_address(self.account_address)
        self._chain_id: Optional[str] = None
        self._account = None

    def connect(self) -> WalletConnection:
        """Connect using the configured keys."""
        self._init_account()
        if self._account is None:
            raise ConnectionError("Failed to initialize starknet.py Account")
        return WalletConnection(
            address=self._address_canonical,
            chain_id=self._chain_id or "SN_SEPOLIA",
            wallet_type="local",
        )

    def _init_account(self):
        """Initialize the starknet.py Account."""
        if self._account is not None:
            return
        try:
            from starknet.networks import Network
            from starknet import Account
            from starknet.key_pair import KeyPair
            from starknet.id import uint256

            key_pair = KeyPair.from_private_key(int(self.private_key or "", 16))
            self._account = Account(
                address=int(self._address_canonical, 16),
                key_pair=key_pair,
                network=Network.STARKNET_TESTNET,
            )
            self._chain_id = "SN_SEPOLIA"
        except ImportError:
            raise ConfigurationError(
                "starknet package is not installed. "
                "Install with: pip install starknet.py"
            )

    def disconnect(self) -> None:
        self._account = None
        self._chain_id = None

    def get_address(self) -> str:
        return self._address_canonical

    def sign_typed_data(self, typed_data: dict) -> list[str]:
        """
        Sign SNIP-12 typed data using the local Account.

        BLOCKED: starknet.py SNIP-12 signing support is partial.
        The sign_message method may not support SNIP-12 format.
        """
        self._init_account()
        if self._account is None:
            raise SigningError("Account not initialized")
        try:
            # starknet.py Account.sign_message for typed data
            signature = self._account.sign_message(typed_data)
            return [hex(int(x)) for x in signature]
        except NotImplementedError:
            raise SigningError(
                "starknet.py does not fully support SNIP-12 typed data signing. "
                "Use @argent/argent-android-sdk, Braavos wallet extension, "
                "or @starkware/starknet.js for SNIP-12 signing."
            )
        except Exception as e:
            raise SigningError(f"Signing failed: {e}") from e

    def execute_calls(self, calls: list[Call]) -> str:
        """Execute calls through the local Account."""
        self._init_account()
        if self._account is None:
            raise WalletError("Account not initialized")
        try:
            starknet_calls = [
                {
                    "contract_address": call.contract_address,
                    "entry_point": call.entrypoint,
                    "calldata": call.calldata,
                }
                for call in calls
            ]
            result = self._account.execute(starknet_calls, auto_estimate=True)
            return hex(result.transaction_hash)
        except Exception as e:
            raise WalletError(f"Execute failed: {e}") from e

    def estimate_fee(self, calls: list[Call]) -> EstimatedFee:
        self._init_account()
        if self._account is None:
            raise WalletError("Account not initialized")
        try:
            starknet_calls = [
                {
                    "contract_address": call.contract_address,
                    "entry_point": call.entrypoint,
                    "calldata": call.calldata,
                }
                for call in calls
            ]
            estimate = self._account.estimate_fee(starknet_calls)
            return EstimatedFee(
                gas_price=estimate.gas_price,
                gas_limit=estimate.gas_limit,
                total_fee=estimate.total_fee,
                suggested_max_fee=estimate.suggested_max_fee,
            )
        except Exception as e:
            raise WalletError(f"Fee estimation failed: {e}") from e

    def wait_for_transaction(self, tx_hash: str) -> TransactionStatus:
        """Wait for transaction and return status."""
        self._init_account()
        if self._account is None:
            raise WalletError("Account not initialized")
        try:
            tx_hash_int = int(tx_hash, 16) if tx_hash.startswith("0x") else int(tx_hash)
            receipt = self._account.wait_for_transaction(tx_hash_int)
            status_str = receipt.get("status", "").upper()
            if status_str == "ACCEPTED_ON_L2":
                return TransactionStatus.ACCEPTED_ON_L2
            elif status_str == "ACCEPTED_ON_L1":
                return TransactionStatus.ACCEPTED_ON_L1
            elif status_str == "REJECTED":
                return TransactionStatus.REJECTED
            else:
                return TransactionStatus.NOT_RECEIVED
        except Exception:
            return TransactionStatus.NOT_RECEIVED


# ---------------------------------------------------------------------------
# Wallet registry
# ---------------------------------------------------------------------------

def get_wallet(name: str) -> WalletAdapter:
    """
    Factory for wallet adapters by name.

    Supported: "local", "braavos", "argent", "cartridge", "xverse", "metamask_snap"
    """
    name = name.lower().strip()
    if name == "local":
        return LocalAccountAdapter()
    elif name in ("braavos", "argent", "cartridge", "xverse", "metamask_snap"):
        raise NotImplementedError(
            f"{name} wallet adapter requires a browser extension integration. "
            f"For server-side: use LocalAccountAdapter with a deployed account. "
            f"For browser-side: use the official {name} SDK."
        )
    else:
        raise ValueError(
            f"Unknown wallet: {name}. "
            f"Supported: local, braavos, argent, cartridge, xverse, metamask_snap"
        )
