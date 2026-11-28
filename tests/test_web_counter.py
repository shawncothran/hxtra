"""web/index.html's anonymous usage counts (GoatCounter): what each event sends, that it stays off
outside the live page and under Do Not Track / Global Privacy Control, and that no event carries a
file, a file name or a unit ID."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

PAGE = (Path(__file__).resolve().parent.parent / "web/index.html").read_text()
needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")


def snippet(start, end):
    i = PAGE.index(start)
    return PAGE[i:PAGE.index(end, i)]


TRACKER = snippet('  var COUNTER = ', '  function markDone(n) {')
COUNT_BUILD = snippet('  function countBuild(b) {', '  function slotsPicked() {')


def run(js, host="wisemandenny.github.io", dnt=None, gpc=False, referrer="", search=""):
    """Runs the page's tracker in node with a fake browser; returns each fetch as [url, options]."""
    env = f"""
var sent = [];
var location = {{ hostname: {json.dumps(host)}, origin: "https://" + {json.dumps(host)}, search: {json.dumps(search)} }};
var navigator = {{ doNotTrack: {json.dumps(dnt)}, globalPrivacyControl: {json.dumps(gpc)} }};
var document = {{ referrer: {json.dumps(referrer)} }};
var screen = {{ width: 1440, height: 900 }};
var window = {{ devicePixelRatio: 2 }};
function fetch(url, opts) {{ sent.push([url, opts]); return Promise.resolve(); }}
var lang = "de", release = "v1.2.0";
"""
    # a function scope, since node has its own global navigator
    script = "(function () {" + env + TRACKER + COUNT_BUILD + js + "\nconsole.log(JSON.stringify(sent));\n})();"
    r = subprocess.run(["node", "-e", script],
                       capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


def query(url):
    assert url.startswith("https://hxtra.goatcounter.com/count?")
    q = url.split("?", 1)[1]
    assert re.search(r"&rnd=[0-9a-z]+$", q)
    return re.sub(r"&rnd=[0-9a-z]+$", "", q)


@needs_node
def test_event_sends_only_its_name():
    (url, opts), = run('countEvent("build/gr-on");')
    assert query(url) == "p=build%2Fgr-on&e=true"
    assert opts == {"mode": "no-cors", "cache": "no-store", "credentials": "omit",
                    "referrerPolicy": "no-referrer", "keepalive": True}


@needs_node
@pytest.mark.parametrize("kw", [{"host": "localhost"}, {"host": "127.0.0.1"}, {"dnt": "1"}, {"gpc": True}])
def test_nothing_sent_off_the_live_page_or_when_asked_not_to_track(kw):
    assert run('countEvent("build"); countVisit();', **kw) == []


@needs_node
def test_visit_sends_screen_and_only_the_referring_site():
    (url, _), = run("countVisit();", referrer="https://www.reddit.com/r/Line6Helix/comments/abc?utm_source=x")
    assert query(url) == "p=%2Fweb%2F&s=1440,900,2&r=https%3A%2F%2Fwww.reddit.com"


@needs_node
def test_visit_from_the_page_itself_has_no_referrer():
    (url, _), = run("countVisit();", referrer="https://wisemandenny.github.io/hxtra/web/#build")
    assert query(url) == "p=%2Fweb%2F&s=1440,900,2"


@needs_node
def test_build_counts_every_choice_on_and_off():
    sent = run('countBuild({ pinned: true, slots: 2, choices: [{ name: "gr", on: true }, '
               '{ name: "click", on: false }, { name: "real-names", on: true }] });')
    names = [re.match(r"p=([^&]*)&e=true$", query(u)).group(1).replace("%2F", "/").replace("%2B", "+") for u, _ in sent]
    assert names == ["build", "build/verified", "build/nam-2", "build/gr-on", "build/click-off",
                     "build/real-names-on", "build/set/nam-2+gr+real-names", "build/lang-de", "build/v1.2.0"]


def test_download_counts_each_build_once():
    click = snippet('$("fwSave").addEventListener("click"', "});")
    assert re.search(r"if \(!built\.counted\)\s*\{\s*built\.counted = true;\s*countBuild\(built\);\s*\}", click)


def test_choices_are_taken_when_the_build_starts():
    assert 'var picked = { choices: choices(), slots: dsp ? slotsPicked() : 3 };' in PAGE
    assert re.search(r"choices: picked\.choices,\s*slots: picked\.slots,\s*pinned: m\.pinned,?\s*};", PAGE)


def test_no_event_carries_a_file_or_unit():
    calls = re.findall(r"countEvent\((.*?)\);", PAGE)
    assert len(calls) >= 10
    for c in calls:
        assert not re.search(r"file|md5|unit|\.text|message|\.info|\.wav", c), c


@needs_node
@pytest.mark.parametrize("kw", [{}, {"host": "example.com"}, {"host": "localhost"}, {"host": "127.0.0.1"},
                                {"host": "localhost", "dnt": "1"}, {"host": "127.0.0.1", "gpc": True}])
def test_test_switch_counts_under_test(kw):
    (e, _), (v, _) = run('countEvent("build/gr-on"); countVisit();', search="?lang=de&count=test", **kw)
    assert query(e) == "p=test%2Fbuild%2Fgr-on&e=true"
    assert query(v) == "p=%2Ftest%2Fweb%2F&s=1440,900,2"


@needs_node
@pytest.mark.parametrize("kw", [{"dnt": "1"}, {"gpc": True}, {"host": "example.com", "dnt": "1"}])
def test_test_switch_keeps_dnt_and_gpc_off_a_local_copy(kw):
    """A shared ?count=test link must not count a browser that asked not to be tracked."""
    assert run('countEvent("build/gr-on"); countVisit();', search="?count=test", **kw) == []


@needs_node
@pytest.mark.parametrize("search", ["?count=testing", "?count=tes", "?recount=test"])
def test_only_the_exact_test_switch_counts_off_the_live_page(search):
    assert run('countEvent("build");', host="localhost", search=search) == []
