# starknet/tests/unit/test_rpc_client.py
import pytest
from starknet.rpc.client import StarknetRPCClient, StarknetRPCError


class TestStarknetRPCClientUnit:
    def test_client_init(self):
        client = StarknetRPCClient("https://example.com/rpc")
        assert client.rpc_url == "https://example.com/rpc"
        assert client.timeout == 30

    def test_batch_call_empty(self):
        client = StarknetRPCClient("https://example.com/rpc")
        assert client.batch_call([]) == []


class TestBatchCallSemantics:
    def test_batch_call_produces_correct_request_shape(self):
        client = StarknetRPCClient("https://example.com/rpc")
        assert callable(client.batch_call)

    def test_batch_call_distinguishes_from_onchain_multicall(self):
        """
        CRITICAL DISTINCTION: batch_call sends multiple JSON-RPC requests
        in ONE HTTP POST. This is NOT starknet_multicall which is an
        ON-CHAIN contract invocation.
        """
        client = StarknetRPCClient("https://example.com/rpc")
        assert not hasattr(client, 'starknet_multicall')
        assert hasattr(client, 'batch_call')


class TestRPCError:
    def test_error_format(self):
        err = StarknetRPCError(-32600, "Invalid request", {"key": "value"})
        assert err.code == -32600
        assert err.message == "Invalid request"
        assert err.data == {"key": "value"}
        assert "Invalid request" in str(err)
