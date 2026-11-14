"""CLI: python -m medvital.device --device-id MEDVITAL-WEARABLE-001 --crew-id CREW-001 --gateway http://HOST:8000"""

from __future__ import annotations

import argparse

from medvital.device.simulator import GENERATOR_VERSION, WearableSimulator
from medvital.device.uplink import Uplink, UrllibTransport, run_device


def main() -> None:
    p = argparse.ArgumentParser(description="Simulated MEDVITAL astronaut wearable (synthetic data only).")
    p.add_argument("--device-id", default="MEDVITAL-WEARABLE-001")
    p.add_argument("--crew-id", default="CREW-001")
    p.add_argument("--gateway", default="http://localhost:8000", help="Gateway base URL")
    p.add_argument("--interval", type=float, default=1.0, help="Seconds between readings")
    p.add_argument(
        "--duration", type=float, default=None, help="Stop after N seconds (default: until Ctrl+C)"
    )
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--slow-every", type=int, default=30, help="Emit sleep/exercise entries every N ticks")
    p.add_argument("--radiation-factor", type=float, default=1.0, help="Radiation scenario multiplier")
    args = p.parse_args()

    sim = WearableSimulator(
        args.device_id, args.crew_id, seed=args.seed, slow_every=args.slow_every
    )
    sim.radiation_factor = args.radiation_factor
    uplink = Uplink(UrllibTransport(args.gateway))
    print(
        f"[{args.device_id}] SIMULATED device for {args.crew_id} ({GENERATOR_VERSION}, seed={args.seed}) -> "
        f"{args.gateway}. All values are SYNTHETIC test signals, not astronaut data. Ctrl+C to stop."
    )
    try:
        run_device(sim, uplink, interval=args.interval, duration=args.duration)
        uplink.flush()  # last chance to deliver anything still buffered
    except KeyboardInterrupt:
        print(f"\n[{args.device_id}] stopped; {len(uplink.buffer)} event(s) still buffered (not delivered).")
        return
    print(
        f"[{args.device_id}] done: accepted={uplink.total_accepted} duplicate={uplink.total_duplicate} "
        f"rejected={uplink.total_rejected} still_buffered={len(uplink.buffer)} dropped={uplink.dropped}"
    )


if __name__ == "__main__":
    main()
