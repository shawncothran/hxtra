"""The features page (web/features.html): the README's and docs' links reach its sections, and its demos and icons load."""
import json
import re
import shutil
import subprocess
from html.parser import HTMLParser
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "web" / "features.html"
URL = "https://wisemandenny.github.io/hxtra/web/features.html"


def page():
    return PAGE.read_text()


def ids():
    return set(re.findall(r'\bid="([^"]+)"', page()))


def test_links_to_the_page_reach_a_section():
    docs = [ROOT / "README.md", ROOT / "CONTRIBUTING.md", *(ROOT / "docs").glob("*.md")]
    broken = [f"{d.name}: #{a}" for d in docs for a in re.findall(re.escape(URL) + r"#([\w-]+)", d.read_text())
              if a not in ids()]
    assert not broken


def test_readme_watch_demo_badges_link_to_the_page():
    readme = (ROOT / "README.md").read_text()
    badges = re.findall(r'<a href="([^"]+)"><img src="docs/assets/icons/watch-demo.svg"', readme)
    assert len(badges) == readme.count("watch-demo.svg") > 0
    assert all(b.startswith(URL + "#") for b in badges)
    assert "<details>" not in readme


def test_page_files_exist():
    # Pages publishes docs/assets beside web/, so ../docs/assets resolves there as in a checkout.
    missing = [s for s in re.findall(r'src="([^":]+)"', page()) if not (PAGE.parent / s).resolve().exists()]
    assert not missing


def test_every_demo_slot_has_sized_media():
    # Sized media keep the layout still while the demos load, so an anchor lands on its section.
    slots = re.findall(r'<!-- demo: [^>]*-->\n\s*<div class="demos[^"]*">(.*?)</div>', page(), re.S)
    assert len(slots) == page().count("<!-- demo:") > 0
    for slot in slots:
        media = re.findall(r"<(?:img|video)\s+[^>]*>", slot)
        assert media and all(re.search(r'width="\d+"', m) and re.search(r'height="\d+"', m) for m in media)


def test_every_feature_card_ends_with_its_settings():
    cards = re.findall(r'<section class="card feat" id="[\w-]+">(.*?)</section>', page(), re.S)
    assert cards
    for card in cards:
        settings = card.rfind('<div class="settings">')
        assert settings >= 0 and "<table>" not in card[:settings]


class _Strings(HTMLParser):
    """Each data-i18n element's inner HTML, and each data-i18n-alt image's alt text."""
    VOID = {"img", "br", "source", "input", "meta", "link"}

    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.stack, self.strings = [], {}

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        for e in self.stack:
            e[1].append(self.get_starttag_text())
        if "data-i18n-alt" in a:
            self.strings[a["data-i18n-alt"]] = a["alt"]
        if tag not in self.VOID:
            self.stack.append([a.get("data-i18n"), []])

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        key, inner = self.stack.pop()
        if key:
            self.strings[key] = "".join(inner)
        for e in self.stack:
            e[1].append(f"</{tag}>")

    def handle_data(self, d):
        for e in self.stack:
            e[1].append(d)

    def handle_entityref(self, name):
        self.handle_data(f"&{name};")

    def handle_charref(self, name):
        self.handle_data(f"&#{name};")


def english():
    """Each data-i18n key's English, as the page holds it."""
    body = page().split("<body>")[1].split("<script")[0]
    p = _Strings()
    p.feed(body)
    p.strings["doc.title"] = re.search(r"<title>(.*)</title>", page()).group(1)
    return p.strings


def langs():
    if shutil.which("node") is None:
        pytest.skip("node is needed to parse the page's JavaScript translations")
    source = page().split("// LANGS-BEGIN", 1)[1].split("// LANGS-END", 1)[0]
    result = subprocess.run(
        ["node", "-e", 'const vm = require("vm"), fs = require("fs"); '
         'const context = {}; vm.runInNewContext(fs.readFileSync(0, "utf8"), context); '
         'process.stdout.write(JSON.stringify(context.LANGS));'],
        input=source, text=True, capture_output=True, check=True)
    return json.loads(result.stdout)


def tags(text):
    class Tags(HTMLParser):
        def __init__(self):
            super().__init__()
            self.items = []

        def handle_starttag(self, tag, attrs):
            self.items.append((tag, tuple(sorted(attrs))))

        def handle_endtag(self, tag):
            if tag not in _Strings.VOID:
                self.items.append((f"/{tag}", ()))

    parser = Tags()
    parser.feed(text)
    return parser.items


def test_every_language_has_every_string_with_the_same_tags():
    en, data = english(), langs()
    names = re.findall(r"(\w+): \"", page().split("var LANG_NAMES = {")[1].split("};")[0])
    assert sorted(data) == sorted(n for n in names if n != "en")
    for code, strings in data.items():
        assert sorted(strings) == sorted(en), f"{code}: keys differ from the page's"
        bad = [k for k in en if tags(strings[k]) != tags(en[k])]
        assert not bad, f"{code}: tags differ in {bad}"


def test_language_names_match_the_setup_page():
    names = lambda html: re.findall(r'(\w+): "([^"]+)"', html.split("var LANG_NAMES = {")[1].split("};")[0])
    assert names(page()) == names((ROOT / "web" / "index.html").read_text())
