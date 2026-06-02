import asyncio
import os
from pathlib import Path

import pytest

from webchat.cannex_chat.agent.worker_client import WorkerClient

CANNEX_ROOT = str(Path(__file__).resolve().parents[3])


@pytest.fixture
def env():
    e = os.environ.copy()
    e["CANNEX_ROOT"] = CANNEX_ROOT
    return e


@pytest.mark.asyncio
async def test_call_ping(env):
    client = WorkerClient(env=env)
    await client.start()
    try:
        result = await client.call("ping", {})
        assert result == "pong"
    finally:
        await client.stop()


@pytest.mark.asyncio
async def test_call_list_resources(env):
    client = WorkerClient(env=env)
    await client.start()
    try:
        result = await client.call("list_known_resources", {})
        assert "docs" in result and "repos" in result
    finally:
        await client.stop()


@pytest.mark.asyncio
async def test_auto_restart_on_crash(env):
    client = WorkerClient(env=env)
    await client.start()
    try:
        # kill the worker process
        client._proc.kill()
        await asyncio.sleep(0.5)
        # next call should auto-restart and retry
        result = await client.call("ping", {})
        assert result == "pong"
    finally:
        await client.stop()


@pytest.mark.asyncio
async def test_error_response_propagated(env):
    client = WorkerClient(env=env)
    await client.start()
    try:
        with pytest.raises(RuntimeError) as exc:
            await client.call("nonexistent_method", {})
        assert "UnknownMethod" in str(exc.value)
    finally:
        await client.stop()
