"""The Cloudflare checker, spacecraft side: report in every few seconds, keep the Worker's verdict.

Cloudflare cannot call into a private laptop or Codespace, so the hub (and the NASA receiver) report to the
Worker every ``settings.HEARTBEAT_S`` seconds with their database counts and which parts answer. The Worker
compares the three databases and marks silent parts as down (cloudflare/src/index.js, check()). Without a
Worker configured, the hub runs the same comparison itself and labels it a local check.

Mixed into ``Hub`` (service.py).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from medvital.hub import ai
from medvital.hub import settings as S
from medvital.hub.store import now_iso

if TYPE_CHECKING:
    from medvital.hub.service import Hub


class CheckerLink:
    checker: dict[str, Any]

    def heartbeat_report(self: Hub) -> dict[str, Any]:
        devs = self.devices()
        return {
            "confirmed": self.store.scalar("SELECT COUNT(*) FROM synced") or 0,
            "created": self.store.scalar("SELECT COUNT(*) FROM records") or 0,
            "outbox": self.store.scalar("SELECT COUNT(*) FROM outbox") or 0,
            "devices": [
                {"id": d["astronautId"], "up": bool(d["connected"]), "seenS": d["lastSeenSeconds"]} for d in devs
            ],
            "agent": {"up": True, "model": ai.agent_label()},
        }

    def heartbeat(self: Hub) -> None:
        """Every few seconds. Through Cloudflare when configured, otherwise a local check."""
        report = self.heartbeat_report()
        if self.cf_url:
            status, ans = self._nasa("POST", "/heartbeat", {"node": "hub", "report": report}, timeout=8)
            if status == 200 and isinstance(ans, dict):
                self.checker = {"via": "cloudflare", "ok": True, **ans}
                self.net.add("check", ["checker", "cloudflare", "net", "hub"], "ok", "Cloudflare checker: hub checked")
            else:
                self.checker = {
                    **self.checker,
                    "via": "cloudflare",
                    "ok": False,
                    "error": "Cloudflare unreachable" if status is None else f"Cloudflare answered HTTP {status}",
                    "at": now_iso(),
                }
            return
        self.checker = self.local_check(report)

    def local_check(self: Hub, report: dict[str, Any]) -> dict[str, Any]:
        """No Worker configured: the hub compares its own counts with the NASA receiver's."""
        nasa = self.nasa_stats()
        link = self.link()
        nasa_total = nasa.get("total") if nasa else None
        ok = nasa_total is None or nasa_total >= report["confirmed"]
        devs = report["devices"]
        up = sum(1 for d in devs if d["up"])
        sentence = (
            f"Local check (Cloudflare not configured): {up} of {len(devs)} wearables reporting; "
            + ("NASA reporting" if nasa else "NASA silent")
            + f"; spacecraft confirmed {report['confirmed']}, NASA holds {nasa_total if nasa_total is not None else '?'}."
        )
        return {
            "via": "local",
            "ok": True,
            "at": now_iso(),
            "parts": {
                "cloudflare": {"up": False, "configured": False},
                "d1": {"up": False},
                "hub": {"up": True, "seenS": 0},
                "nasa": {"up": nasa is not None, "seenS": 0 if nasa else None},
                "agent": report["agent"],
                "donki": {"up": not self.donki_state.get("error"), "fetchedAt": self.donki_state.get("lastFetch")},
                "devices": devs,
            },
            "link": {"up": bool(link.get("up")), "retryEveryS": S.RETRY_S},
            "db": {
                "spacecraftConfirmed": report["confirmed"],
                "spacecraftWaiting": report["outbox"],
                "cloudflare": None,
                "nasa": nasa_total,
                "waitingAtCloudflare": 0,
                "ok": ok,
            },
            "log": [],
            "sentence": {"text": sentence, "source": "rules", "at": now_iso()},
        }
