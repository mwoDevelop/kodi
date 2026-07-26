#!/usr/bin/env python3
"""Exercise Umbrella's real search keyboard without reading account secrets."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from urllib.parse import quote_plus

from sony_kodi_matrix import JsonRpc, addon_version, kodi_version, shell


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


def submit_keyboard(rpc: JsonRpc, term: str, timeout: float) -> None:
	rpc.call("Input.SendText", {"text": term, "done": True})
	started = time.monotonic()
	while time.monotonic() - started < timeout:
		result = rpc.call(
			"GUI.GetProperties",
			{"properties": ["currentwindow", "currentcontrol"]},
		)
		window = result.get("currentwindow", {}) if isinstance(result, dict) else {}
		control = result.get("currentcontrol", {}) if isinstance(result, dict) else {}
		if isinstance(window, dict) and window.get("id") == VIDEOS_WINDOW:
			return
		if isinstance(control, dict) and control.get("label") == "Done":
			rpc.call("Input.Select")
			return
		time.sleep(0.1)
	raise RuntimeError("virtual keyboard never focused its Done control")


def open_search_keyboard(
	rpc: JsonRpc,
	timeout: float,
	transitions: list[dict],
) -> dict:
	deadline = time.monotonic() + timeout
	while time.monotonic() < deadline:
		url = (
			"plugin://plugin.video.umbrella/"
			"?action=movieSearchnew&e2e_nonce=%d" % time.time_ns()
		)
		rpc.call(
			"GUI.ActivateWindow",
			{"window": "videos", "parameters": [url, "return"]},
		)
		probe_deadline = min(deadline, time.monotonic() + 10)
		while time.monotonic() < probe_deadline:
			window = current_window(rpc)
			if not transitions or transitions[-1] != window:
				transitions.append(window)
			if window.get("id") in KEYBOARD_WINDOWS:
				return window
			if window.get("id") == SOURCE_PROGRESS_WINDOW:
				raise RuntimeError("source_progress appeared while opening search")
			time.sleep(0.25)
	raise RuntimeError("Umbrella search keyboard did not open")


def run_search(
	rpc: JsonRpc,
	term: str,
	timeout: float,
) -> dict:
	transitions = []
	before = current_window(rpc)
	if before.get("id") == SOURCE_PROGRESS_WINDOW:
		raise RuntimeError(
			"stale Umbrella source_progress window blocks search before test start"
		)
	if before.get("id") in KEYBOARD_WINDOWS:
		rpc.call("Input.Back")
		wait_for_window(
			rpc,
			lambda window: window.get("id") not in KEYBOARD_WINDOWS,
			timeout,
			transitions,
		)
	rpc.call("GUI.ActivateWindow", {"window": "home"})
	wait_for_window(
		rpc,
		lambda window: window.get("id") == 10000,
		timeout,
		transitions,
	)
	time.sleep(2)
	keyboard = open_search_keyboard(rpc, timeout, transitions)
	# Kodi 21 may focus the virtual keyboard's Done control without activating it.
	# Selecting the focused control makes submission deterministic on Android TV.
	submit_keyboard(rpc, term, timeout)
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
	parser.add_argument("--term", default="Sintel")
	parser.add_argument("--timeout", type=float, default=30)
	parser.add_argument("--result", required=True)
	args = parser.parse_args()

	rpc = JsonRpc(args.host, args.jsonrpc_port)
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
		"search": run_search(rpc, args.term, args.timeout),
		"tokens_collected": False,
	}
	output = Path(args.result)
	output.parent.mkdir(parents=True, exist_ok=True)
	output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
	print(json.dumps(report, indent=2))
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
