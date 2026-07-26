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
