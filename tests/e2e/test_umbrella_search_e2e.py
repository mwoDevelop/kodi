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


def test_keyboard_window_ids_cover_kodi_omega_variants():
	assert 10103 in umbrella_search_e2e.KEYBOARD_WINDOWS
	assert 10138 in umbrella_search_e2e.KEYBOARD_WINDOWS
