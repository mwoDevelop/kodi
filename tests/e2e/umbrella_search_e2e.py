#!/usr/bin/env python3
"""Exercise Umbrella's real search keyboard without reading account secrets."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from urllib.parse import quote_plus

from sony_kodi_matrix import (
	AdbEventClient,
	EventClient,
	JsonRpc,
	addon_version,
	kodi_version,
	shell,
)


SOURCE_PROGRESS_WINDOW = 10160
KEYBOARD_WINDOWS = {10103, 10138}
VIDEOS_WINDOW = 10025


def current_window(rpc: JsonRpc) -> dict:
	result = rpc.call("GUI.GetProperties", {"properties": ["currentwindow"]})
	window = result.get("currentwindow", {}) if isinstance(result, dict) else {}
	return window if isinstance(window, dict) else {}


def wait_for_window(
	rpc: JsonRpc,
	predicate,
	timeout: float,
	transitions: list[dict],
) -> dict:
	started = time.monotonic()
	last = {}
	while time.monotonic() - started < timeout:
		last = current_window(rpc)
		if not transitions or transitions[-1] != last:
			transitions.append(last)
		if predicate(last):
			return last
		time.sleep(0.25)
	raise RuntimeError("window transition timed out; last window was %r" % last)


def matching_search_results(rpc: JsonRpc, term: str) -> list[str]:
	directory = (
		"plugin://plugin.video.umbrella/?action=movieSearchterm&name=%s"
		% quote_plus(term)
	)
	result = rpc.call(
		"Files.GetDirectory",
		{"directory": directory, "properties": ["title"]},
	)
	files = result.get("files", []) if isinstance(result, dict) else []
	labels = [
		str(item.get("label") or item.get("title") or "")
		for item in files
		if isinstance(item, dict)
	]
	return [label for label in labels if term.casefold() in label.casefold()]


def run_search(
	rpc: JsonRpc,
	events: EventClient,
	term: str,
	timeout: float,
) -> dict:
	transitions = []
	before = current_window(rpc)
	if before.get("id") == SOURCE_PROGRESS_WINDOW:
		raise RuntimeError(
			"stale Umbrella source_progress window blocks search before test start"
		)
	events.execute_builtin("ActivateWindow(Home)")
	wait_for_window(
		rpc,
		lambda window: window.get("id") == 10000,
		timeout,
		transitions,
	)
	events.execute_builtin(
		"ActivateWindow(Videos,"
		"plugin://plugin.video.umbrella/?action=movieSearchnew,return)"
	)
	keyboard = wait_for_window(
		rpc,
		lambda window: window.get("id") in KEYBOARD_WINDOWS,
		timeout,
		transitions,
	)
	rpc.call("Input.SendText", {"text": term, "done": True})
	wait_for_window(
		rpc,
		lambda window: window.get("id") == VIDEOS_WINDOW,
		timeout,
		transitions,
	)
	matches = []
	started = time.monotonic()
	while time.monotonic() - started < timeout:
		matches = matching_search_results(rpc, term)
		if matches:
			break
		time.sleep(0.5)
	if not matches:
		raise RuntimeError("Umbrella returned no matching result for %r" % term)
	after = current_window(rpc)
	if after.get("id") == SOURCE_PROGRESS_WINDOW:
		raise RuntimeError("source_progress window reappeared during search")
	return {
		"term": term,
		"keyboard_window": keyboard,
		"matches": matches[:10],
		"window_transitions": transitions,
		"final_window": after,
	}


def main() -> int:
	parser = argparse.ArgumentParser()
	parser.add_argument("--adb", required=True)
	parser.add_argument("--serial", required=True)
	parser.add_argument("--host", required=True)
	parser.add_argument("--jsonrpc-port", type=int, default=9090)
	parser.add_argument("--event-via-adb", action="store_true")
	parser.add_argument("--term", default="Sintel")
	parser.add_argument("--timeout", type=float, default=30)
	parser.add_argument("--result", required=True)
	args = parser.parse_args()

	rpc = JsonRpc(args.host, args.jsonrpc_port)
	events = (
		AdbEventClient(args.adb, args.serial)
		if args.event_via_adb
		else EventClient(args.host)
	)
	if rpc.call("JSONRPC.Ping") != "pong":
		raise RuntimeError("Kodi JSON-RPC did not return pong")

	report = {
		"schema": 1,
		"device": {
			"serial": args.serial,
			"manufacturer": shell(
				args.adb, args.serial, "getprop ro.product.manufacturer"
			).strip(),
			"model": shell(
				args.adb, args.serial, "getprop ro.product.model"
			).strip(),
			"kodi": kodi_version(args.adb, args.serial),
		},
		"umbrella_version": addon_version(
			args.adb, args.serial, "plugin.video.umbrella"
		),
		"search": run_search(rpc, events, args.term, args.timeout),
		"tokens_collected": False,
	}
	output = Path(args.result)
	output.parent.mkdir(parents=True, exist_ok=True)
	output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
	print(json.dumps(report, indent=2))
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
