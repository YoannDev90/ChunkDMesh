"""Client-side benchmark: generates a small zone to measure chunk generation speed."""

import httpx
import time
from typing import Optional


class BenchmarkRunner:
    def __init__(self, server_url: str, token: str):
        self.server_url = server_url.rstrip("/")
        self.token = token
        self.headers = {"Authorization": f"Bearer {token}"}

    def run(
        self,
        java_bin: str,
        server_jar: str,
        server_dir: str,
        radius: int = 2,
        dimension: str = "overworld",
        seed: int = 12345,
    ) -> dict:
        import subprocess
        import os

        print(f"Running benchmark: radius={radius}, seed={seed}")

        cmd = [
            java_bin,
            "-Xmx2G",
            "-Xms512M",
            "-jar", server_jar,
            "nogui",
        ]

        start_time = time.time()
        proc = subprocess.Popen(
            cmd,
            cwd=server_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        ready = False
        lines = []
        for line in iter(proc.stdout.readline, ""):
            line = line.rstrip()
            lines.append(line)
            if "Done" in line or "RCON listener started" in line:
                ready = True
                break
            if proc.poll() is not None:
                break

        if not ready:
            proc.kill()
            raise RuntimeError("Server did not start for benchmark")

        ready_time = time.time() - start_time
        print(f"  Server ready in {ready_time:.1f}s")

        rcon_port = 25575
        rcon_password = "chunkdmesh"

        try:
            from rcon_client import RCONConnection
            rcon = RCONConnection("127.0.0.1", port=rcon_port, password=rcon_password)
            if not rcon.connect(retries=10, delay=2.0):
                print("  RCON connection failed")
                return
            rcon.run("chunky", "start", dimension, "0", "0", str(radius))

            gen_start = time.time()
            time.sleep(1)
            while True:
                resp = rcon.run("chunky progress")
                if "not running" in resp.lower() or "done" in resp.lower():
                    break
                time.sleep(0.5)
                elapsed = time.time() - gen_start
                if elapsed > 120:
                    rcon.run("chunky cancel")
                    break

            gen_duration = time.time() - gen_start
            total_chunks = (radius * 2 + 1) ** 2
            chunks_per_second = total_chunks / gen_duration if gen_duration > 0 else 0

        except Exception as e:
            print(f"  Benchmark failed: {e}")
            chunks_per_second = 0
            gen_duration = 0
            total_chunks = 0
        finally:
            proc.stdin.write("stop\n")
            proc.stdin.flush()
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()

        result = {
            "chunks_per_second": round(chunks_per_second, 2),
            "duration_seconds": round(gen_duration, 2),
            "chunks_generated": total_chunks,
        }
        print(f"  Result: {chunks_per_second:.1f} chunks/s ({total_chunks} in {gen_duration:.1f}s)")
        return result

    def submit(self, result: dict) -> dict:
        with httpx.Client(follow_redirects=True, timeout=30) as client:
            resp = client.post(
                f"{self.server_url}/benchmark",
                json=result,
                headers=self.headers,
            )
            resp.raise_for_status()
            return resp.json()
