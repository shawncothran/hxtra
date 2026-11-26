"""web/firmware-worker.js, the in-browser build.py: it accepts the same Stomp and XL stock files,
pins the same known built MD5s, and loads every file the build reads; with HX_STOMP_HXF set, its
copy of the repository builds the features from a release's M4 code (tools/m4cache.py) as
the repository does with clang."""
import ast
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import types
from html.parser import HTMLParser
from pathlib import Path

import pytest

import block3
import features
import m4asm
import m4cache

ROOT = Path(__file__).resolve().parent.parent
WORKER = (ROOT / "web/firmware-worker.js").read_text()


def js_object(name):
    return js_value(name)


def py_dict(path, name):
    """A module-level value of literals, or of names of such values assigned before it."""
    tree = ast.parse((ROOT / path).read_text())
    env = {}
    for n in tree.body:
        if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name):
            try:
                env[n.targets[0].id] = eval(compile(ast.Expression(n.value), path, "eval"), {"__builtins__": {}}, dict(env))
            except Exception:
                continue
            if n.targets[0].id == name:
                return env[name]
    raise KeyError(name)


# The stock HX Effects 3.80.0 file, which upstream builds and HXtra refuses
NOT_SUPPORTED = {"7c2ebdf1bffb6bcc5f89dda97f91e40c": "HX_Effects"}


def test_stock_md5_as_build_py():
    assert js_object("STOCK_MD5") == py_dict("build.py", "STOCK_MD5")


def test_stomp_and_xl_profiles():
    assert py_dict("build.py", "STOCK_MD5") == {
        "a2cd8f4ae56f49415380270ebc484bf1": "HX_Stomp",
        "329e3a26d60d3de1988b6785fa833ee1": "HX_Stomp_XL",
    }
    assert set(py_dict("build.py", "KERNEL")) == set(py_dict("build.py", "STEPS")) == {"HX_Stomp", "HX_Stomp_XL"}
    assert not NOT_SUPPORTED.keys() & js_object("STOCK_MD5").keys()
    assert set(js_object("BUILT_MD5")) == {"HX_Stomp"}
    assert js_value("KERNEL") == py_dict("build.py", "KERNEL")
    assert js_value("STEPS") == py_dict("build.py", "STEPS")
    assert "HX_Effects" not in WORKER and "--effects" not in WORKER


def test_worker_refuses_another_file_as_the_page_expects():
    # the page shows fw.wrongText for an error with "not the stock" in it
    refusal = re.search(r'throw new Error\(\s*"(This is not the stock[^"]*)"', WORKER).group(1)
    assert "HX Stomp or HX Stomp XL" in refusal
    assert "/not the stock/.test(m.text)" in (ROOT / "web/index.html").read_text()


@pytest.mark.parametrize("md5", [*NOT_SUPPORTED, None], ids=[*NOT_SUPPORTED.values(), "other"])
def test_build_py_refuses_another_unit(tmp_path, monkeypatch, md5):
    spec = importlib.util.spec_from_file_location("hxtra_build", ROOT / "build.py")
    build = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build)
    stock = tmp_path / "stock.hxf"
    stock.write_bytes(b"not firmware")
    if md5:
        monkeypatch.setattr(build.hashlib, "md5", lambda b: types.SimpleNamespace(hexdigest=lambda: md5))
    md5 = md5 or hashlib.md5(b"not firmware").hexdigest()
    monkeypatch.setattr(build, "run", lambda *a: pytest.fail(f"ran {a[1:]}"))
    monkeypatch.setattr(sys, "argv", ["build.py", str(stock), "-o", str(tmp_path / "out.hxf"), "--no-check"])
    with pytest.raises(SystemExit) as e:
        build.main()
    assert f"MD5 {md5}, not stock HX Stomp or HX Stomp XL 3.80.0 firmware" in str(e.value)
    assert not (tmp_path / "out.hxf").exists()


@pytest.mark.parametrize("slots", [0, 2])
def test_build_xl_uses_the_xl_menu_and_selected_nam_slots(tmp_path, monkeypatch, slots):
    spec = importlib.util.spec_from_file_location("hxtra_build_xl", ROOT / "build.py")
    build = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build)
    stock = tmp_path / "stock-xl.hxf"
    stock.write_bytes(b"not firmware")
    xl_md5 = "329e3a26d60d3de1988b6785fa833ee1"
    monkeypatch.setattr(build.hashlib, "md5", lambda _data: types.SimpleNamespace(hexdigest=lambda: xl_md5))
    monkeypatch.setenv("HX_NAM_SLOTS", str(slots))
    monkeypatch.setattr(build.os, "replace", lambda *_args: None)
    monkeypatch.setattr(build.os, "remove", lambda *_args: None)
    ran = []

    def run(*args):
        ran.append(args[1:])
        return "ALL OK"

    monkeypatch.setattr(build, "run", run)
    monkeypatch.setattr(sys, "argv", ["build.py", str(stock), "-o", str(tmp_path / "xl.hxf"), "--no-check"])
    build.main()
    menu = next(args for args in ran if args[0] == "tools/patch_menu.py")
    assert menu[-2:] == ("--device", "HX_Stomp_XL")
    assert any("nam_multi.py" in arg for args in ran for arg in args) == (slots > 0)
    assert any(args[:2] == ("tools/patch_amp.py", "patch") for args in ran) == (slots > 0)
    assert ran[-1][:2] == ("tools/hxf.py", "pack")
    assert Path(ran[-1][2]).name == "nam_lite.l6ia" and Path(ran[-1][3]).name == "xl.hxf"


def js_value(name):
    """Read the worker's build constants as JavaScript values."""
    if shutil.which("node") is None:
        pytest.skip("node is needed to parse the worker's JavaScript constants")
    source = WORKER.split("var SOURCES", 1)[0]
    result = subprocess.run(
        ["node", "-e", 'const vm = require("vm"), fs = require("fs"); '
         'const context = {}; vm.runInNewContext(fs.readFileSync(0, "utf8"), context); '
         'process.stdout.write(JSON.stringify(context[process.argv[1]]));', name],
        input=source, text=True, capture_output=True, check=True)
    return json.loads(result.stdout)


def test_build_steps_as_build_py():
    for name in ("KERNEL", "STEPS"):
        assert js_value(name) == py_dict("build.py", name), name
    assert int(re.search(r"var E3_MAX = (\w+);", WORKER).group(1), 0) == py_dict("build.py", "E3_MAX")


def test_kernel_slots_as_build_py():
    # build.py's kernel(unit, slots): "--slots" for fewer than 3, nothing for 3
    assert 'KERNEL[unit].concat(slots === 3 ? [] : ["--slots", String(slots)]' in WORKER
    spec = importlib.util.spec_from_file_location("hxtra_build", ROOT / "build.py")
    build = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build)
    assert build.kernel("HX_Stomp", 3) == build.KERNEL["HX_Stomp"]
    assert build.kernel("HX_Stomp", 2) == build.KERNEL["HX_Stomp"] + ["--slots", "2"]


def test_built_md5_as_firmware_test():
    pinned = py_dict("tests/test_firmware.py", "BUILT_MD5")
    assert js_object("BUILT_MD5") == {"HX_Stomp": pinned["HX_STOMP_HXF"]}


def test_sources_cover_the_build():
    listed = set(listed_sources())
    assert all((ROOT / p).is_file() for p in listed)
    # every module the build's scripts import, and every file they open next to themselves
    need = {"tools/hxf.py", "tools/l6ia.py", "tools/l6ia_verify.py", "tools/patch_amp.py", "tools/kit_patch_amp.py",
            "tools/sharc/nam_lite.py",
            "tools/sharc/nam_multi.py", "tools/sharc/nam_multi_kernel.asm",
            *(f"tools/features/{f.name}" for f in (ROOT / "tools/features").glob("*.py")),
            "tools/patch_click.py", "build.py", "src/sharc/click.asm",      # the Metronome: patch_click.py reads both
            "tools/patch_gate.py", "src/sharc/fx_gate.asm",                 # the gate in the FX Loop and Return blocks
            "tools/patch_sidechain.py", "src/sharc/gate_sc.asm",            # the Noise Gate's Input Sidechain
            "tools/patch_comp.py", "src/sharc/frame_probe.asm"}             # the GR meter's knobs and DSP code
    for d in ("tools", "tools/sharc"):
        for f in listed:
            if not f.endswith(".py"):
                continue
            for mod in re.findall(r"^\s*import (\w+)", (ROOT / f).read_text(), re.M):
                if (ROOT / d / f"{mod}.py").is_file():
                    need.add(f"{d}/{mod}.py")
            for name in re.findall(r"""['"](\w+\.(?:json|asm))['"]""", (ROOT / f).read_text()):
                if (ROOT / d / name).is_file() and d == str(Path(f).parent):
                    need.add(f"{d}/{name}")
    assert need - {"tools/sharc/nam_a2.asm"} <= listed


def listed_sources():
    return re.findall(r'"((?:tools/|src/)?[\w/.]+\.\w+)"', WORKER.split("var SOURCES")[1].split("];")[0])


def test_sources_have_every_m4_source():
    # m4asm.key hashes every source next to a module, so the page needs all of them, as at the release
    m4 = {f"src/m4/{f.name}" for f in (ROOT / "src/m4").iterdir() if f.suffix in m4asm.SOURCE_TYPES}
    assert {p for p in listed_sources() if p.startswith("src/m4/")} == m4


class PageInputs(HTMLParser):
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}

    def __init__(self):
        super().__init__()
        self.stack, self.inputs, self.elements = [], [], []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.elements.append((tag, attrs))
        if tag == "input":
            self.inputs.append((attrs, [item[1] for item in self.stack]))
        if tag not in self.VOID:
            self.stack.append((tag, attrs))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag not in self.VOID:
            assert self.stack.pop()[0] == tag


def parsed_page():
    parser = PageInputs()
    parser.feed((ROOT / "web/index.html").read_text())
    return parser


def page_inputs():
    return parsed_page().inputs


def test_page_lists_the_web_options():
    # opt-in features: a checkbox each, hidden until the release's cache offers it, unticked
    boxes = [(attrs, parent) for attrs, parents in page_inputs() for parent in parents if "data-option" in parent]
    assert sorted(parent["data-option"] for _, parent in boxes) == sorted(m4cache.web_options())
    assert all(attrs.get("type") == "checkbox" and "checked" not in attrs and "hidden" in parent for attrs, parent in boxes)


def page_dsp():
    """The DSP features' boxes ({flag: ticked}), the NAM slot counts (the one picked first) and whether NAM's box is ticked."""
    inputs = page_inputs()
    boxes = {parent["data-dsp"]: "checked" in attrs for attrs, parents in inputs for parent in parents
             if "data-dsp" in parent and attrs.get("type") == "checkbox" and "hidden" in parent}
    slots = [("checked" in attrs, int(attrs["value"])) for attrs, _ in inputs if attrs.get("name") == "slots"]
    nam, = [attrs for attrs, _ in inputs if attrs.get("id") == "namOn"]
    return boxes, sorted(slots, reverse=True), "checked" in nam


def test_page_lists_the_dsp_features_and_slot_counts():
    import block3
    # NAM's box unticked is 0 slots, the radios the rest
    boxes, slots, _ = page_dsp()
    assert sorted(boxes) == sorted(m4cache.web_dsp())
    assert sorted([v for _, v in slots] + [0]) == sorted(block3.SLOTS)


def test_page_default_is_two_nam_slots_and_every_dsp_feature_and_fits():
    # The default (issue #111): 2 NAM slots with the GR meter, the Metronome and the FX Loop gate
    import block3
    boxes, slots, nam = page_dsp()
    picked = slots[0][1]
    assert nam and slots[0][0] and not slots[1][0] and picked == 2
    assert all(boxes.values())
    assert block3.fits(picked, [f for f, on in boxes.items() if on])


def test_download_is_named_by_the_release():
    # the built file downloads as "HXtra_v1.2.0.hxf", the page names it the same before the build, and no copy names the old file
    page = (ROOT / "web/index.html").read_text()
    assert re.search(r'var name\s*=\s*"HXtra"\s*\+\s*\(unit === "HX_Stomp_XL" \? "_XL" : ""\)', WORKER)
    assert 'function firmwareName()' in page and 'device === "HX_Stomp_XL" ? "_XL" : ""' in page
    assert re.search(r'post\(\s*\{\s*type: "done",\s*unit: unit,\s*file: name,', WORKER)
    assert '$("fwName").textContent = firmwareName();' in page
    assert "_HXtra.hxf" not in page
    assert page.count("<code>HXtra</code>") == len(re.findall(r'"faq\.a5":', page))


def test_page_anchors_are_readable():
    # every section a link can land on is named in words, and each step's nav link points at one
    elements = parsed_page().elements
    sections = [attrs["id"] for tag, attrs in elements if tag == "section" and "step" in attrs.get("class", "").split()]
    nav = [attrs["href"][1:] for tag, attrs in elements if tag == "a" and re.fullmatch(r"nav\d+", attrs.get("id", ""))]
    assert all(re.fullmatch(r"[a-z]+(-[a-z]+)*", s) for s in sections), sections
    assert nav and set(nav) <= set(sections)


def test_page_moves_old_anchors_to_their_names():
    # #s1..#s6 from links shared before the steps were named go to the step's section, as numbered then
    # (Select features, step 2 since #111, never had one)
    page = (ROOT / "web/index.html").read_text()
    old = dict(re.findall(r'(s\d): "([a-z-]+)"', re.search(r"var named = \{(.*?)\}", page, re.S).group(1)))
    nav = {attrs["href"][1:]: attrs["id"][3:] for tag, attrs in parsed_page().elements
           if tag == "a" and re.fullmatch(r"nav\d+", attrs.get("id", ""))}
    assert old == {"s1": "get-ready", "s2": "build", "s3": "try-without-installing", "s4": "install", "s5": "convert-captures",
                   "s6": "play-nam"}
    assert set(old.values()) <= set(nav) and nav["options"] == "2"


def test_site_root_keeps_the_anchor():
    # wisemandenny.github.io/hxtra/#install lands on the page's install step
    site = (ROOT / ".github/workflows/pages.yml").read_text()
    assert 'location.replace("web/" + location.hash)' in site


def page_combo(slots, leave_out=()):
    """The flags of the page's combination with every feature and DSP feature that fits but leave_out, at slots NAM slots."""
    dsp = [f for f in m4cache.web_dsp() if f not in leave_out]
    while not block3.fits(slots, dsp):
        dsp.pop(0)
    return m4cache.web_flags() + dsp + [m4cache.slots_flag(slots)]


# the default selection, then one of each kind the v1.2.0 cache lacked a module for (issue #163)
PAGE_COMBOS = {"default": (2, ()), "no GR": (2, ("HX_GR",)), "no Metronome": (2, ("HX_CLICK",)),
               "no USB Monitor": (2, ("HX_USB_MONITOR",)), "3 NAM slots": (3, ()), "no NAM, no DSP": (0, tuple(m4cache.web_dsp()))}


def test_page_combos_are_offered():
    offered = {m4cache.combo_key(c) for c in m4cache.combos()}
    assert all(m4cache.combo_key(page_combo(*c)) in offered for c in PAGE_COMBOS.values())


def test_xl_cache_offers_only_xl_ported_features_with_nam():
    xl = m4cache.XL_UNIT
    mods = features.load()
    supported = {features.flags(module)[0] for module in mods if features.flags(module)
                 and getattr(module, 'XL_PORTED', False)}
    assert set(m4cache.web_flags(xl) + m4cache.web_options(xl) + m4cache.web_dsp(xl)) <= supported
    assert {'HX_FX_GATE', 'HX_GATE_SC'} <= set(m4cache.web_dsp(xl))
    for offered in (m4cache.web_flags, m4cache.web_options, m4cache.web_dsp):
        assert set(offered(xl)) == set(offered(m4cache.UNIT))
    combos = m4cache.combos(xl)
    assert {m4cache.flag_env(combo)[block3.VAR] for combo in combos} == set(map(str, block3.SLOTS))


def test_release_requires_both_units_for_website_parity():
    result = subprocess.run([sys.executable, str(ROOT / "tools/release.py"), "stock.hxf", "v1.0.0", "--dry-run"],
                            capture_output=True, text=True)
    assert result.returncode == 2
    assert "--xl-stock" in result.stderr and "required" in result.stderr


def test_release_dry_run_writes_both_unit_caches(tmp_path, monkeypatch):
    import release

    monkeypatch.setattr(release, "ROOT", str(tmp_path))
    monkeypatch.setattr(release, "check_version", lambda *_: None)
    monkeypatch.setattr(release, "git", lambda *args: "" if args[0] == "status" or args[0] == "rev-parse" and "-q" in args else "ready")
    monkeypatch.setattr(release.m4cache, "make", lambda stock, tag, unit=m4cache.UNIT: {
        "unit": unit, "stock": stock, "release": tag, "modules": {}, "features": []})
    monkeypatch.setattr(sys, "argv", ["release.py", "stomp.hxf", "v1.0.0", "--xl-stock", "xl.hxf", "--dry-run"])

    release.main()
    stomp = json.loads((tmp_path / "build/m4cache.json").read_text())
    xl = json.loads((tmp_path / "build/m4cache-xl.json").read_text())
    assert (stomp["unit"], stomp["stock"]) == (m4cache.UNIT, "stomp.hxf")
    assert (xl["unit"], xl["stock"]) == (m4cache.XL_UNIT, "xl.hxf")
    assert stomp["release"] == xl["release"] == "v1.0.0"


def test_release_attaches_both_unit_caches(tmp_path, monkeypatch):
    import release

    monkeypatch.setattr(release, "ROOT", str(tmp_path))
    monkeypatch.setattr(release, "check_version", lambda *_: None)
    monkeypatch.setattr(release, "git", lambda *args: (
        "" if args[0] == "status" or args[0] == "rev-parse" and "-q" in args else
        "https://github.com/example/hxtra.git" if args[0] == "remote" else "ready"))
    monkeypatch.setattr(release.m4cache, "make", lambda stock, tag, unit=m4cache.UNIT: {
        "unit": unit, "modules": {}, "features": []})
    calls = []
    monkeypatch.setattr(release.subprocess, "run", lambda command, **kwargs: calls.append((command, kwargs)))
    monkeypatch.setattr(sys, "argv", ["release.py", "stomp.hxf", "v1.0.0", "--xl-stock", "xl.hxf"])

    release.main()
    command, kwargs = calls[0]
    assert command[:4] == ["gh", "release", "create", "v1.0.0"]
    assert command[4:6] == [str(tmp_path / "build/m4cache.json"), str(tmp_path / "build/m4cache-xl.json")]
    assert kwargs["check"] is True


@pytest.mark.parametrize("event, expected", [("release", 1), ("workflow_dispatch", 0)])
def test_pages_requires_xl_cache_for_new_releases(event, expected):
    site = (ROOT / ".github/workflows/pages.yml").read_text()
    block = re.search(r'if \[ "\$GITHUB_EVENT_NAME" = "release" \]; then\n(.*?)\n\s*fi', site, re.S)
    assert block and 'm4cache-xl.json' in block.group(1)
    script = 'gh() { return 1; }\n' + block.group(0)
    result = subprocess.run(["sh", "-c", script], env={**os.environ, "GITHUB_EVENT_NAME": event}, capture_output=True)
    assert result.returncode == expected


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
@pytest.mark.parametrize("selected,slots,cache,expected", [
    ("HX_Stomp", 0, True, "not the stock firmware for the selected device"),
    ("HX_Stomp_XL", 1, True, "no build with 1 NAM slots"),
    ("HX_Stomp_XL", 0, False, "no XL feature cache"),
])
def test_worker_rejects_invalid_xl_build_requests(selected, slots, cache, expected):
    script = r"""
const vm = require('vm'), fs = require('fs');
global.self = {postMessage() {}};
vm.runInThisContext(fs.readFileSync(process.argv[1], 'utf8'));
boot = async () => ({FS: {writeFile() {}}, runPython() { return '329e3a26d60d3de1988b6785fa833ee1'; }});
if (process.argv[4] === 'true') caches.HX_Stomp_XL = {features: [], dsp: {features: [], slots: [0], room: {0: 100}, cost: {}}};
build(new ArrayBuffer(1), [], Number(process.argv[3]), process.argv[2]).then(
  () => { process.exitCode = 1; }, error => { console.log(error.message); });
"""
    result = subprocess.run(["node", "-e", script, str(ROOT / "web/firmware-worker.js"), selected, str(slots),
                             str(cache).lower()], capture_output=True, text=True, check=True)
    assert expected in result.stdout


@pytest.mark.firmware
@pytest.mark.parametrize("combo", PAGE_COMBOS)
def test_page_copy_builds_features_from_the_cache(tmp_path, combo):
    stock = os.environ.get("HX_STOMP_HXF")
    if not stock:
        pytest.skip("HX_STOMP_HXF is not set")
    flags = page_combo(*PAGE_COMBOS[combo])
    nam = m4cache.flag_env(flags)[block3.VAR] != "0"
    cache = tmp_path / "m4cache.json"
    cache.write_text(json.dumps({"modules": m4cache.modules(stock, flags, nam)}))      # what m4cache.make keeps for it
    page = tmp_path / "repo"
    for p in listed_sources():
        (page / p).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / p, page / p)
    env = {k: v for k, v in os.environ.items() if not k.startswith("HX_")}
    env.update(m4cache.flag_env(flags))
    base = m4cache.nam_base(stock, str(tmp_path)) if nam else stock     # what build.py, and the page, give patch_menu.py
    out = {}
    for name, root, extra in (("clang", ROOT, {}), ("cache", page, {"HX_M4_CACHE": str(cache)})):
        out[name] = tmp_path / f"{name}.l6ia"
        r = subprocess.run([sys.executable, str(root / "tools/patch_menu.py"), base, str(out[name])],
                           env={**env, **extra}, cwd=root, capture_output=True, text=True)
        assert r.returncode == 0, r.stdout + r.stderr
    assert out["cache"].read_bytes() == out["clang"].read_bytes()


@pytest.mark.firmware
@pytest.mark.parametrize("slots", [0, 2])
def test_xl_page_copy_builds_features_from_the_cache(tmp_path, slots):
    stock = os.environ.get("HX_STOMP_XL_HXF")
    if not stock:
        pytest.skip("HX_STOMP_XL_HXF is not set")
    unit = m4cache.XL_UNIT
    flags = m4cache.web_flags(unit) + m4cache.web_dsp(unit) + [m4cache.slots_flag(slots)]
    cache = tmp_path / "m4cache-xl.json"
    cache.write_text(json.dumps({"modules": m4cache.modules(stock, flags, nam=slots > 0, unit=unit)}))
    page = tmp_path / "repo"
    for path in listed_sources():
        (page / path).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / path, page / path)
    env = {key: value for key, value in os.environ.items() if not key.startswith("HX_")}
    env.update(m4cache.flag_env(flags))
    base = m4cache.nam_base(stock, str(tmp_path), unit) if slots else stock
    outputs = {}
    for name, root, extra in (("clang", ROOT, {}), ("cache", page, {"HX_M4_CACHE": str(cache)})):
        outputs[name] = tmp_path / f"xl-{name}.l6ia"
        result = subprocess.run([sys.executable, str(root / "tools/patch_menu.py"), base, str(outputs[name]),
                                 "--device", unit], env={**env, **extra}, cwd=root, capture_output=True, text=True)
        assert result.returncode == 0, result.stdout + result.stderr
    assert outputs["cache"].read_bytes() == outputs["clang"].read_bytes()


def worker_driver(repo):
    """The worker's DRIVER as Python, with the page's /repo at `repo`."""
    lines = WORKER.split("var DRIVER = [")[1].split('].join("\\n");')[0]
    return "\n".join(ast.literal_eval("[" + lines + "]")).replace("/repo", str(repo))


@pytest.mark.parametrize("script", ["tools/patch_menu.py", "tools/patch_amp.py"])
def test_worker_runs_each_script_with_its_folder_on_sys_path(tmp_path, script):
    # A 0-slot build runs patch_menu.py first, before patch_amp.py had put tools/ on sys.path: "No module named 'features'"
    page = tmp_path / "repo"
    for p in listed_sources():
        (page / p).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / p, page / p)
    code = worker_driver(page) + f"\nprint(run([{script!r}, '--help']).splitlines()[0])"
    r = subprocess.run([sys.executable, "-I", "-c", code], cwd=tmp_path, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.startswith("usage:")


def test_pages_publishes_every_source():
    # the page fetches each of SOURCES from the site, which has only what .github/workflows/pages.yml copies there
    site = ROOT / ".github/workflows/pages.yml"
    copied = [p for line in re.findall(r"^\s*cp -r (.*) _site/", site.read_text(), re.M) for p in line.split()]
    assert [p for p in listed_sources() if not any(p == c or p.startswith(c + "/") for c in copied)] == []
