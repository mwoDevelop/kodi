#!/usr/bin/env python3
"""Exercise Umbrella's real search keyboard without reading account secrets."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Callable
from urllib.parse import quote_plus

from sony_kodi_matrix import (
	JsonRpc,
	JsonRpcError,
	addon_version,
	kodi_version,
	shell,
)

SOURCE_PROGRESS_WINDOW = 10160
SHUTDOWN_MENU_WINDOW = 10111
OK_DIALOG_WINDOW = 12002
PVR_INFO_TITLE = "No PVR add-on enabled"
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


def search_action(media_type: str, suffix: str) -> str:
	return "%sSearch%s" % ("tv" if media_type == "tv" else "movie", suffix)


def dismiss_known_startup_window(
	rpc: JsonRpc,
	window: dict,
	timeout: float,
	transitions: list[dict],
	modal_back: Callable[[], None] | None = None,
) -> dict:
	"""Close a harmless stale Kodi modal without hiding resolver failures."""
	window_id = window.get("id")
	if window_id == OK_DIALOG_WINDOW:
		labels = rpc.call(
			"XBMC.GetInfoLabels",
			{"labels": ["Control.GetLabel(1)"]},
		)
		title = (
			labels.get("Control.GetLabel(1)", "")
			if isinstance(labels, dict)
			else ""
		)
		if title != PVR_INFO_TITLE:
			return window
		if modal_back is not None:
			modal_back()
			dismiss_method = None
		else:
			dismiss_method = "Input.Select"
	elif window_id != SHUTDOWN_MENU_WINDOW:
		return window
	else:
		dismiss_method = "Input.Back"
	if dismiss_method is not None:
		rpc.call(dismiss_method)
	return wait_for_window(
		rpc,
		lambda current: current.get("id") != window_id,
		timeout,
		transitions,
	)


def activate_home(
	rpc: JsonRpc,
	timeout: float,
	transitions: list[dict],
	modal_back: Callable[[], None] | None = None,
) -> dict:
	for _attempt in range(3):
		rpc.call("GUI.ActivateWindow", {"window": "home"})
		window = wait_for_window(
			rpc,
			lambda current: current.get("id")
			in {10000, SHUTDOWN_MENU_WINDOW, OK_DIALOG_WINDOW},
			timeout,
			transitions,
		)
		if window.get("id") == 10000:
			return window
		dismissed = dismiss_known_startup_window(
			rpc, window, timeout, transitions, modal_back
		)
		if dismissed == window:
			raise RuntimeError(
				"unexpected dialog blocks Kodi home: %r" % window
			)
	raise RuntimeError("Kodi home remained blocked by startup dialogs")


def matching_search_results(
	rpc: JsonRpc,
	term: str,
	media_type: str = "movie",
) -> list[str]:
	directory = (
		"plugin://plugin.video.umbrella/?action=%s&name=%s"
		% (search_action(media_type, "term"), quote_plus(term))
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
	media_type: str = "movie",
) -> dict:
	deadline = time.monotonic() + timeout
	while time.monotonic() < deadline:
		url = (
			"plugin://plugin.video.umbrella/"
			"?action=%s&e2e_nonce=%d"
			% (search_action(media_type, "new"), time.time_ns())
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
	media_type: str = "movie",
	modal_back: Callable[[], None] | None = None,
) -> dict:
	transitions = []
	before = current_window(rpc)
	before = dismiss_known_startup_window(
		rpc, before, timeout, transitions, modal_back
	)
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
	activate_home(rpc, timeout, transitions, modal_back)
	time.sleep(2)
	keyboard = open_search_keyboard(rpc, timeout, transitions, media_type)
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
	directory_error = None
	started = time.monotonic()
	while time.monotonic() - started < timeout:
		try:
			matches = matching_search_results(rpc, term, media_type)
		except JsonRpcError as error:
			# Kodi can expose the Videos window before an asynchronous plugin
			# directory becomes queryable.  Retry only this exact transient
			# GetDirectory response; all other RPC errors remain fail-fast.
			if error.method != "Files.GetDirectory" or error.code != -32602:
				raise
			directory_error = error
			time.sleep(0.5)
			continue
		if matches:
			break
		time.sleep(0.5)
	if not matches:
		if directory_error is not None:
			raise RuntimeError(
				"Umbrella search directory remained unavailable"
			) from directory_error
		raise RuntimeError("Umbrella returned no matching result for %r" % term)
	after = current_window(rpc)
	if after.get("id") == SOURCE_PROGRESS_WINDOW:
		raise RuntimeError("source_progress window reappeared during search")
	return {
		"term": term,
		"media_type": media_type,
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
	parser.add_argument("--media-type", choices=("movie", "tv"), default="movie")
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
			args.adb, args.serial, "plugin.video.umbrella", rpc
		),
		"search": run_search(
			rpc,
			args.term,
			args.timeout,
			args.media_type,
			modal_back=lambda: shell(
				args.adb, args.serial, "input keyevent 4"
			),
		),
		"tokens_collected": False,
	}
	output = Path(args.result)
	output.parent.mkdir(parents=True, exist_ok=True)
	output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
	print(json.dumps(report, indent=2))
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
