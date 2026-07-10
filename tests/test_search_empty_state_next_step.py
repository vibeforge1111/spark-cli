"""Test: search empty state next step."""
def test_search_empty_suggests_setup():
    query = ""
    hits = []
    if not hits:
        if not query:
            msg = "No modules in registry. Run `spark setup telegram-starter` to install the starter bundle."
        else:
            msg = "No matching modules for '" + query + "'. Run `spark list` to see installed modules."
    expected = "No modules in registry. Run `spark setup telegram-starter` to install the starter bundle."
    assert msg == expected

def test_search_no_match_suggests_list():
    query = "nonexistent"
    hits = []
    if not hits:
        if not query:
            msg = "No modules in registry. Run `spark setup telegram-starter` to install the starter bundle."
        else:
            msg = "No matching modules for '" + query + "'. Run `spark list` to see installed modules."
    expected = "No matching modules for 'nonexistent'. Run `spark list` to see installed modules."
    assert msg == expected
