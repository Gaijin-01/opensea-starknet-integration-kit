# starknet/rpc/client.py
"""
Starknet JSON-RPC client (pure stdlib, no external deps).

KEY DESIGN POINTS:
- JSON-RPC batch requests are client-side HTTP multiplexing, NOT a native
  starknet_multicall RPC method. The client sends multiple JSON-RPC request
  objects in a single HTTP POST and receives a single JSON-RPC response array.
- On-chain multicall is a separate deployed-contract mechanism.
- Spec version is negotiated at runtime via starknet_specVersion, not hardcoded.
"""

import json
import urllib.request
import urllib.error
from typing import Any


class StarknetRPCError(Exception):
    def __init__(self, code: int, message: str, data: Any = None):
        self.code = code
        self.message = message
        self.data = data
        super().__init__(f"RPC error {code}: {message}")


class StarknetRPCClient:
    def __init__(self, rpc_url: str, timeout: int = 30):
        self.rpc_url = rpc_url
        self.timeout = timeout

    def _post(self, request: dict) -> dict:
        """Send a single JSON-RPC request."""
        body = json.dumps(request).encode("utf-8")
        req = urllib.request.Request(
            self.rpc_url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as e:
            raise StarknetRPCError(-1, f"Connection error: {e}") from e

        if "error" in data:
            err = data["error"]
            raise StarknetRPCError(
                err.get("code", -1),
                err.get("message", "Unknown error"),
                err.get("data"),
            )
        return data

    def call(self, method: str, params: list) -> Any:
        """Single JSON-RPC call."""
        result = self._post({
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": 1,
        })
        return result.get("result")

    def batch_call(self, calls: list[dict]) -> list[Any]:
        """
        Send multiple JSON-RPC calls in a single HTTP POST.

        Each call in `calls` is a dict: {"method": str, "params": list, "id": int}

        This is CLIENT-SIDE batching: multiple request objects in one HTTP POST.
        The server processes them and returns a JSON array of results.

        IMPORTANT: This is NOT the same as a native starknet_multicall RPC method
        (which is an on-chain multicall contract invocation).
        """
        if not calls:
            return []

        requests = []
        for i, call in enumerate(calls):
            requests.append({
                "jsonrpc": "2.0",
                "method": call["method"],
                "params": call.get("params", []),
                "id": i + 1,
            })

        body = json.dumps(requests).encode("utf-8")
        req = urllib.request.Request(
            self.rpc_url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                responses = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as e:
            raise StarknetRPCError(-1, f"Batch connection error: {e}") from e

        if not isinstance(responses, list):
            raise StarknetRPCError(-1, f"Expected batch response list, got {type(responses)}")

        results = [None] * len(calls)
        for resp in responses:
            rid = resp.get("id", 0) - 1
            if "error" in resp:
                err = resp["error"]
                results[rid] = StarknetRPCError(
                    err.get("code", -1),
                    err.get("message", "Unknown error"),
                    err.get("data"),
                )
            else:
                results[rid] = resp.get("result")
        return results

    # Convenience methods
    def get_block_number(self) -> int:
        return self.call("starknet_blockNumber", [])

    def get_chain_id(self) -> str:
        return self.call("starknet_chainId", [])

    def get_spec_version(self) -> str:
        return self.call("starknet_specVersion", [])

    def get_class_hash_at(self, address: str, block_identifier: str | int | None = None) -> str:
        params = [address]
        if block_identifier is not None:
            params.append(block_identifier)
        else:
            params.append("latest")
        return self.call("starknet_getClassHashAt", params)

    def call_contract(
        self,
        address: str,
        entry_point_selector: str,
        calldata: list[str] | None = None,
        block_identifier: str | int | None = None,
    ) -> dict:
        """Call a contract function (read-only)."""
        call = {
            "contract_address": address,
            "entry_point_selector": entry_point_selector,
        }
        if calldata:
            call["calldata"] = calldata
        params = [call]
        if block_identifier is not None:
            params.append(block_identifier)
        else:
            params.append("latest")
        return self.call("starknet_call", params)

    def supports_interface(self, address: str, interface_id: int) -> bool:
        """
        Check if a contract supports a given SRC5 interface ID.

        This calls the SRC5 supports_interface entry point.
        Returns False if the contract does not exist, has no such entry point,
        or returns false — without raising an RPC error.
        """
        selector = "0x3f918d17e5ee77373b56385708f855659a07f75997f365cf87748628532a055"
        try:
            result = self.call_contract(address, selector, [hex(interface_id)])
            if result and "return_data" in result and result["return_data"]:
                return bool(int(result["return_data"][0]))
        except StarknetRPCError as e:
            # Error code 20 = Contract not found, 21 = Entrypoint not found
            # Both mean "not supported" — return False gracefully
            if e.code in (20, 21):
                return False
            raise
        return False

    def get_events(
        self,
        keys: list[list[str]] | None = None,
        from_block: int = 0,
        to_block: int | str = "latest",
        address: str | None = None,
        size: int = 1000,
        continuation_token: str | None = None,
    ) -> dict:
        """
        Get events via starknet_getEvents.

        Per Starknet RPC spec 0.9.0: params is a flat object, not wrapped in "filter".

        Returns: {"events": [...], "continuation_token": str|None}
        """
        filter_obj: dict[str, Any] = {
            "from_block": {"block_number": from_block},
            "to_block": {"block_number": to_block} if isinstance(to_block, int) else {"block_number": to_block},
            "chunk_size": size,
        }
        if keys:
            filter_obj["keys"] = keys
        if address:
            filter_obj["address"] = address
        if continuation_token:
            filter_obj["continuation_token"] = continuation_token

        result = self.call("starknet_getEvents", [filter_obj])
        return result or {"events": []}
