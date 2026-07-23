"""Watch a Palworld AMP application and recover it after an unexpected crash.

This command deliberately does not use the database.  It reads AMP's controller
state, persists a small watchdog state file, sends a Discord notification, and
starts/restarts only the configured AMP application.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import aiohttp
from django.core.management.base import BaseCommand, CommandError

from ampapi.bridge import Bridge
from ampapi.controller import AMPControllerInstance
from ampapi.dataclass import APIParams


logger = logging.getLogger(__name__)

DEFAULT_INSTANCE = "HeroesofPalpagos02"
DEFAULT_CHANNEL_ID = "1297409767207079936"
DEFAULT_USER_ID = "141890558045061120"
DEFAULT_MANAGER_ROLE_ID = "1346385909158903839"
DEFAULT_STATE_FILE = "/srv/ch-webserver/cache/palworld_amp_watchdog_state.json"

HEALTHY_STATES = {"ready"}
UNHEALTHY_STATES = {"failed", "stopped", "indeterminate", "undefined"}
INTENTIONAL_STOP_STATES = {
    "stopping",
    "preparing_for_sleep",
    "sleeping",
    "suspended",
    "maintenance",
}
TRANSITIONAL_STATES = {
    "pre_start",
    "configuring",
    "starting",
    "restarting",
    "waiting",
    "installing",
    "updating",
    "awaiting_user_input",
}

_ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_CRASH_RE = re.compile(
    r"\b(fatal|crash(?:ed)?|unhandled exception|segmentation fault|access violation|out of memory)\b",
    re.IGNORECASE,
)


@dataclass
class Observation:
    state: str
    amp_running: bool
    friendly_name: str
    console_context: list[str]
    instance: Any
    controller: AMPControllerInstance


def default_watchdog_state() -> dict[str, Any]:
    return {
        "version": 1,
        "armed": False,
        "incident_open": False,
        "unhealthy_polls": 0,
        "last_state": None,
        "last_healthy_at": None,
        "incident_started_at": None,
        "last_restart_at": None,
        "restart_requested": False,
        "recovery_timeout_notified": False,
    }


def evaluate_observation(
    state: dict[str, Any],
    app_state: str,
    amp_running: bool,
    failure_polls: int,
) -> str:
    """Update state and return one of: healthy, wait, disarmed, or crash."""
    previous_state = state.get("last_state")
    state["last_state"] = app_state

    if amp_running and app_state in HEALTHY_STATES:
        state["armed"] = True
        state["unhealthy_polls"] = 0
        state["last_healthy_at"] = int(time.time())
        return "healthy"

    if app_state in INTENTIONAL_STOP_STATES:
        state["armed"] = False
        state["unhealthy_polls"] = 0
        return "disarmed"

    if app_state in TRANSITIONAL_STATES:
        state["unhealthy_polls"] = 0
        return "wait"

    is_unhealthy = (not amp_running) or app_state in UNHEALTHY_STATES
    if not is_unhealthy:
        state["unhealthy_polls"] = 0
        return "wait"

    # A deliberate stop normally exposes `stopping` before `stopped`.  Disarm
    # on that sequence so a manual AMP stop does not get undone by the watcher.
    if app_state == "stopped" and previous_state in INTENTIONAL_STOP_STATES:
        state["armed"] = False
        state["unhealthy_polls"] = 0
        return "disarmed"

    # Never start a server merely because the watchdog itself just came online.
    # It must first have observed this application healthy (persisted in state).
    if not state.get("armed"):
        state["unhealthy_polls"] = 0
        return "disarmed"

    state["unhealthy_polls"] = int(state.get("unhealthy_polls") or 0) + 1
    if state["unhealthy_polls"] >= failure_polls:
        return "crash"
    return "wait"


class PalworldAMPWatchdog:
    def __init__(self, command: BaseCommand, options: dict[str, Any]):
        self.command = command
        self.instance_name = options["instance"]
        self.channel_id = options["channel_id"]
        self.user_id = options["user_id"]
        self.manager_role_id = options["manager_role_id"]
        self.interval = options["interval"]
        self.failure_polls = options["failure_polls"]
        self.restart_cooldown = options["restart_cooldown"]
        self.recovery_timeout = options["recovery_timeout"]
        self.state_path = Path(options["state_file"])
        self.once = options["once"]
        self.dry_run = options["dry_run"]
        self.include_console = options["include_console"]
        self.amp_url = os.getenv("AMP_URL", "").strip()
        self.amp_user = os.getenv("AMP_USER", "").strip()
        self.amp_password = os.getenv("AMP_PASSWORD", "")
        self.discord_token = os.getenv("DISCORD_BOT_TOKEN", "").strip()
        self.state = self._load_state()

    def validate(self) -> None:
        missing = [
            key
            for key, value in (
                ("AMP_URL", self.amp_url),
                ("AMP_USER", self.amp_user),
                ("AMP_PASSWORD", self.amp_password),
            )
            if not value
        ]
        if not self.dry_run and not self.discord_token:
            missing.append("DISCORD_BOT_TOKEN")
        if missing:
            raise CommandError("Missing required environment variables: " + ", ".join(missing))

    def _load_state(self) -> dict[str, Any]:
        state = default_watchdog_state()
        try:
            loaded = json.loads(self.state_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict) and loaded.get("version") == 1:
                state.update(loaded)
        except FileNotFoundError:
            pass
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Ignoring unreadable Palworld watchdog state file: %s", exc)
        return state

    def _save_state(self) -> None:
        if self.dry_run:
            return
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        temporary.write_text(json.dumps(self.state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temporary, self.state_path)

    async def run(self) -> None:
        self.validate()
        self.command.stdout.write(
            f"Watching AMP instance {self.instance_name!r} every {self.interval}s"
            + (" (dry run)" if self.dry_run else "")
        )
        while True:
            try:
                observation = await self._observe()
                await self._process(observation)
            except asyncio.CancelledError:
                raise
            except Exception:
                # An AMP/network failure is not evidence that Palworld crashed.
                # Never restart based only on the monitor losing API access.
                logger.exception("Palworld AMP watchdog poll failed")
            if self.once:
                return
            await asyncio.sleep(self.interval)

    async def _observe(self) -> Observation:
        Bridge(
            api_params=APIParams(
                url=self.amp_url,
                user=self.amp_user,
                password=self.amp_password,
            )
        )
        controller = AMPControllerInstance()
        await asyncio.wait_for(controller.get_instances(), timeout=15)

        instance = self._select_instance(controller)
        state_value = getattr(instance.app_state, "name", str(instance.app_state)).lower()
        context: list[str] = []
        if self.include_console and instance.running and state_value in UNHEALTHY_STATES:
            context = await self._get_console_context(instance)

        return Observation(
            state=state_value,
            amp_running=bool(instance.running),
            friendly_name=instance.friendly_name or instance.instance_name,
            console_context=context,
            instance=instance,
            controller=controller,
        )

    def _select_instance(self, controller: AMPControllerInstance) -> Any:
        exact = [item for item in controller.instances if item.instance_name == self.instance_name]
        if not exact:
            wanted = self.instance_name.casefold()
            exact = [
                item
                for item in controller.instances
                if item.instance_name.casefold() == wanted or item.friendly_name.casefold() == wanted
            ]
        if len(exact) != 1:
            available = sorted(item.instance_name for item in controller.instances)
            raise RuntimeError(
                f"AMP instance {self.instance_name!r} was not found uniquely. "
                f"Available instances: {', '.join(available)}"
            )
        return exact[0]

    async def _get_console_context(self, instance: Any) -> list[str]:
        try:
            updates = await asyncio.wait_for(instance.get_updates(), timeout=5)
        except Exception as exc:
            logger.info("Could not collect AMP console context: %s", exc)
            return []

        matches: list[str] = []
        for entry in getattr(updates, "console_entries", [])[-100:]:
            contents = _ANSI_RE.sub("", str(getattr(entry, "contents", "")))
            entry_type = str(getattr(entry, "type", ""))
            if entry_type.casefold() == "error" or _CRASH_RE.search(contents):
                clean = " ".join(contents.split()).replace("```", "'''")
                if clean:
                    matches.append(clean[:350])
        return matches[-3:]

    async def _process(self, observation: Observation) -> None:
        outcome = evaluate_observation(
            self.state,
            observation.state,
            observation.amp_running,
            self.failure_polls,
        )
        logger.info(
            "Palworld AMP state=%s amp_running=%s outcome=%s armed=%s unhealthy_polls=%s",
            observation.state,
            observation.amp_running,
            outcome,
            self.state.get("armed"),
            self.state.get("unhealthy_polls"),
        )

        if outcome == "healthy":
            if self.state.get("incident_open"):
                await self._notify_recovered(observation)
                self.state.update(
                    incident_open=False,
                    incident_started_at=None,
                    restart_requested=False,
                    recovery_timeout_notified=False,
                )
        elif outcome == "crash" and not self.state.get("incident_open"):
            await self._open_incident(observation)
        elif self.state.get("incident_open"):
            await self._check_recovery_timeout(observation)

        self._save_state()

    async def _open_incident(self, observation: Observation) -> None:
        now = int(time.time())
        last_restart = int(self.state.get("last_restart_at") or 0)
        cooldown_left = max(0, self.restart_cooldown - (now - last_restart))
        will_restart = cooldown_left == 0

        self.state.update(
            incident_open=True,
            incident_started_at=now,
            restart_requested=False,
            recovery_timeout_notified=False,
        )

        action_text = (
            "Automatic recovery is being requested now."
            if will_restart
            else f"Automatic recovery is suppressed by the cooldown for another {cooldown_left}s."
        )
        context = ""
        if observation.console_context:
            context = "\nRecent matching AMP console output:\n```\n" + "\n".join(observation.console_context) + "\n```"
        content = (
            f"<@{self.user_id}> <@&{self.manager_role_id}>\n"
            f"**Palworld crash detected** - {observation.friendly_name} "
            f"(`{self.instance_name}`) is `{observation.state}` "
            f"(AMP instance running: `{str(observation.amp_running).lower()}`).\n"
            f"{action_text}{context}"
        )
        await self._send_discord(content, ping=True)

        if not will_restart:
            return
        if self.dry_run:
            self.command.stdout.write("DRY RUN: would request automatic Palworld recovery")
            return

        try:
            result, action = await self._recover(observation)
            success = bool(getattr(result, "status", True))
            reason = getattr(result, "reason", None)
            if not success:
                raise RuntimeError(reason or "AMP rejected the recovery request")
            self.state["last_restart_at"] = now
            self.state["restart_requested"] = True
            await self._send_discord(
                f"AMP accepted automatic `{action}` recovery for **{observation.friendly_name}**. "
                "Watching for the application to return to Ready.",
                ping=False,
            )
        except Exception as exc:
            logger.exception("Automatic Palworld recovery failed")
            await self._send_discord(
                f"AMP automatic recovery failed for **{observation.friendly_name}**: "
                f"`{self._safe_error(exc)}`. Manual action is required.",
                ping=False,
            )

    async def _recover(self, observation: Observation) -> tuple[Any, str]:
        if not observation.amp_running:
            result = await asyncio.wait_for(
                observation.controller.start_instance(instance_name=self.instance_name), timeout=30
            )
            return result, "start AMP instance"

        if observation.state in {"stopped", "failed"}:
            result = await asyncio.wait_for(observation.instance.start_application(), timeout=30)
            return result, "start application"

        result = await asyncio.wait_for(observation.instance.restart_application(), timeout=30)
        return result, "restart application"

    async def _check_recovery_timeout(self, observation: Observation) -> None:
        started = int(self.state.get("incident_started_at") or 0)
        if (
            not self.state.get("restart_requested")
            or self.state.get("recovery_timeout_notified")
            or not started
            or int(time.time()) - started < self.recovery_timeout
        ):
            return
        self.state["recovery_timeout_notified"] = True
        await self._send_discord(
            f"**{observation.friendly_name}** has not returned to Ready within "
            f"{self.recovery_timeout}s after automatic recovery. Current AMP state: "
            f"`{observation.state}`. Manual investigation is required.",
            ping=False,
        )

    async def _notify_recovered(self, observation: Observation) -> None:
        started = int(self.state.get("incident_started_at") or int(time.time()))
        elapsed = max(0, int(time.time()) - started)
        await self._send_discord(
            f"**{observation.friendly_name}** is back in AMP state `ready` "
            f"after {elapsed}s. Automatic monitoring remains active.",
            ping=False,
        )

    async def _send_discord(self, content: str, ping: bool) -> bool:
        if self.dry_run:
            self.command.stdout.write("DRY RUN Discord message: " + content)
            return True

        allowed_mentions: dict[str, Any] = {"parse": []}
        if ping:
            allowed_mentions.update(users=[self.user_id], roles=[self.manager_role_id])
        payload = {"content": content[:2000], "allowed_mentions": allowed_mentions}
        headers = {
            "Authorization": f"Bot {self.discord_token}",
            "Content-Type": "application/json",
            "User-Agent": "CasualHeroes-PalworldWatchdog/1.0",
        }
        timeout = aiohttp.ClientTimeout(total=15)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    f"https://discord.com/api/v10/channels/{self.channel_id}/messages",
                    json=payload,
                    headers=headers,
                ) as response:
                    if response.status not in (200, 201):
                        body = (await response.text())[:500]
                        raise RuntimeError(f"Discord returned HTTP {response.status}: {body}")
            return True
        except Exception:
            # Discord being unavailable must never prevent the independent AMP
            # recovery action or leave an incident wedged open.
            logger.exception("Could not send Palworld watchdog Discord notification")
            return False

    def _safe_error(self, exc: Exception) -> str:
        # Keep credentials/URLs out of Discord if an HTTP library includes them.
        message = " ".join(str(exc).split())[:300]
        for secret in (self.amp_password, self.discord_token, self.amp_user, self.amp_url):
            if secret:
                message = message.replace(secret, "[redacted]")
        return message.replace("`", "'") or exc.__class__.__name__


class Command(BaseCommand):
    help = "Watch a Palworld AMP application, notify Discord after a crash, and recover it automatically."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--instance", default=os.getenv("PALWORLD_AMP_INSTANCE", DEFAULT_INSTANCE))
        parser.add_argument("--channel-id", default=os.getenv("PALWORLD_CRASH_CHANNEL_ID", DEFAULT_CHANNEL_ID))
        parser.add_argument("--user-id", default=os.getenv("PALWORLD_CRASH_USER_ID", DEFAULT_USER_ID))
        parser.add_argument(
            "--manager-role-id",
            default=os.getenv("PALWORLD_SERVER_MANAGER_ROLE_ID", DEFAULT_MANAGER_ROLE_ID),
        )
        parser.add_argument(
            "--interval", type=int, default=int(os.getenv("PALWORLD_CRASH_POLL_SECONDS", "5"))
        )
        parser.add_argument(
            "--failure-polls", type=int, default=int(os.getenv("PALWORLD_CRASH_FAILURE_POLLS", "2"))
        )
        parser.add_argument(
            "--restart-cooldown",
            type=int,
            default=int(os.getenv("PALWORLD_CRASH_RESTART_COOLDOWN", "300")),
        )
        parser.add_argument(
            "--recovery-timeout",
            type=int,
            default=int(os.getenv("PALWORLD_CRASH_RECOVERY_TIMEOUT", "300")),
        )
        parser.add_argument(
            "--state-file", default=os.getenv("PALWORLD_CRASH_STATE_FILE", DEFAULT_STATE_FILE)
        )
        parser.add_argument("--once", action="store_true", help="Poll once, then exit.")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Read AMP and show decisions without Discord, recovery, or state-file writes.",
        )
        parser.add_argument(
            "--include-console",
            action="store_true",
            default=os.getenv("PALWORLD_CRASH_INCLUDE_CONSOLE", "false").lower() in {"1", "true", "yes"},
            help="Include matching fatal/error console lines in Discord alerts.",
        )

    def handle(self, *args, **options) -> None:
        if options["interval"] < 5:
            raise CommandError("--interval must be at least 5 seconds")
        if options["failure_polls"] < 1:
            raise CommandError("--failure-polls must be at least 1")
        asyncio.run(PalworldAMPWatchdog(self, options).run())
