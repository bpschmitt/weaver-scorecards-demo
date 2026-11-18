"""Tiny stdlib-only load generator for both services.

    python loadgen.py                        # loop forever against both services
    python loadgen.py --once --target checkout=http://localhost:8080

--once sends a small fixed batch and exits (used by the CI live-check job).
"""

from __future__ import annotations

import argparse
import json
import random
import time
import urllib.error
import urllib.request

PATHS = {"checkout": "/orders", "legacy-cart": "/cart/checkout"}
CHANNELS = ["web", "mobile", "partner"]
PAYMENTS = ["card", "wallet", "invoice"]


def order_body() -> dict:
    items = [{"sku": f"sku-{random.randint(1, 50)}", "price": round(random.uniform(5, 120), 2)}
             for _ in range(random.randint(1, 4))]
    return {"items": items, "channel": random.choice(CHANNELS), "payment_method": random.choice(PAYMENTS)}


def post(base_url: str, path: str) -> int:
    req = urllib.request.Request(
        base_url + path,
        data=json.dumps(order_body()).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status
    except urllib.error.HTTPError as err:
        return err.code
    except (urllib.error.URLError, OSError):
        return 0  # service not up yet


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", action="append", default=[],
                        help="name=url, e.g. checkout=http://checkout:8080 (repeatable)")
    parser.add_argument("--once", action="store_true", help="send 20 requests per target, then exit")
    parser.add_argument("--interval", type=float, default=0.5, help="seconds between rounds")
    args = parser.parse_args()

    targets = dict(t.split("=", 1) for t in args.target) or {
        "checkout": "http://checkout:8080",
        "legacy-cart": "http://legacy-cart:8081",
    }
    rounds = 20 if args.once else None
    sent = 0
    while rounds is None or sent < rounds:
        for name, url in targets.items():
            status = post(url, PATHS[name])
            print(f"{name}: {status}", flush=True)
        sent += 1
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
