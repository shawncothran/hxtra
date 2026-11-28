#!/usr/bin/env python3
"""m4cache.py - the M4 code of the web page's features, made at a release for the page, which has no clang.

usage: m4cache.py <HX_Stomp_v3.80.0_0x103966115.hxf> [-o build/m4cache.json] [--release v1.0.0]

Runs the features of tools/patch_menu.py for every combination the page offers (each NAM slot count with each set of DSP
features that fits beside it, tools/block3.py, with each set of the other opt-ins) on the image build.py gives them (the stock
file with NAM A2 Lite added, and without it for HX_NAM_SLOTS=0: the features' code reads addresses in it), keeping what every
module assembled to (keyed by m4asm.key: a module's .inc differs with the other features built). Then it builds each
combination with build.py through those modules, as the page does, to pin its MD5, so a module missing fails here, not on
the page. XL releases have two combinations: every supported feature with two NAM slots, and Real Names off or on.
The page reads the room and the costs from "dsp". tools/release.py attaches the file to the GitHub release, and
the Pages workflow publishes it next to the page; m4asm reads it when HX_M4_CACHE names it.
"""
import argparse
import contextlib
import functools
import hashlib
import importlib.util
import itertools
import json
import os
import subprocess
import sys
import tempfile

import block3
import features
import m4asm
import patch_amp as pa
import patch_menu as pm

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
UNIT = 'HX_Stomp'                   # the features are the HX Stomp's only
XL_UNIT = 'HX_Stomp_XL'


def web_flags(unit=UNIT):
    """The switch of every feature the page always builds (WEB True, the default), in feature order."""
    return _web(True, unit)


def web_options(unit=UNIT):
    """The switch of every feature the page offers as a checkbox, off until ticked (WEB 'opt-in'), in feature order."""
    return _web('opt-in', unit)


def web_dsp(unit=UNIT):
    """The switch of every feature the page offers among its DSP features, off until ticked (WEB 'dsp'), in feature order."""
    return _web('dsp', unit)


def _web(kind, unit=UNIT):
    return [features.flags(m)[0] for m in features.load()
            if features.flags(m) and getattr(m, 'WEB', True) == kind
            and (unit != XL_UNIT or getattr(m, 'XL_PORTED', False))]


def combo_key(flags):
    return '+'.join(sorted(flags))


def subsets(flags):
    return [list(c) for n in range(len(flags) + 1) for c in itertools.combinations(flags, n)]


def slots_flag(slots):
    """The NAM slot count as the pseudo-flag a combination's key and built_md5's environment take."""
    return f'{block3.VAR}={slots}'


def nam_base(stock, d, unit=UNIT):
    """The image build.py hands tools/patch_menu.py: build.py's STEPS on the stock file, written in the directory d."""
    spec = importlib.util.spec_from_file_location('build', os.path.join(ROOT, 'build.py'))
    build = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build)
    src = stock
    for k, step in enumerate(build.STEPS[unit]):
        dst = os.path.join(d, f'nam_lite_{k}.l6ia')
        r = subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'patch_amp.py'), step[0], src, dst, *step[1:]],
                           cwd=ROOT, capture_output=True, text=True)
        if r.returncode:
            raise SystemExit(f'm4cache: patch_amp.py {step[0]} failed:\n{r.stdout}{r.stderr}')
        src = dst
    return src


@functools.lru_cache(maxsize=None)
def image(stock, nam, unit=UNIT):
    """The image build.py hands tools/patch_menu.py: with NAM A2 Lite (nam), or the stock file's (HX_NAM_SLOTS=0)."""
    with tempfile.TemporaryDirectory() as d:
        return pa.load_l6ia_from_any(nam_base(stock, d, unit) if nam else stock)[0]


def flag_env(flags):
    """The environment flags turn on: '1' each, a 'VAR=value' one set to its value."""
    return dict(f.split('=', 1) if '=' in f else (f, '1') for f in flags)


@contextlib.contextmanager
def build_env(env):
    """os.environ's HX_ variables as build.py's would be (features read some through it), restored after."""
    saved = {k: v for k, v in os.environ.items() if k.startswith('HX_')}
    for k in saved:
        del os.environ[k]
    os.environ.update(env)
    try:
        yield
    finally:
        for k in [k for k in os.environ if k.startswith('HX_')]:
            del os.environ[k]
        os.environ.update(saved)


def modules(stock, flags, nam=True, out=None, unit=UNIT):
    """{m4asm.key: {code, symbols}} of every module the features of flags assemble, on the image with NAM A2 Lite (nam) or without,
    added to out: a module already in it isn't assembled again."""
    out, assemble = {} if out is None else out, m4asm.assemble_module

    def keep(src, include=()):
        k = m4asm.key(src, include)
        if k not in out:
            code, symbols = assemble(src, include)
            out[k] = {'code': code.hex(), 'symbols': symbols}
        return bytes.fromhex(out[k]['code']), out[k]['symbols']

    layout = pm.XL_MENU if unit == XL_UNIT else pm.STOMP_MENU
    data, env = image(stock, nam, unit), flag_env(flags)
    m4asm.assemble_module = keep
    try:
        with build_env(env):
            pm.menu_entries(lambda e: pa.get_entry_swapped(data, e), env=env, layout=layout)
    finally:
        m4asm.assemble_module = assemble
    return out


def built_md5(stock, flags, cache=None, unit=UNIT):
    """The MD5 of build.py's .hxf with flags on (a 'VAR=value' one set to its value) and no other HX_ variable, its modules from
    the m4cache.json cache, as the page builds, when given."""
    env = {k: v for k, v in os.environ.items() if not k.startswith('HX_')}
    env.update(flag_env(flags))
    if cache:
        env[m4asm.CACHE] = os.path.abspath(cache)
    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, 'out.hxf')
        r = subprocess.run([sys.executable, os.path.join(ROOT, 'build.py'), os.path.abspath(stock), '-o', out, '--no-check'],
                           env=env, cwd=ROOT, capture_output=True, text=True)
        if r.returncode or 'ALL OK' not in r.stdout:
            raise SystemExit(f'm4cache: the build with {combo_key(flags) or "no features"} failed:\n{r.stdout}{r.stderr}')
        return hashlib.md5(open(out, 'rb').read()).hexdigest()


def combos(unit=UNIT):
    """The flags of every combination the page offers: each NAM slot count with each set of DSP features that fits beside it,
    with each set of the other opt-ins."""
    flags, options, dsp = web_flags(unit), web_options(unit), web_dsp(unit)
    if unit == XL_UNIT:
        options = [option for option in options if option == 'HX_REAL_NAMES']
        if not options:
            raise SystemExit('m4cache: XL releases require the Real Names option')
        if not block3.fits(2, dsp):
            raise SystemExit('m4cache: XL DSP features do not fit beside two NAM slots')
        return [flags + dsp + o + [slots_flag(2)] for o in subsets(options)]
    slots = block3.SLOTS
    return [flags + d + o + [slots_flag(s)] for s in slots for d in subsets(dsp) if block3.fits(s, d)
            for o in subsets(options)]


def make(stock, release=None, unit=UNIT):
    if os.environ.get(m4asm.CACHE):
        raise SystemExit(f'm4cache: unset {m4asm.CACHE}: this assembles with clang')
    if unit not in (UNIT, XL_UNIT):
        raise SystemExit(f'm4cache: unknown device {unit!r}')
    flags, options, dsp = web_flags(unit), web_options(unit), web_dsp(unit)
    costs = {f: block3.cost(f) for f in dsp}
    if unit == XL_UNIT:
        options = [option for option in options if option == 'HX_REAL_NAMES']
        flags, dsp = flags + dsp, []
    every = combos(unit)
    # a module's key covers its .inc, which differs with the other features built, so each combination keeps its own
    mods = {}
    for c in every:
        slots = flag_env(c)[block3.VAR]
        modules(stock, c, nam=slots != '0', out=mods, unit=unit)
    with tempfile.TemporaryDirectory() as d:
        cache = os.path.join(d, 'm4cache.json')
        with open(cache, 'w') as f:
            json.dump({'modules': mods}, f)
        md5 = {combo_key(c): built_md5(stock, c, cache, unit) for c in every}
    slots = (2,) if unit == XL_UNIT else block3.SLOTS
    return {'release': release, 'unit': unit, 'features': flags, 'options': options,
            'dsp': {'features': dsp, 'slots': list(slots), 'room': {str(s): block3.words(s) for s in slots},
                'cost': costs},
            'md5': {unit: md5}, 'modules': mods}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('stock', help='the stock device 3.80.0 .hxf')
    ap.add_argument('--unit', choices=(UNIT, XL_UNIT), default=UNIT)
    ap.add_argument('-o', '--out')
    ap.add_argument('--release', help='the release tag it is made for, shown on the page')
    a = ap.parse_args()
    out = a.out or os.path.join(ROOT, 'build', 'm4cache-xl.json' if a.unit == XL_UNIT else 'm4cache.json')
    cache = make(a.stock, a.release, a.unit)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, 'w') as f:
        json.dump(cache, f, separators=(',', ':'), sort_keys=True)
    print(f'[+] Wrote {out}: {len(cache["modules"])} modules for {", ".join(cache["features"])}')


if __name__ == '__main__':
    main()
