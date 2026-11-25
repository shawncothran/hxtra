"""tools/features/breathing_line.py and src/m4/breathing_line.s: the settings and their IDs, the hooks on the firmware, and the
handlers run in tests/m4emu.py against a model of each Type and Color."""
import math
import os
import struct
from types import SimpleNamespace

import pytest

import features
import patch_amp as pa
import patch_menu as pm
import setting_ids
from features import breathing_line as bl, gr
from firmware import assert_virtual, branch_target, menu_entry0, reader, stock_e0

RATES = [round(2 ** 32 / (ms * 1000)) for ms in (8000, 6000, 4800, 4000, 3200, 2500, 2000, 1500, 1100, 800)]

SCHEMES = [(c, c, c) for c in (0xffffff, 0xff0000, 0x00ff00, 0x0060ff)] + [
    (0xff1800, 0xff7000, 0xffc800), (0x0050ff, 0x00d0ff, 0xd0f8ff), (0x9000ff, 0xff2a7a, 0xff8a00),     # Fire, Ice, Sunset
    (0x0018ff, 0x0090ff, 0x00ffd0), (0x00ff70, 0x00b0ff, 0x9a00ff), (0xff00d0, 0x5000ff, 0x00f0ff)]     # Ocean, Aurora, Neon
BEATS = [1, 4, 2, 2, 2, 1, 8]       # Speed Tempo: beats a cycle for each Type
TEMPO = 10                          # Speed's Tempo value
SINE = [round(127.5 + 127.5 * math.sin(2 * math.pi * a / 256)) for a in range(256)]


def test_settings_values_defaults_and_ids():
    s = {x.key: x for x in bl.SETTINGS}
    assert [x.label for x in bl.SETTINGS] == [b'Color', b'Type', b'Speed', b'Thick'], 'one line: a 2-line label shows its name above its page'
    assert s['color'].values == (b'White', b'Red', b'Green', b'Blue', b'Fire', b'Ice', b'Sunset', b'Ocean', b'Aurora', b'Neon',
                                 b'Rainbow')
    assert s['color'].values[s['color'].default] == b'Rainbow' and len(s['color'].values) == len(SCHEMES) + 1
    assert s['motion'].values == (b'Off', b'Steady', b'Breathe', b'Cylon', b'Comet', b'Heart', b'Sparkle')
    assert s['motion'].values[s['motion'].default] == b'Breathe'
    assert s['speed'].values == tuple(str(n).encode() for n in range(1, 11)) + (b'Tempo',)
    assert s['speed'].values[s['speed'].default] == b'4'
    assert s['thickness'].values == (b'Normal', b'+1 px', b'+2 px', b'+3 px', b'+4 px')
    assert s['thickness'].default == 0
    ids = setting_ids.by_name()
    assert (ids['breathing_line.color'], ids['breathing_line.motion'], ids['breathing_line.speed'],
            ids['breathing_line.thickness']) == (0xd7, 0xd8, 0xd9, 0xe9)
    fields = {who: (cid, bit, bits) for _, cid, bit, bits, who, _ in setting_ids.VIRTUAL}
    assert [fields[f'breathing_line.{k}'] for k in ('color', 'motion', 'speed', 'thickness')] == [
        (109, 0, 4), (109, 4, 4), (109, 8, 4), (109, 12, 4)]
    assert bl.FLAG == 'HX_BREATHING_LINE'


def breathing_line_paint_hooks(layout):
    paint_hooks = []
    patch = SimpleNamespace(layout=layout, modules={})
    patch.module = lambda path, inc: {
        'bl_paint': 'bl_paint', 'bl_paint_play': 'bl_paint_play',
        'bl_paint_edit': 'bl_paint_edit', 'bl_tick': 'bl_tick'}
    patch.chain_ptr = lambda site, target, **kwargs: paint_hooks.append((site, target))
    patch.chain_bl = lambda site, target, **kwargs: None
    bl.apply(patch)
    return paint_hooks


def test_stomp_breathing_line_keeps_its_home_paint_hook():
    assert breathing_line_paint_hooks(pm.STOMP_MENU) == [(bl.HOME_PAINT_LIT, bl.HOME_PAINT)]


def test_xl_breathing_line_paints_play_and_edit_views():
    assert set(breathing_line_paint_hooks(pm.XL_MENU)) == {
        (0x28d99a44, 0x28dcc98d), (bl.XL.paint_lit, bl.XL.paint)}


# --- the build, on the stock firmware ---

@pytest.mark.firmware
@pytest.mark.parametrize('count, width', [(1, 320), (3, 106), (4, 80), (8, 40)])
def test_xl_stock_divider_sizes_one_selection_over_a_background(m4emu, count, width):
    path = os.environ.get('HX_STOMP_XL_HXF')
    if not path:
        pytest.skip('HX_STOMP_XL_HXF is not set')
    archive = pa.load_l6ia_from_any(path)[0]
    stock = reader(pa.get_entry_swapped(archive, 0))
    size, position, selected = 0x28e2aed0, 0x28e2aeb8, 0x281f9298
    assert branch_target(0x28dc97f0, stock(0x28dc97f0, 4)) == size
    assert branch_target(0x28dc980c, stock(0x28dc980c, 4)) == position
    assert struct.unpack('<II', stock(0x28dc9818, 8)) == (selected, selected - 0x1c)
    assert struct.unpack('<II', stock(0x28dc89d8, 8)) == (selected - 0x1c, selected)
    assert bl.XL.play_segments == bl.XL.edit_segments == selected - 0x1c
    assert struct.unpack('<I', stock(0x28d99df8, 4))[0] == 0x28d96565
    assert struct.unpack('<I', stock(0x28d99e0c, 4))[0] == 0x2812c240
    assert branch_target(0x28dc880e, stock(0x28dc880e, 4)) == 0x28e2ad98
    assert branch_target(0x28dc8818, stock(0x28dc8818, 4)) == 0x28e2ad98
    machine = m4emu.M4(stock(0x28dc97c8, 0x58), 0x28dc97c8)
    machine.stub(size)
    machine.stub(position)
    machine.u32(selected + 8, 119)
    machine.call(0x28dc97c8, count)
    assert [args[:3] for args in machine.calls(size)] == [(selected, width, 2)]
    assert [args[:3] for args in machine.calls(position)] == ([(selected, 0, 119)] if count == 1 else [])


@pytest.mark.firmware
def test_xl_build_hooks_edit_divider_and_tick():
    path = os.environ.get('HX_STOMP_XL_HXF')
    if not path:
        pytest.skip('HX_STOMP_XL_HXF is not set')
    archive = pa.load_l6ia_from_any(path)[0]
    load = lambda index: pa.get_entry_swapped(archive, index)
    entries, enabled = pm.menu_entries(load, features.load(), {'HX_BREATHING_LINE': '1'},
                                       setting_ids.by_name(), layout=pm.XL_MENU)
    assert 'breathing_line' in [features.name(feature) for feature in enabled]
    read, stock = reader(entries[0]), reader(load(0))
    assert read(bl.XL.play_paint_lit, 4) != stock(bl.XL.play_paint_lit, 4)
    assert read(bl.XL.paint_lit, 4) != stock(bl.XL.paint_lit, 4)
    assert read(bl.XL.tick, 4) != stock(bl.XL.tick, 4)
    for setting in bl.SETTINGS:
        assert_virtual(entries[0], bl, setting)

@pytest.mark.firmware
def test_build_serves_the_settings_virtually_and_hooks_the_paint_and_the_tick():
    e0 = stock_e0()
    new, on = menu_entry0(e0, None, {'HX_BREATHING_LINE': '1'})
    assert 'breathing_line' in [features.name(m) for m in on]
    for s in bl.SETTINGS:
        assert_virtual(new, bl, s)
    read, stock = reader(new), reader(e0)
    assert read(bl.HOME_PAINT_LIT, 4) != stock(bl.HOME_PAINT_LIT, 4)
    assert read(bl.EDIT_PAINT_LIT, 4) == stock(bl.EDIT_PAINT_LIT, 4)
    assert read(bl.LED_TICK_CALL, 4) != stock(bl.LED_TICK_CALL, 4)


@pytest.mark.firmware
def test_a_build_with_the_gr_meter_hands_the_line_its_shown_word(monkeypatch):
    """GR is built first (ORDER), so the line gets the address of the word that says its meter shows; without GR, 0."""
    assert gr.ORDER < getattr(bl, 'ORDER', 100)
    seen, real = {}, pm.Patch.module

    def module(self, path, inc=None):
        seen[path] = (real(self, path, inc), inc)
        return seen[path][0]
    monkeypatch.setattr(pm.Patch, 'module', module)
    menu_entry0(stock_e0(), None, {'HX_BREATHING_LINE': '1', 'HX_GR': '1'})
    assert seen['src/m4/breathing_line.s'][1]['gr.inc'] == f'.equ GR_SHOWN, {seen[gr.MODULE][0]["data"] + gr.SHOWN:#x}\n'
    seen.clear()
    menu_entry0(stock_e0(), None, {'HX_BREATHING_LINE': '1'})
    assert seen['src/m4/breathing_line.s'][1]['gr.inc'] == '.equ GR_SHOWN, 0x0\n'


@pytest.mark.firmware
def test_xl_build_with_gr_hands_the_line_its_middle_divider_word(monkeypatch):
    path = os.environ.get('HX_STOMP_XL_HXF')
    if not path:
        pytest.skip('HX_STOMP_XL_HXF is not set')
    archive = pa.load_l6ia_from_any(path)[0]
    seen, real = {}, pm.Patch.module

    def module(self, path, inc=None):
        seen[path] = (real(self, path, inc), inc)
        return seen[path][0]

    monkeypatch.setattr(pm.Patch, 'module', module)
    pm.menu_entries(lambda n: pa.get_entry_swapped(archive, n), features.load(),
                    {'HX_BREATHING_LINE': '1', 'HX_GR': '1'}, setting_ids.by_name(), layout=pm.XL_MENU)
    gr_module = seen[gr.MODULE][0]
    assert seen['src/m4/breathing_line.s'][1]['gr.inc'] == f'.equ GR_SHOWN, {gr_module["gr_line_middle"]:#x}\n'


# --- the handlers, run in unicorn: a model of each first ---

M32 = 0xffffffff
CENTRE = 632                        # the line's middle in 1/16 strips
EYE_CORE = 64                       # Cylon's eye: full on 4 strips either side of its centre


def fall(d, width):
    return 0 if not 0 <= d < width else 255 - d * 255 // width


def fall2(d, width):
    return (fall(d, width) ** 2 + 255) >> 8


def beat(u):
    return 0 if not 0 <= u < 56 else u * 255 // 6 if u < 6 else fall2(u - 6, 50)


def spark(phase, strip, seed):
    h = (strip + 80 * (seed + (phase >> 6))) * 0x9e3779b1 & M32
    h ^= h >> 15
    h = h * 0x85ebca6b & M32
    h ^= h >> 13
    if h >> 28 >= 3:
        return 0
    d = (phase & 63) - (h >> 8 & 31)
    return 0 if d < 0 else 128 + 127 * d if d < 2 else fall2(d - 2, 30)


def sparkle(strip, t, cycles):
    return max(spark(t, strip, 8 * cycles & M32), spark((t + 32) & 255, strip, 8 * cycles + 4 & M32))


def level(motion, strip, t16, cycles=0):
    t, at = t16 >> 8, strip * 16
    if motion in (0, 1):
        return 255
    if motion == 2:
        return (SINE[(t + 192) & 255] ** 2 + 255) >> 8
    if motion == 3:
        eye, trail = SINE[(t + 192) & 255] * 79 * 16 // 255, 2 * abs(SINE[t] - 128) + 32
        behind = eye - at if t < 128 else at - eye
        return fall2(max(behind - EYE_CORE, 0), trail) if behind >= 0 else fall(max(-behind - EYE_CORE, 0), 24)
    if motion == 4:
        behind = (t16 * (80 * 16 + 320) >> 16) - at
        return fall2(behind, 320) if behind >= 0 else fall(-behind, 16)
    if motion == 5:
        return max(beat(t), beat(t - 48) * 3 // 4) * (255 - abs(at - CENTRE) * 150 // CENTRE) >> 8
    return sparkle(strip, t, cycles)


def hue(h):
    region, up = h // 43, (h % 43) * 6
    down = 255 - up
    return [(255, up, 0), (down, 255, 0), (0, 255, up), (0, down, 255), (up, 0, 255), (255, 0, down)][region]


def rgb(r, g, b):
    return r << 16 | g << 8 | b


def dim(c):
    """A quarter of each channel: a colour at level 0."""
    return sum(((c >> s & 255) // 4) << s for s in (0, 8, 16))


def lift(lvl):
    """The level eased out, so the line spends less time near its dimmest."""
    return 255 - (((255 - lvl) ** 2 + 255) >> 8)


def mix(a, b, k):
    k += k >> 7
    return sum(((a >> s & 255) + (((b >> s & 255) - (a >> s & 255)) * k >> 8)) << s for s in (0, 8, 16))


def colour(scheme, strip, t16, lvl):
    h = (strip * 16 // 5 + (t16 >> 8)) & 255
    if scheme == len(SCHEMES):
        c = rgb(*hue(h))
    else:
        stops, seg = SCHEMES[scheme], h * 3 >> 8
        c = mix(stops[seg], stops[(seg + 1) % 3], h * 3 & 255)
    return mix(dim(c), c, lift(lvl))


MOD = 0x28e60000
SEGMENTS, NODES = 0x2812a594, 0x2812b000
REDRAW, GET_VALUE, CLOCK, LOCK, UNLOCK, FILL = 0x28db8508, 0x28e1f844, 0x28da6458, 0x28e24970, 0x28e24ae8, 0x100017e8
IDS = {'color': 0xd7, 'motion': 0xd8, 'speed': 0xd9, 'thickness': 0xe9}
START_MS = 2000                     # the line starts this long after the first Home paint
_code = {}


class Line:
    """breathing_line.s in the M4, with a stock or XL divider; settings and the clock are modelled."""

    def __init__(self, m4emu, text, sym, profile=bl.STOMP):
        self.sym, self.settings, self.now, self.fills = sym, {}, 0, []
        self.profile = profile
        self.m = m4emu.M4(text, MOD)
        for at in (profile.redraw & ~1, profile.lock & ~1, profile.unlock & ~1):
            self.m.stub(at)
        self.m.stub(profile.get & ~1, self.get_value)
        self.m.stub(profile.clock & ~1, lambda m: m.reg('r0', self.now))
        self.m.stub(FILL, lambda m: self.fills.append((m.reg('r0'), m.reg('r1'), m.reg('r2'), m.reg('r3'), *m.stack_args(3))))
        if profile is bl.XL:
            for k in range(2):
                self.segment(k, h=2 if k == 1 else 1, segments=profile.edit_segments, node_index=k)
        else:
            for k in range(4):
                self.segment(k, segments=profile.play_segments, node_index=k)
        self.set_data(6, START_MS + 1)

    def segment(self, k, h=1, visible=1, segments=None, node_index=None):
        segments = segments if segments is not None else self.profile.play_segments
        node_index = k if node_index is None else node_index
        w = segments + 0x1c * k
        if self.profile is bl.XL and segments == self.profile.edit_segments:
            self.m.u32(w + 4, 0)
            self.m.u32(w + 8, 120)
            self.m.u32(w + 12, 320)
            self.m.u32(w + 16, h)
            self.m.u8(w + 0x14, 6)
            self.m.u8(w + 0x15, visible)
        else:
            self.m.write(w, struct.pack('<5I', 0x666666, 80 * k, 0x77, 80, h) + bytes([0, visible, 0, 0]))
        self.m.u32(w + 0x18, NODES + 0x28 * node_index)
        self.m.u8(NODES + 0x28 * node_index + 0x24, 0)

    def dirty(self, k):
        return self.m.read(NODES + 0x28 * k + 0x24, 1)[0]

    def get_value(self, m):
        m.write(m.reg('r1'), struct.pack('<II', 2, self.settings.get(m.reg('r0'), 0)))
        m.reg('r0', 0)

    def call(self, sym, *args):
        self.m.log.clear()
        return self.m.call(MOD + self.sym[sym], *args)

    def data(self, i):
        return self.m.u32(MOD + self.sym['bl_data'] + 4 * i)

    def set_data(self, i, v):
        self.m.u32(MOD + self.sym['bl_data'] + 4 * i, v)

    def paint(self, fb=0x28d1ce98, stock=None, view=None, **settings):
        self.settings = {IDS[k]: v for k, v in settings.items()} | (stock or {})
        self.fills = []
        view = view or ('edit' if self.profile is bl.XL else 'play')
        if self.profile is bl.XL and view == 'play':
            selected = self.profile.play_segments + 0x1c
            self.m.u32(selected + 4, 240)
            self.m.u32(selected + 8, 119)
            self.m.u32(selected + 12, 80)
        self.call(f'bl_paint_{view}', fb)
        return self.fills

    def expected_redraw(self):
        if self.profile is bl.XL:
            return (1, 1) if self.data(7) == 0 else (1, 0)
        return (1, 0) if self.data(7) == 1 else (0, 1)


@pytest.fixture
def line(m4emu):
    if 'line' not in _code:
        _code['line'] = m4emu.assemble('src/m4/breathing_line.s', features.load(), setting_ids.by_name(),
                                       inc={'gr.inc': '.equ GR_SHOWN, 0\n', 'breathing.inc': bl.line_inc()})
    return Line(m4emu, *_code['line'])


GR_SHOWN = 0x28e7f000               # the GR meter's shown word, in a build with both


@pytest.fixture
def line_gr(m4emu):
    if 'line_gr' not in _code:
        _code['line_gr'] = m4emu.assemble('src/m4/breathing_line.s', features.load(), setting_ids.by_name(),
                                          inc={'gr.inc': f'.equ GR_SHOWN, {GR_SHOWN:#x}\n', 'breathing.inc': bl.line_inc()})
    return Line(m4emu, *_code['line_gr'])


@pytest.fixture
def line_xl(m4emu):
    if 'line_xl' not in _code:
        _code['line_xl'] = m4emu.assemble('src/m4/breathing_line.s', features.load(), setting_ids.by_name(),
                                          inc={'gr.inc': '.equ GR_SHOWN, 0\n', 'breathing.inc': bl.line_inc(bl.XL)},
                                          layout=pm.XL_MENU)
    return Line(m4emu, *_code['line_xl'], profile=bl.XL)


def test_xl_edit_divider_is_animated_with_xl_apis(line_xl):
    fills = line_xl.paint(fb=0x28d1f650, motion=1, color=0, speed=0)
    assert len(fills) == 80
    assert [fill[1] for fill in fills] == list(range(0, 320, 4))
    assert all(fill[0] == 0x28d1f650 and fill[2] == 120 and fill[3] == 4 and fill[4] == 2 for fill in fills)


def test_xl_edit_divider_guard_skips_other_rectangles(line_xl):
    for k in range(2):
        line_xl.m.u32(bl.XL.segments + 0x1c * k + 12, 319)
    assert line_xl.paint(fb=0x28d1f650, motion=1, color=0, speed=0) == []


def test_xl_play_divider_uses_the_native_rectangle_pair(line_xl):
    fills = line_xl.paint(fb=0x28d1f650, motion=1, color=0, speed=0, view='play')
    assert len(fills) == 80
    assert [fill[1] for fill in fills] == list(range(0, 320, 4))
    assert {(fill[2], fill[4]) for fill in fills if fill[1] < 240} == {(156, 1)}
    assert {(fill[2], fill[4]) for fill in fills if fill[1] >= 240} == {(155, 2)}


def test_xl_animation_requests_the_edit_display_list(line_xl):
    line_xl.paint(fb=0x28d1f650, motion=2, color=0, speed=0)
    for _ in range(25):
        line_xl.call('bl_tick')
    assert [args[:2] for args in line_xl.m.calls(bl.XL.redraw)] == [(1, 0)]


def test_xl_play_animation_requests_both_display_lists(line_xl):
    line_xl.paint(fb=0x28d1f650, motion=2, color=0, speed=0, view='play')
    for _ in range(25):
        line_xl.call('bl_tick')
    assert [args[:2] for args in line_xl.m.calls(bl.XL.redraw)] == [(1, 1)]


def test_stomp_animation_requests_the_home_display_list(line):
    line.paint(motion=2, color=0, speed=0, view='play')
    for _ in range(25):
        line.call('bl_tick')
    assert [args[:2] for args in line.m.calls(REDRAW)] == [(0, 1)]


PHASES = (0, 1, 0x1234, 0x3fff, 0x4000, 0x7fff, 0x8000, 0x8001, 0xa000, 0xbfff, 0xc000, 0xfeff, 0xffff)


@pytest.mark.parametrize('motion', range(7))
def test_level_matches_the_model(line, motion):
    for strip in range(80):
        for t16 in PHASES + tuple(range(0, 0x10000, 0x0f1)):
            if strip % 7 and t16 not in PHASES:
                continue
            assert line.call('bl_level', motion, strip, t16) == level(motion, strip, t16), (strip, hex(t16))
    line.set_data(5, 7)
    for strip in range(80):
        assert line.call('bl_level', motion, strip, 0x5a00) == level(motion, strip, 0x5a00, 7), 'cycle 7'


def test_levels_have_their_shape():
    assert level(2, 0, 0) == 0 and level(2, 0, 128 << 8) == 255
    assert level(3, 0, 0) == 255 and level(3, 79, 0x8000) == 255 and level(3, 40, 0) == 0
    fast = [level(3, s, 64 << 8) for s in range(80)]
    full = [s for s, v in enumerate(fast) if v == 255]
    assert len(full) >= 8 and full == list(range(full[0], full[-1] + 1)), 'a wide eye, full on across its middle'
    assert sum(v > 0 for v in fast[:full[0]]) > 12 and sum(v > 0 for v in fast[full[-1] + 1:]) < 3, 'a long trail behind, a short fade ahead'
    assert level(4, 10, 0) == 0 and max(level(4, 10, t << 8) for t in range(256)) > 240
    assert level(5, 39, 6 << 8) > 250 and level(5, 0, 6 << 8) < 110 and level(5, 39, 54 << 8) > 180 and level(5, 39, 200 << 8) == 0
    for cycles in (0, 1, 2):
        lit = [sum(level(6, s, t << 8, cycles) > 0 for s in range(80)) for t in range(0, 256, 8)]
        assert 0 < min(lit) and max(lit) < 24, 'never dark, and a few strips lit at a time'
    assert [level(6, s, 0x2000, 0) for s in range(80)] != [level(6, s, 0x2000, 1) for s in range(80)], 'new strips each cycle'


def test_shade_is_brighter_than_the_level():
    assert dim(0xffffff) == 0x3f3f3f and colour(0, 0, 0, 0) == 0x3f3f3f, 'a quarter of the colour at level 0'
    assert lift(0) == 0 and lift(255) == 255 and lift(128) > 180, 'half a level shows well over half bright'


def test_hue_matches_the_model(line):
    for h in range(256):
        assert line.call('bl_hue', h) == rgb(*hue(h)), h


@pytest.mark.parametrize('scheme', range(len(SCHEMES) + 1))
def test_colour_matches_the_model(line, scheme):
    for strip in (0, 1, 33, 79):
        for t16 in (0, 0x4000, 0xff00):
            for lvl in (0, 1, 100, 128, 254, 255):
                assert line.call('bl_colour', scheme, strip, t16, lvl) == colour(scheme, strip, t16, lvl)
    if scheme < len(SCHEMES):
        assert colour(scheme, 0, 0, 255) == SCHEMES[scheme][0] and colour(scheme, 0, 0, 0) == dim(SCHEMES[scheme][0])


def test_tables_are_as_modelled(line):
    def words(sym, n):
        return list(struct.unpack(f'<{n}I', line.m.read(MOD + line.sym[sym], 4 * n)))
    assert words('bl_rates', 10) == RATES
    assert words('bl_schemes', 3 * len(SCHEMES)) == [c for stops in SCHEMES for c in stops]
    assert list(line.m.read(MOD + line.sym['bl_sine'], 256)) == SINE


def test_paint_fills_each_strip_as_tall_as_its_segment(line):
    line.segment(2, h=2)
    line.now = 1_000_000
    fills = line.paint(color=1, motion=1, speed=3)
    assert len(fills) == 80
    for i, (fb, x, y, w, h, c, anchor) in enumerate(fills):
        assert (fb, x, y, w, h, c, anchor) == (0x28d1ce98, 4 * i, 0x77, 4, 2 if x // 80 == 2 else 1, 0xff0000, 6)
    assert line.data(0) == 1 and line.data(1) == 0
    assert line.m.calls(LOCK) and line.m.calls(UNLOCK)


def test_paint_skips_a_hidden_segment(line):
    line.segment(0, visible=0)
    assert [x for _, x, *_ in line.paint(motion=3)] == list(range(80, 320, 4))


def test_paint_moves_the_phase_by_the_time_since_the_last(line):
    line.paint(motion=2, speed=9)
    line.now += 400_000                         # half of Speed 10's 0.8 s
    phase = line.data(4)
    fills = line.paint(motion=2, speed=9, color=0)
    assert line.data(4) == (phase + 400_000 * RATES[9]) & 0xffffffff
    t16 = line.data(4) >> 16
    assert abs(t16 - 0x8000) < 4
    assert fills[0][5] == colour(0, 0, t16, level(2, 0, t16))


def test_paint_survives_the_clock_wrapping(line):
    line.now = 0xffff0000
    line.paint(motion=2, speed=0)
    phase = line.data(4)
    line.now = 0x00010000
    line.paint(motion=2, speed=0)
    assert line.data(4) == (phase + 0x20000 * RATES[0]) & 0xffffffff


def f32(x):
    return struct.unpack('<I', struct.pack('<f', x))[0]


def tempo_rate(bpm, motion):
    """The Tempo rate: 2^32 / BEATS[motion] beats of a whole-ms beat in µs, rounded as bl_tempo_rate rounds it."""
    cycle = int(60000 / f32_value(bpm)) * 1000 * BEATS[motion]
    q, r = divmod(M32, cycle)
    return q + (r >= cycle >> 1)


def f32_value(x):
    return struct.unpack('<f', struct.pack('<f', x))[0]


def rate_after(line, us, **paint):
    line.paint(**paint)
    phase = line.data(4)
    line.now += us
    line.paint(**paint)
    return (line.data(4) - phase) & M32, us


@pytest.mark.parametrize('motion', range(1, 7))
def test_tempo_runs_a_cycle_in_each_types_beats(line, motion):
    stock = {14: 2, 15: f32(120.0)}                 # Tempo Select Global, Global BPM 120
    delta, us = rate_after(line, 100_000, motion=motion, speed=TEMPO, stock=stock)
    assert delta == us * tempo_rate(120.0, motion)
    assert abs(tempo_rate(120.0, motion) - 2 ** 32 / (500_000 * BEATS[motion])) < 1


def test_tempo_follows_preset_bpm_unless_tempo_select_is_global(line):
    for select in (0, 1):                           # Preset, Snapshot
        stock = {14: select, 15: f32(120.0), 16: f32(90.0)}
        delta, us = rate_after(line, 100_000, motion=2, speed=TEMPO, stock=stock)
        assert delta == us * tempo_rate(90.0, 2)


def test_tempo_takes_the_beat_in_whole_ms_as_the_stock_beat(line):
    stock = {14: 2, 15: f32(133.0)}                 # 451.13 ms: the stock beat runs at 451
    delta, us = rate_after(line, 100_000, motion=5, speed=TEMPO, stock=stock)
    assert delta == us * round(2 ** 32 / (451_000 * BEATS[5]))


@pytest.mark.parametrize('bpm', [0.0, 0.5, 1024.0, float('nan')])
def test_tempo_without_a_tempo_runs_at_the_default_speed(line, bpm):
    stock = {14: 2, 15: f32(bpm)}
    delta, us = rate_after(line, 100_000, motion=2, speed=TEMPO, stock=stock)
    assert delta == us * RATES[bl.SETTINGS[2].default]


def test_paint_uses_the_defaults_for_values_above_max(line):
    fills = line.paint(color=15, motion=12, speed=14)                   # what a 4-bit field holds above each max
    t16 = line.data(4) >> 16
    assert line.data(0) == 1 and len(fills) == 80
    assert fills[5][5] == colour(len(SCHEMES), 5, t16, level(2, 5, t16))


def test_paint_counts_cycles_for_sparkle(line):
    line.paint(motion=6, speed=9)
    counted = []
    for _ in range(4):
        line.now += 500_000                     # 5/8 of a cycle at Speed 10
        line.paint(motion=6, speed=9)
        counted.append(line.data(5))
    assert counted == [0, 1, 1, 2]


def test_off_draws_nothing_and_hands_the_line_back_to_the_stock_segments(line):
    assert line.paint(motion=0) == [] and line.data(0) == 0
    assert not any(line.dirty(k) for k in range(4)), 'never on: nothing to give back'
    line.paint(motion=3)
    assert line.data(0) == 1
    assert line.paint(motion=0) == []
    assert all(line.dirty(k) for k in range(4)) and line.data(0) == 2, 'the stock paint redraws them on the next paint'
    for k in range(4):
        line.segment(k)
    assert line.paint(motion=0) == [] and line.data(0) == 0
    assert not any(line.dirty(k) for k in range(4))


def test_line_holds_still_while_a_gr_meter_shows(line_gr):
    """User decision: the line yields to a compressor's meter, as at Type Off, and runs again once the meter is off."""
    line_gr.m.u32(GR_SHOWN, 0)
    assert len(line_gr.paint(motion=3)) == 80 and line_gr.data(0) == 1
    line_gr.m.u32(GR_SHOWN, 1)
    assert line_gr.paint(motion=3) == []
    assert all(line_gr.dirty(k) for k in range(4)) and line_gr.data(0) == 2, 'the stock segments back, for the meter'
    assert line_gr.paint(motion=3) == [] and line_gr.data(0) == 0
    assert ticks(line_gr, 100) == 0, 'no repaints while it holds'
    line_gr.m.u32(GR_SHOWN, 0)
    assert len(line_gr.paint(motion=3)) == 80 and line_gr.data(0) == 1


@pytest.mark.parametrize('fixture', ['line', 'line_xl'])
@pytest.mark.parametrize('value', [1, 2, 3, 4])
def test_thickness_changes_the_rendered_line(request, fixture, value):
    line = request.getfixturevalue(fixture)
    fills = line.paint(motion=1, color=0, speed=0, thickness=value)
    assert len(fills) == 80
    assert {fill[4] for fill in fills} == {(2 if fixture == 'line_xl' else 1) + value}


@pytest.mark.parametrize(('fixture', 'view'), [('line', 'edit'), ('line_xl', 'play')])
def test_thickness_applies_in_each_added_view(request, fixture, view):
    line = request.getfixturevalue(fixture)
    if fixture == 'line_xl':
        line.segment(1, h=2, segments=bl.XL.play_segments, node_index=1)
    else:
        line.segment(1, h=2)
    fills = line.paint(motion=1, color=0, speed=0, thickness=3, view=view)
    assert len(fills) == 80
    selected_start, selected_end = (240, 320) if fixture == 'line_xl' else (80, 160)
    assert {fill[4] for fill in fills if not selected_start <= fill[1] < selected_end} == {4}
    assert {fill[4] for fill in fills if selected_start <= fill[1] < selected_end} == {5}
    if fixture == 'line_xl':
        assert {fill[2] for fill in fills if fill[1] < selected_start} == {156}
        assert {fill[2] for fill in fills if fill[1] >= selected_start} == {155}


@pytest.mark.parametrize('fixture', ['line', 'line_xl'])
@pytest.mark.parametrize('next_motion,next_thickness', [(0, 4), (1, 0), (1, 1)])
def test_extra_thickness_is_removed_after_a_change(request, fixture, next_motion, next_thickness):
    line = request.getfixturevalue(fixture)
    framebuffer = 0x28a00000
    background = 0x1234
    line.m.write(framebuffer, struct.pack('<H', background) * (320 * 240))

    def fill(machine):
        x, top, width = machine.reg('r1'), machine.reg('r2'), machine.reg('r3')
        height, color, _ = machine.stack_args(3)
        pixel = ((color >> 3) & 31) << 11 | ((color >> 10) & 63) << 5 | ((color >> 19) & 31)
        for column in range(x, x + width):
            for row in range(top - height + 1, top + 1):
                machine.write(framebuffer + 2 * (240 * column + row), struct.pack('<H', pixel))

    line.m.stub(FILL, fill)
    line.paint(fb=framebuffer, motion=1, color=0, speed=0, thickness=4)
    top = 120 if fixture == 'line_xl' else 0x77
    updated = framebuffer + 2 * (240 * 100 + top - 3)
    line.m.write(updated, struct.pack('<H', 0x5678))
    line.paint(fb=framebuffer, motion=next_motion, color=0, speed=0, thickness=next_thickness)
    for row in range(top - 5, top - 1):
        if next_motion and row >= top - ((2 if fixture == 'line_xl' else 1) + next_thickness) + 1:
            continue
        expected = 0x5678 if row == top - 3 else background
        assert struct.unpack('<H', line.m.read(framebuffer + 2 * (240 * 100 + row), 2))[0] == expected


def ticks(line, n):
    count = 0
    for _ in range(n):
        line.call('bl_tick')
        assert all(regs[:2] == line.expected_redraw() for regs in line.m.calls(REDRAW)), 'repaint the last view that drew the line'
        count += len(line.m.calls(REDRAW))
    return count


def test_tick_asks_for_a_repaint_every_25_ms_while_running(line):
    assert ticks(line, 100) == 0, 'no paint yet'
    line.paint(motion=3)
    assert ticks(line, 100) == 4


def test_line_starts_2_s_after_the_first_home_paint(line):
    """User decision: the BPM shows at 1 s and the line starts at 2 s, as both starting together glitched at boot."""
    line.set_data(6, 0)
    assert ticks(line, 3000) == 0, 'no Home paint yet'
    assert line.paint(motion=3) == [] and line.data(0) == 0
    assert ticks(line, START_MS - 1) == 0
    assert line.paint(motion=3) == [], 'a later paint does not restart the count'
    assert ticks(line, 1) == 1, 'a paint to start the line'
    assert len(line.paint(motion=3)) == 80 and line.data(0) == 1
    assert ticks(line, 25) == 1 and line.data(6) == START_MS + 1


def test_tick_stops_once_the_home_view_stops_painting(line):
    line.paint(motion=3)
    assert ticks(line, 2000) == 40, 'a second of frames, then the Home view is taken to be gone'
    line.paint(motion=3)
    assert ticks(line, 50) == 2


def test_tick_runs_on_for_the_stock_lines_repaint_then_stops(line):
    line.paint(motion=3)
    line.paint(motion=0)
    assert ticks(line, 25) == 1
    line.paint(motion=0)
    assert ticks(line, 100) == 0
