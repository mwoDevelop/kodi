"""Bounded GitHub failure observation and durable, single-writer retry budget."""

import datetime as dt
import fcntl
import json
import os
import tempfile
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

DAY = 86400
MAX_ATTEMPTS = 3
MAX_BYTES = 1024 * 1024
BILLING_MESSAGES = (
    "the job was not started because an actions budget is preventing further use",
    "the job was not started because recent account payments have failed",
    "you have exceeded your spending limit",
    "artifact storage quota has been hit",
    "usage quota has been exceeded",
)


def timestamp(value):
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timezone required")
    return parsed.astimezone(dt.timezone.utc)


def _get(repository, path, token):
    # Never follow annotation URLs supplied in remote response bodies.
    url = "https://api.github.com/repos/" + quote(repository, safe="/") + path
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "kodi-watchdog/2"}
    if token:
        headers["Authorization"] = "Bearer " + token
    with urlopen(Request(url, headers=headers), timeout=10) as response:
        raw = response.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("annotation response too large")
    return json.loads(raw)


def classify_failure(repository, run, token=None):
    """Return only a category; never retain/log annotation text or arbitrary URLs."""
    suite = run.get("check_suite_id")
    if type(suite) is not int or suite <= 0:
        raise ValueError("missing check suite")
    document = _get(repository, f"/check-suites/{suite}/check-runs?per_page=100", token)
    checks = document["check_runs"]
    if not isinstance(checks, list) or document.get("total_count") != len(checks):
        raise ValueError("incomplete checks")
    found = False
    requests = 0
    for check in checks:
        if check.get("app", {}).get("slug") != "github-actions":
            continue
        count = check.get("output", {}).get("annotations_count", 0)
        if not count:
            continue
        requests += 1
        check_id = check.get("id")
        if type(check_id) is not int or not 0 < count <= 100 or requests > 8:
            raise ValueError("annotation limit")
        annotations = _get(
            repository, f"/check-runs/{check_id}/annotations?per_page=100", token
        )
        if not isinstance(annotations, list) or len(annotations) != count:
            raise ValueError("incomplete annotations")
        for item in annotations:
            if item.get("annotation_level") != "failure":
                continue
            found = True
            message = str(item.get("message", "")).lower()
            if any(fragment in message for fragment in BILLING_MESSAGES):
                return "BILLING_BLOCKED"
    return "OTHER_FAILURE" if found else "NOT_OBSERVED"


def atomic_write(path, payload):
    path = Path(path)
    fd, temporary = tempfile.mkstemp(prefix=".ledger-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class RetryLedger:
    """No implicit reset: absent, corrupt or locked state disables all writes to GitHub."""

    def __init__(self, path, classifier=classify_failure):
        self.path = Path(path)
        self.classifier = classifier
        self.entries = {}
        self.cache = {}
        self.ready = False
        self.lock = None
        try:
            self.lock = os.open(
                str(self.path) + ".lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600
            )
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if self.path.is_symlink() or self.path.stat().st_size > MAX_BYTES:
                raise ValueError("invalid ledger file")
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if data.get("schema") != 1 or not isinstance(data.get("entries"), dict):
                raise ValueError("invalid ledger schema")
            if len(data["entries"]) > 100:
                raise ValueError("ledger too large")
            for key, entry in data["entries"].items():
                identity = json.loads(key)
                if (
                    not isinstance(identity, list)
                    or len(identity) != 3
                    or not all(isinstance(x, str) and x for x in identity)
                ):
                    raise ValueError("invalid identity")
                if (
                    set(entry) != {"attempts", "blocked_at"}
                    or not isinstance(entry["attempts"], list)
                    or len(entry["attempts"]) > MAX_ATTEMPTS
                ):
                    raise ValueError("invalid entry")
                for value in entry["attempts"] + (
                    [entry["blocked_at"]] if entry["blocked_at"] is not None else []
                ):
                    timestamp(value)
            self.entries = data["entries"]
            self.ready = True
        except (OSError, ValueError, TypeError, AttributeError):
            # Keep the lock when a malformed ledger is found: never overwrite it.
            pass

    @staticmethod
    def initialize(path):
        path = Path(path)
        # Only the explicit provisioning command may create the first ledger.
        if path.exists() or path.is_symlink() or any(path.parent.iterdir()):
            raise ValueError("refusing to reset existing ledger directory")
        atomic_write(path, {"schema": 1, "entries": {}})

    def close(self):
        if self.lock is not None:
            os.close(self.lock)
            self.lock = None
        self.ready = False

    def _save(self):
        if not self.ready:
            raise OSError("ledger unavailable")
        try:
            if not self.path.is_file() or self.path.is_symlink():
                raise OSError("ledger was lost")
            atomic_write(self.path, {"schema": 1, "entries": self.entries})
        except (OSError, ValueError):
            self.ready = False
            raise OSError("ledger write failed") from None

    def policy(self, key, runs, now, token=None):
        encoded = json.dumps(key)
        entry = self.entries.setdefault(encoded, {"attempts": [], "blocked_at": None})
        completed = [r for r in runs if r.get("status") == "completed"]
        latest = max(completed, key=lambda r: timestamp(r["updated_at"]), default=None)
        category = "NOT_OBSERVED"
        observation = "NOT_OBSERVED"
        before = entry["blocked_at"]
        if latest:
            observed_at = timestamp(latest["updated_at"])
            if latest.get("conclusion") == "success":
                category, observation = "NONE", "READY"
                if not before or observed_at > timestamp(before):
                    entry["blocked_at"] = None
            elif latest.get("conclusion") == "failure":
                cache_key = (key[0], latest["id"], latest.get("run_attempt", 1))
                try:
                    category = self.cache.get(cache_key)
                    if category is None:
                        category = self.classifier(key[0], latest, token=token)
                        if category not in {
                            "BILLING_BLOCKED",
                            "OTHER_FAILURE",
                            "NOT_OBSERVED",
                        }:
                            raise ValueError("invalid classification")
                        if category != "NOT_OBSERVED":
                            self.cache[cache_key] = category
                        if len(self.cache) > 100:
                            self.cache.pop(next(iter(self.cache)))
                    observation = (
                        "READY" if category != "NOT_OBSERVED" else "NOT_OBSERVED"
                    )
                    if category == "BILLING_BLOCKED" and (
                        not before or observed_at > timestamp(before)
                    ):
                        entry["blocked_at"] = observed_at.isoformat()
                except (OSError, ValueError, KeyError, TypeError):
                    category = "NOT_OBSERVED"
                    observation = "UNAVAILABLE"
        if entry["blocked_at"] != before and self.ready:
            self._save()
        if entry["blocked_at"]:
            category = "BILLING_BLOCKED"
        return {
            "failure_category": category,
            "failure_observation": observation,
            "remediation_ledger_state": "READY" if self.ready else "UNAVAILABLE",
        }

    def reserve(self, key, now, latest_attempt, cooldown, policy):
        if not self.ready:
            return "LEDGER_UNAVAILABLE"
        entry = self.entries[json.dumps(key)]
        attempts = [
            timestamp(t)
            for t in entry["attempts"]
            if (now - timestamp(t)).total_seconds() < DAY
        ]
        if len(attempts) >= MAX_ATTEMPTS:
            return "RETRY_BUDGET_EXHAUSTED"
        candidates = attempts + ([latest_attempt] if latest_attempt else [])
        if policy["failure_category"] in {"BILLING_BLOCKED", "NOT_OBSERVED"}:
            cooldown = DAY
            if entry["blocked_at"]:
                candidates.append(timestamp(entry["blocked_at"]))
        if candidates and (now - max(candidates)).total_seconds() < cooldown:
            return "NOT_DUE"
        entry["attempts"] = [t.isoformat() for t in attempts] + [now.isoformat()]
        self._save()  # Reserve BEFORE sending even a potentially ambiguous POST.
        return "RESERVED"
