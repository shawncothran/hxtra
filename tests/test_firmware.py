"""The whole build from the stock HX Stomp 3.80.0 .hxf (not in the repo: point HX_STOMP_HXF
at your copy). The build is deterministic, so the output's
MD5 is pinned: a change to any byte of the firmware fails here until BUILT_MD5
is updated on purpose."""
import hashlib
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

import features
import l6ia
import patch_amp as pa
import patch_menu as pm
import patch_click
import patch_gate
import patch_sidechain
import patch_usbmon
import setting_ids

ROOT = Path(__file__).resolve().parent.parent
pytestmark = pytest.mark.firmware

# The ten-knob NAM A2 Lite with its tone stack in Amp > NAM on Xenomorph Fuzz Mono's ID 555 (build.py's STEPS),
# the kernel's --mid-sweep, DSP cost 2275, tools/patch_menu.py's HXtra entry and boot screen.
BUILT_MD5 = {
    "HX_STOMP_HXF": "a070c1ddaf5d656d195f16d3e784a540",
}
STOMP_FEATURE_ENTRY0_MD5 = {
    "HX_BPM": "6eb9bbfb5b1afc7864f3fcf24a7b4f39",
    "HX_BREATHING_LINE": "b698e5193a9348fbf79ff0ef61a0a986",
    "HX_DSP_METER": "5a8d5d23ce0b950187450fd7dd6b1534",
    "HX_LONG_PRESS": "49a87320e5d0e33280f2e18a83046ac8",
    "HX_MORE_SNAPSHOTS": "caf5da5bc140e6c990c47bb6765b1378",
    "HX_TAP_COMMAND": "4f8090ee16b389fbcc7202c872f9ddac",
    "all": "0d7185a50d207f5c1a285673ca279752",
}


def test_stomp_xl_shares_dsp_entries():
    paths = [os.environ.get(name) for name in ("HX_STOMP_HXF", "HX_STOMP_XL_HXF")]
    if not all(paths):
        pytest.skip("set HX_STOMP_HXF and HX_STOMP_XL_HXF to the stock 3.80.0 files")
    for path, expected in zip(paths, ("a2cd8f4ae56f49415380270ebc484bf1", "329e3a26d60d3de1988b6785fa833ee1")):
        assert hashlib.md5(Path(path).read_bytes()).hexdigest() == expected
    stomp, xl = (pa.load_l6ia_from_any(path)[0] for path in paths)
    for entry in (2, 3, 4):
        assert pa.get_entry_swapped(stomp, entry) == pa.get_entry_swapped(xl, entry), f"Entry {entry} differs"
    assert pa.get_entry_swapped(stomp, 0) != pa.get_entry_swapped(xl, 0)


def test_xl_features_preserve_stomp_entry0():
    stock = os.environ.get("HX_STOMP_HXF")
    if not stock:
        pytest.skip("HX_STOMP_HXF is not set")
    archive = pa.load_l6ia_from_any(stock)[0]
    load = lambda index: pa.get_entry_swapped(archive, index)
    mods, ids = features.load(), setting_ids.by_name()
    for flag, expected in STOMP_FEATURE_ENTRY0_MD5.items():
        flags = {name: "1" for name in STOMP_FEATURE_ENTRY0_MD5 if name != "all"} if flag == "all" else {flag: "1"}
        entry0, _ = pm.menu_entry0(load(0), mods, flags, ids, others=load)
        assert hashlib.md5(entry0).hexdigest() == expected, f"Stomp Entry 0 changed with {flag}"


def test_xl_ported_features_build_together(tmp_path):
    stock = os.environ.get("HX_STOMP_XL_HXF")
    if not stock:
        pytest.skip("HX_STOMP_XL_HXF is not set")
    archive = pa.load_l6ia_from_any(stock)[0]
    flags = {"HX_TUNER": "1", "HX_LABEL_COLOR": "1", "HX_REAL_NAMES": "1", "HX_USB_MONITOR": "1"}
    entries, enabled = pm.menu_entries(lambda index: pa.get_entry_swapped(archive, index),
                                       features.load(), flags, layout=pm.XL_MENU)
    assert {features.name(feature) for feature in enabled} == {"label_color", "real_names", "splash", "tuner", "usb_monitor"}
    image = l6ia.rebuild_archive(archive, entries)[0]
    image = patch_usbmon.patch_dsp(image, log=lambda *_: None)
    output = tmp_path / "xl.l6ia"
    output.write_bytes(image)
    result = subprocess.run([sys.executable, str(ROOT / "tools/l6ia_verify.py"), str(output)], capture_output=True, text=True)
    assert result.returncode == 0 and "ALL OK" in result.stdout, result.stdout + result.stderr


def test_xl_nam_and_ported_features_build_together(tmp_path, monkeypatch):
    stock = os.environ.get("HX_STOMP_XL_HXF")
    if not stock:
        pytest.skip("HX_STOMP_XL_HXF is not set")
    spec = importlib.util.spec_from_file_location("hxtra_build", ROOT / "build.py")
    build = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build)
    flags = {"HX_NAM_SLOTS": "2", "HX_TUNER": "1", "HX_LABEL_COLOR": "1", "HX_REAL_NAMES": "1", "HX_USB_MONITOR": "1", "HX_CLICK": "1",
             "HX_FX_GATE": "1", "HX_GATE_SC": "1"}
    for name in tuple(os.environ):
        if name.startswith("HX_"):
            monkeypatch.delenv(name)
    for name, value in flags.items():
        monkeypatch.setenv(name, value)

    def run(*args):
        result = subprocess.run([sys.executable, *map(str, args)], cwd=ROOT, capture_output=True, text=True)
        assert result.returncode == 0, result.stdout + result.stderr
        return result.stdout

    asm = tmp_path / "nam.asm"
    run(*build.kernel("HX_Stomp_XL", 2), "-o", asm)
    source = Path(stock)
    for index, step in enumerate(build.NAM_EQ + [["model-int"]]):
        output = tmp_path / f"model-{index}.l6ia"
        run("tools/patch_amp.py", step[0], source, output, *step[1:])
        source = output
    archive = source.read_bytes()
    entries, enabled = pm.menu_entries(lambda index: pa.get_entry_swapped(archive, index),
                                       features.load(), flags, layout=pm.XL_MENU)
    assert {features.name(feature) for feature in enabled} == {
        "label_color", "real_names", "splash", "tuner", "usb_monitor", "metronome", "fx_gate", "gate_sidechain"}
    menu = tmp_path / "menu.l6ia"
    menu.write_bytes(l6ia.rebuild_archive(archive, entries)[0])
    kernel = tmp_path / "kernel.l6ia"
    run("tools/patch_amp.py", "patch", menu, kernel, "--asm", asm)
    image = patch_click.add_click(kernel.read_bytes(), log=lambda *_: None)[0]
    image = patch_gate.patch_gate(patch_gate.patch_dsp(image, log=lambda *_: None), log=lambda *_: None)
    image = patch_sidechain.patch_sidechain(patch_sidechain.patch_dsp(image, log=lambda *_: None), log=lambda *_: None)
    image = patch_usbmon.patch_dsp(image, log=lambda *_: None)
    output = tmp_path / "xl.l6ia"
    output.write_bytes(image)
    info = pa.parse_entry3_full(pa.get_entry_swapped(image, 3))
    assert pa.find_model(info, "HD2_DistNAMLite")
    assert pa.find_model(info, patch_click.NAME)
    assert "ALL OK" in run("tools/l6ia_verify.py", output, "--e3-max", hex(build.E3_MAX))


@pytest.mark.parametrize("env", BUILT_MD5)
def test_build(tmp_path, env):
    stock = os.environ.get(env)
    if not stock:
        pytest.skip(f"{env} is not set")
    out = tmp_path / "out.hxf"
    r = subprocess.run([sys.executable, str(ROOT / "build.py"), stock, "-o", str(out), "--no-check"],
                       capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "ALL OK" in r.stdout
    assert hashlib.md5(out.read_bytes()).hexdigest() == BUILT_MD5[env]
