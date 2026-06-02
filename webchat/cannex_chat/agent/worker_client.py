"""
持久 Worker 客户端：spawn 一个 worker/server.py 子进程，通过 JSON Lines 通信。
崩溃自动重启 + 单次请求重试 1 次。
"""
import asyncio
import json
import logging
import os
import sys
import uuid
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

WORKER_SCRIPT = Path(__file__).resolve().parents[1] / "worker" / "server.py"


class WorkerClient:
    """Manages a persistent worker subprocess and communicates via JSON Lines RPC."""

    def __init__(self, env: dict | None = None, timeout: float = 60.0):
        # 透传足够多的环境变量，确保 worker subprocess 能找到 codegraph CLI
        # （npm 全局 bin 可能在 /usr/local/bin、~/.nvm/versions/node/xxx/bin 等）
        _passthrough = {
            "CANNEX_ROOT", "PATH", "HOME", "USER", "SHELL",
            "NVM_DIR", "NVM_BIN", "NODE_PATH", "npm_config_prefix",
            "LANG", "LC_ALL",
        }
        self._env = env or {
            k: v for k, v in os.environ.items() if k in _passthrough
        }
        self._timeout = timeout
        self._proc: asyncio.subprocess.Process | None = None
        self._lock = asyncio.Lock()
        self._pending: dict[str, asyncio.Future] = {}
        self._reader_task: asyncio.Task | None = None

    async def start(self):
        """Start the worker subprocess if not already running."""
        if self._proc and self._proc.returncode is None:
            return
        self._proc = await asyncio.create_subprocess_exec(
            sys.executable, str(WORKER_SCRIPT),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=16 * 1024 * 1024,  # 16 MB，防大 JSON 响应超默认 64KB 限制
            env=self._env,
        )
        self._pending = {}
        self._reader_task = asyncio.create_task(self._reader_loop())
        log.info("Worker started pid=%s", self._proc.pid)

    async def stop(self):
        """Stop the worker subprocess and clean up resources."""
        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()
            try:
                await asyncio.wait_for(self._reader_task, timeout=1.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass
        if self._proc and self._proc.returncode is None:
            self._proc.terminate()
            try:
                await asyncio.wait_for(self._proc.wait(), timeout=2)
            except asyncio.TimeoutError:
                self._proc.kill()
                await self._proc.wait()
        self._proc = None

    async def _reader_loop(self):
        """Read JSON Lines responses from the worker stdout and dispatch to futures."""
        try:
            while self._proc and self._proc.stdout:
                line = await self._proc.stdout.readline()
                if not line:
                    break
                try:
                    msg = json.loads(line.decode())
                except json.JSONDecodeError:
                    log.warning("Worker emitted invalid JSON: %r", line)
                    continue
                rid = msg.get("id")
                fut = self._pending.pop(rid, None)
                if fut and not fut.done():
                    fut.set_result(msg)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            log.warning("Reader loop error: %s", e)
        # Process exited: fail all pending requests
        for fut in list(self._pending.values()):
            if not fut.done():
                fut.set_exception(ConnectionError("Worker process exited"))
        self._pending.clear()

    async def _call_once(self, method: str, params: dict) -> Any:
        """Send a single RPC call to the worker; start worker if not running."""
        if not self._proc or self._proc.returncode is not None:
            await self.start()
        rid = uuid.uuid4().hex
        loop = asyncio.get_event_loop()
        fut: asyncio.Future = loop.create_future()
        self._pending[rid] = fut
        req = json.dumps(
            {"id": rid, "method": method, "params": params},
            ensure_ascii=False,
        ) + "\n"
        async with self._lock:
            self._proc.stdin.write(req.encode())
            await self._proc.stdin.drain()
        try:
            msg = await asyncio.wait_for(fut, timeout=self._timeout)
        except asyncio.TimeoutError:
            self._pending.pop(rid, None)
            raise TimeoutError(
                f"Worker call '{method}' timed out after {self._timeout}s"
            )
        if msg["ok"]:
            return msg["result"]
        err = msg["error"]
        raise RuntimeError(f"{err['type']}: {err['message']}")

    async def call(self, method: str, params: dict) -> Any:
        """Call a method on the worker; retries once on ConnectionError/BrokenPipeError."""
        try:
            return await self._call_once(method, params)
        except (ConnectionError, BrokenPipeError) as e:
            log.warning(
                "Worker call '%s' failed (%s), restarting and retrying once",
                method,
                e,
            )
            await self.stop()
            await self.start()
            return await self._call_once(method, params)
