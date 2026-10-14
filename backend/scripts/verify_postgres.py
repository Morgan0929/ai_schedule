"""Run integration tests using a temporary, loopback-only PostgreSQL instance."""

import argparse
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--pg-bin", type=Path, required=True)
    args = parser.parse_args()
    project = Path(__file__).resolve().parents[2]
    suffix = ".exe" if os.name == "nt" else ""
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    with tempfile.TemporaryDirectory(prefix="codex-pg-tests-") as folder:
        root = Path(folder)
        data = root / "data"
        server_log = root / "postgres.log"
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        pg_ctl = str(args.pg_bin / f"pg_ctl{suffix}")

        def command(arguments):
            # A Windows daemon may inherit pipe handles and prevent communicate()
            # from seeing EOF after pg_ctl exits. A temporary file avoids that.
            with tempfile.NamedTemporaryFile(mode="w+b", dir=root, suffix=".log", delete=False) as output:
                result = subprocess.run(arguments, stdout=output, stderr=subprocess.STDOUT,
                                        creationflags=flags, timeout=60)
                output.seek(0)
                message = output.read().decode("utf-8", errors="replace")
            if result.returncode:
                raise RuntimeError(message)
            return message

        command([str(args.pg_bin / f"initdb{suffix}"), "-D", str(data), "-U", "codex_test",
                 "--auth=trust", "--encoding=UTF8", "--locale=C"])
        started = False
        try:
            command([pg_ctl, "-D", str(data), "-l", str(server_log), "-w", "start",
                     "-o", f"-h 127.0.0.1 -p {port} -c max_connections=50"])
            started = True
            print(command([str(args.pg_bin / f"postgres{suffix}"), "--version"]).strip(), flush=True)
            print(f"Isolated PostgreSQL test instance on loopback port {port}", flush=True)
            env = dict(os.environ)
            env["PYTHONIOENCODING"] = "utf-8"
            env["PYTHONUTF8"] = "1"
            # Never read the application's configured production DATABASE_URL.
            env["SCHEDULE_TEST_DATABASE_URL"] = f"postgresql+asyncpg://codex_test@127.0.0.1:{port}/postgres"
            print("Running backend integration suite against PostgreSQL", flush=True)
            # Pass explicit handles: CREATE_NO_WINDOW can otherwise discard the
            # inherited console streams of the Windows venv launcher.
            with (root / "tests.log").open("w+b") as output:
                result = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "backend/tests", "-v"],
                                        cwd=project, env=env, creationflags=flags,
                                        stdout=output, stderr=subprocess.STDOUT)
                output.seek(0)
                report = output.read().decode("utf-8", errors="replace")
            print(report, flush=True)
            code = result.returncode if "Ran " in report and " tests" in report else 1
        finally:
            if started:
                command([pg_ctl, "-D", str(data), "-m", "fast", "-w", "stop"])
                print("Temporary PostgreSQL instance stopped", flush=True)
        return code


if __name__ == "__main__":
    sys.exit(main())
