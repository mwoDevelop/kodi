import umbrella_search_e2e


class Rpc:
	def call(self, method, params=None):
		assert method == "Files.GetDirectory"
		assert "movieSearchterm" in params["directory"]
		return {
			"files": [
				{"label": "Unrelated (2001)", "title": "Unrelated"},
				{"label": "Sintel (2010)", "title": "Sintel"},
			]
		}


def test_matching_search_results_filters_case_insensitively():
	assert umbrella_search_e2e.matching_search_results(Rpc(), "sintel") == [
		"Sintel (2010)"
	]


def test_tv_search_uses_tvshow_directory_action():
	class TvRpc:
		def call(self, method, params=None):
			assert method == "Files.GetDirectory"
			assert "action=tvSearchterm" in params["directory"]
			return {"files": [{"label": "House of the Dragon"}]}

	assert umbrella_search_e2e.matching_search_results(
		TvRpc(),
		"House of the Dragon",
		media_type="tv",
	) == ["House of the Dragon"]


def test_search_action_selects_movie_or_tv_router():
	assert umbrella_search_e2e.search_action("movie", "new") == "movieSearchnew"
	assert umbrella_search_e2e.search_action("tv", "term") == "tvSearchterm"


def test_keyboard_window_ids_cover_kodi_omega_variants():
	assert 10103 in umbrella_search_e2e.KEYBOARD_WINDOWS
	assert 10138 in umbrella_search_e2e.KEYBOARD_WINDOWS


def test_shutdown_menu_is_dismissed_before_search(monkeypatch):
	class ModalRpc:
		def __init__(self):
			self.calls = []

		def call(self, method, params=None):
			self.calls.append((method, params))
			return "OK"

	rpc = ModalRpc()
	monkeypatch.setattr(
		umbrella_search_e2e,
		"wait_for_window",
		lambda *_args, **_kwargs: {"id": 10000, "label": "Home"},
	)

	result = umbrella_search_e2e.dismiss_known_startup_window(
		rpc,
		{"id": umbrella_search_e2e.SHUTDOWN_MENU_WINDOW},
		timeout=1,
		transitions=[],
	)

	assert result["id"] == 10000
	assert rpc.calls == [("Input.Back", None)]


def test_known_pvr_info_dialog_is_dismissed(monkeypatch):
	class ModalRpc:
		def __init__(self):
			self.calls = []

		def call(self, method, params=None):
			self.calls.append((method, params))
			if method == "XBMC.GetInfoLabels":
				return {"Control.GetLabel(1)": "No PVR add-on enabled"}
			return "OK"

	rpc = ModalRpc()
	monkeypatch.setattr(
		umbrella_search_e2e,
		"wait_for_window",
		lambda *_args, **_kwargs: {"id": 10000, "label": "Home"},
	)

	result = umbrella_search_e2e.dismiss_known_startup_window(
		rpc,
		{"id": umbrella_search_e2e.OK_DIALOG_WINDOW},
		timeout=1,
		transitions=[],
	)

	assert result["id"] == 10000
	assert [method for method, _params in rpc.calls] == [
		"XBMC.GetInfoLabels",
		"Input.Select",
	]


def test_unexpected_ok_dialog_is_not_dismissed():
	class ModalRpc:
		def __init__(self):
			self.calls = []

		def call(self, method, params=None):
			self.calls.append((method, params))
			return {"Control.GetLabel(1)": "Resolver failed"}

	rpc = ModalRpc()
	window = {"id": umbrella_search_e2e.OK_DIALOG_WINDOW}

	assert umbrella_search_e2e.dismiss_known_startup_window(
		rpc, window, timeout=1, transitions=[]
	) == window
	assert [method for method, _params in rpc.calls] == [
		"XBMC.GetInfoLabels"
	]


def test_known_pvr_dialog_can_use_android_back_fallback(monkeypatch):
	class ModalRpc:
		def call(self, method, params=None):
			assert method == "XBMC.GetInfoLabels"
			return {"Control.GetLabel(1)": "No PVR add-on enabled"}

	calls = []
	monkeypatch.setattr(
		umbrella_search_e2e,
		"wait_for_window",
		lambda *_args, **_kwargs: {"id": 10000, "label": "Home"},
	)

	result = umbrella_search_e2e.dismiss_known_startup_window(
		ModalRpc(),
		{"id": umbrella_search_e2e.OK_DIALOG_WINDOW},
		timeout=1,
		transitions=[],
		modal_back=lambda: calls.append("back"),
	)

	assert result["id"] == 10000
	assert calls == ["back"]


def test_submit_keyboard_waits_for_done_before_selecting():
	class KeyboardRpc:
		def __init__(self):
			self.calls = []
			self.probes = 0

		def call(self, method, params=None):
			self.calls.append((method, params))
			if method == "GUI.GetProperties":
				self.probes += 1
				return {
					"currentwindow": {"id": 10103},
					"currentcontrol": {
						"label": "Done" if self.probes == 2 else ""
					},
				}
			return "OK"

	rpc = KeyboardRpc()
	umbrella_search_e2e.submit_keyboard(rpc, "Sintel", timeout=1)

	assert [method for method, _params in rpc.calls] == [
		"Input.SendText",
		"GUI.GetProperties",
		"GUI.GetProperties",
		"Input.Select",
	]


def test_run_search_retries_transient_directory_initialization(monkeypatch):
	class FlakyRpc:
		def __init__(self):
			self.directory_calls = 0

		def call(self, method, params=None):
			assert method == "Files.GetDirectory"
			self.directory_calls += 1
			if self.directory_calls == 1:
				raise umbrella_search_e2e.JsonRpcError(
					method, {"code": -32602, "message": "Invalid params."}
				)
			return {"files": [{"label": "Sintel (2010)"}]}

	rpc = FlakyRpc()
	monkeypatch.setattr(
		umbrella_search_e2e,
		"wait_for_window",
		lambda *_args, **_kwargs: {"id": umbrella_search_e2e.VIDEOS_WINDOW},
	)
	monkeypatch.setattr(
		umbrella_search_e2e,
		"activate_home",
		lambda *_args, **_kwargs: {"id": 10000},
	)
	monkeypatch.setattr(
		umbrella_search_e2e,
		"open_search_keyboard",
		lambda *_args, **_kwargs: {"id": 10103},
	)
	monkeypatch.setattr(
		umbrella_search_e2e, "submit_keyboard", lambda *_args, **_kwargs: None
	)
	monkeypatch.setattr(
		umbrella_search_e2e,
		"current_window",
		lambda *_args, **_kwargs: {"id": umbrella_search_e2e.VIDEOS_WINDOW},
	)
	monkeypatch.setattr(umbrella_search_e2e.time, "sleep", lambda _delay: None)

	result = umbrella_search_e2e.run_search(rpc, "Sintel", timeout=1)

	assert result["matches"] == ["Sintel (2010)"]
	assert rpc.directory_calls == 2
