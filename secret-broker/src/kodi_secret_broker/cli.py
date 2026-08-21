"""Host-local administration and service entrypoint."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .service import serve
from .store import SecretStore


def parser():
    result = argparse.ArgumentParser()
    result.add_argument("--database", default="/data/secrets.db")
    result.add_argument("--master-key", default="/run/secrets/broker-master-key")
    commands = result.add_subparsers(dest="command", required=True)
    commands.add_parser("init-key")
    put = commands.add_parser("import")
    put.add_argument("--input", required=True)
    transition = commands.add_parser("transition")
    transition.add_argument("secret_set_id")
    transition.add_argument("generation", type=int)
    transition.add_argument("--from", dest="expected", required=True)
    transition.add_argument("--to", dest="lifecycle", required=True)
    commands.add_parser("health")
    server = commands.add_parser("serve")
    server.add_argument("--host", default="0.0.0.0")
    server.add_argument("--port", type=int, default=9444)
    server.add_argument("--certificate", default="/run/tls/server.crt")
    server.add_argument("--private-key", default="/run/tls/server.key")
    server.add_argument("--client-ca", default="/run/tls/client-ca.crt")
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    key_path = Path(args.master_key)
    if args.command == "init-key":
        key_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write((os.urandom(32).hex() + "\n").encode("ascii"))
        print(json.dumps({"status": "created", "path": str(key_path)}))
        return 0
    store = SecretStore(args.database, args.master_key)
    if args.command == "import":
        document = (
            json.load(sys.stdin)
            if args.input == "-"
            else json.loads(Path(args.input).read_text(encoding="utf-8"))
        )
        print(json.dumps(store.put(document), sort_keys=True))
    elif args.command == "transition":
        print(
            json.dumps(
                store.transition(
                    args.secret_set_id,
                    args.generation,
                    args.lifecycle,
                    args.expected,
                ),
                sort_keys=True,
            )
        )
    elif args.command == "health":
        print(json.dumps(store.readiness(), sort_keys=True))
    elif args.command == "serve":
        serve(
            store,
            args.host,
            args.port,
            args.certificate,
            args.private_key,
            args.client_ca,
        )
    return 0
