"""tools/features/long_press.py and src/m4/long_press.s: the Hold settings, the event handler run in unicorn against a fake stock
handler (held-back presses, clicks, holds, the tuner and FS4/FS5, and where the stock behaviour stays), and the firmware it builds."""
import os
import struct

import pytest

import features
import patch_amp as pa
import patch_menu as pm
import setting_ids
from features import long_press
from firmware import assert_virtual, branch_target, built, built_e0, reader, stock_e0

MODS = features.load()
IDS = setting_ids.by_name()
HOLD_IDS = [IDS[f'long_press.fs{n}'] for n in (1, 2, 3, 4, 5)]
FUNCTION_IDS = [IDS[f'long_press.fs{n}_function'] for n in (6, 7, 8, 9, 10)]
HOME_CTOR_CALL, HOME_CTOR = 0x28d96c44, 0x28dc91d0

CODE, OBJ, EVENT, LISTS = 0x28e60000, 0x28128a80, 0x28600000, 0x28128b4c
STOCK = 0x28700000                  # the stock handler, as the veneer hands it over
FUNCS, GUARD, REQUEST_TUNER, GET_LISTS, MOMENTARY = 0x28128a74, 0x28d96134, 0x28d96588, 0x28d96084, 0x28dd83c4
REQUEST_VIEW, REQUEST_PANEL = 0x28d96320, 0x28d9638c
HOME_VIEW, TUNER_VIEW, GLOBAL_EQ_VIEW = 0, 5, 6
TOUCH1, TOUCHED = 9, 0x7d           # touches on footswitches 1..3 are codes 9..11; touched flags at the object's +0x7d + k
FS_MODE = 21
PRESS, RELEASE, CLICK, HOLD = 1, 2, 3, 5
TUNER, FS4, FS5 = 1, 2, 3
FS6 = 4                             # FS6..FS10: 4..8
GET_CONTROLLERS, CONTROLLERS, LOCK, UNLOCK = 0x28d9608c, 0x28480000, 0x28e24c00, 0x28e24bb0
TONE_OF, TONE, GET_BYPASS, CONTROL = 0x28d92a98, 0x28490000, 0x28e04514, 0x28dde408
ON, OFF = 0x3f800000, 0
GET_FUNCTIONS, FUNCTIONS_BASE = 0x28d9607c, 0x28128a70
DISPATCH_EXIT = bytes.fromhex('04b0 70bd')      # add sp,#16; pop {r4,r5,r6,pc}: how the dispatch's cases return
TUNER_FN, STOMP, BANK_UP, PRESET_UP, SNAPSHOT_DN, FS_MODE_UP, TOGGLE_EXP, GLOBAL_EQ = 0, 1, 2, 4, 7, 8, 11, 12     # FS6..FS10 Function values
TAP_CORE = 0x28d9bfa8
WIDGET_LOCK, WIDGET_UNLOCK, MEMSET, BLOCK_INFO = 0x28e24970, 0x28e24ae8, 0x28e24b78, 0x28e0fe94
IS_LOOPER, IS_SHUFFLING_LOOPER = 0x28de778c, 0x28de779c
LOOPERS = (504, 505, 570, 571, 616, 617)    # 1 Switch Looper mono/stereo, Shuffling Looper's two pairs
INFO_SIZE = 0x34
NODES = 0x28630000


class Handler:
    """lp_event in unicorn: what reaches the stock handler, and the tuner requests."""

    def __init__(self, m4emu):
        code, self.sym = m4emu.assemble('src/m4/long_press.s', MODS, IDS, inc={'long_press.inc': long_press.long_press_inc()})
        self.m = m4emu.M4(code, CODE)
        self.settings = {FS_MODE: 0, **{pid: 0 for pid in HOLD_IDS}}     # Off unless a test sets an action
        self.momentary, self.view, self.seen = set(), HOME_VIEW, []
        self.m.stub(pm.GET_VALUE, self._get_value)
        self.m.stub(STOCK, self._stock)
        self.m.stub(GUARD, lambda m: m.reg('r0', int(m.reg('r0') == self.view)))
        self.m.stub(REQUEST_TUNER)
        self.m.stub(REQUEST_VIEW)
        self.m.stub(REQUEST_PANEL)
        self.m.stub(GET_LISTS, lambda m: m.reg('r0', LISTS))
        self.m.stub(MOMENTARY, lambda m: m.reg('r0', int(m.reg('r1') in self.momentary)))
        self.bypassed, self.order = {}, []
        self.m.stub(GET_CONTROLLERS, lambda m: m.reg('r0', CONTROLLERS))
        self.m.stub(LOCK, lambda m: self.order.append(('lock', m.reg('r0'))))
        self.m.stub(UNLOCK, lambda m: self.order.append(('unlock', m.reg('r0'))))
        self.m.stub(TONE_OF, lambda m: m.reg('r0', TONE))
        self.m.stub(GET_BYPASS, self._get_bypass)
        self.m.stub(CONTROL, lambda m: self.order.append(('control', m.reg('r0'), m.reg('r1'), m.reg('r2'), m.reg('r3'))))
        for i in range(64):
            self.node(i)
        for k in range(5):
            self.function(k, 2)
        self.cases = []
        self.m.stub(GET_FUNCTIONS, lambda m: m.reg('r0', FUNCTIONS_BASE))
        for at in (long_press.SWITCH + 0xe, long_press.TOGGLE_EXP):
            self.m.stub(at, lambda m, at=at: self._case(m, at), code=DISPATCH_EXIT)
        self.models, self.info_fails = {}, set()     # block -> preset model ID; blocks whose info lookup fails
        for k in range(5):
            self.blocks(k)
        self.m.stub(WIDGET_LOCK, lambda m: self.order.append(('wlock',)))
        self.m.stub(WIDGET_UNLOCK, lambda m: self.order.append(('wunlock',)))
        self.m.stub(MEMSET, lambda m: m.write(m.reg('r0'), bytes([m.reg('r1')]) * m.reg('r2')))
        self.m.stub(BLOCK_INFO, self._block_info)
        self.m.stub(IS_LOOPER, lambda m: m.reg('r0', int(m.reg('r0') in (504, 505))))
        self.m.stub(IS_SHUFFLING_LOOPER, lambda m: m.reg('r0', int(m.reg('r0') in (570, 571, 616, 617))))

    def _block_info(self, m):
        assert m.reg('r0') == TONE
        block, info = m.reg('r1'), m.reg('r2')
        self.order.append(('info', block, m.read(info, INFO_SIZE) == bytes(INFO_SIZE)))
        if block in self.info_fails:
            m.reg('r0', -44)
            return
        if block in self.models:
            m.write(info + 1, struct.pack('<H', self.models[block]))
        m.reg('r0', 0)

    def blocks(self, k, *nodes):
        """Footswitch k's bypass assignment list, as nodes (kind, block): kind 1 a block, as the stock press walks it."""
        head = LISTS + 0x20 * (k + 1)
        at = [NODES + 0x400 * k + 0x40 * i for i in range(len(nodes))]
        for i, (kind, block) in enumerate(nodes):
            self.m.u32(at[i], at[i + 1] if i + 1 < len(nodes) else head)
            self.m.u8(at[i] + 9, kind)
            self.m.u32(at[i] + 0xc, block)
        self.m.u32(head, at[0] if nodes else head)

    def _case(self, m, at):
        """Entered as the dispatch is there: its frame on the stack, r4 k, r6 the object, r0 footswitch k's function slot."""
        k = m.reg('r4')
        assert m.reg('r6') == OBJ and m.reg('r0') == FUNCTIONS_BASE + 2 * k
        r5 = m.reg('r5')
        pressed = m.read(OBJ + 0x78 + k, 1)[0]
        if at == long_press.TOGGLE_EXP:
            assert r5 == OBJ + k, 'TogglEXP reads the pressed byte at r5 + 0x78'
            self.cases.append(('exp', k, pressed))
        else:
            assert r5 == 2 * k
            self.cases.append(('switch', k, m.reg('r3') + 1, pressed))

    def _get_value(self, m):
        pid, out = m.reg('r0'), m.reg('r1')
        if pid in self.settings:
            m.u8(out, 2)
            m.u32(out + 4, self.settings[pid])
            m.reg('r0', 0)
        else:
            m.reg('r0', -1)

    def _stock(self, m):
        ev = m.read(m.reg('r0'), 8)
        assert m.reg('r1') == OBJ
        self.seen.append((ev[0], ev[1], struct.unpack_from('<I', ev, 4)[0]))

    def _get_bypass(self, m):
        assert m.reg('r0') == TONE
        self.order.append(('get', m.reg('r1')))
        if m.reg('r1') in self.bypassed:
            m.u8(m.reg('r2'), self.bypassed[m.reg('r1')])
        m.reg('r0', 0)

    def node(self, i, kind=None, controller=8, cc=0, block=0):
        """Controller node i: free (kind None), or kind 2 a bypass assignment of block to controller (8 MIDI CC) at cc."""
        at = CONTROLLERS + 0xac + 0x48 * i
        self.m.u8(at + 0x44, 0x40 if kind is None else 0)
        self.m.u8(at + 0x28, kind or 0)
        self.m.u8(at + 0x10, controller)
        self.m.u32(at + 0x14, cc)
        self.m.u32(at + 0x2c, block)

    def hold(self, code):
        self.order.clear()
        self.run(*held(code))
        return [o for o in self.order if o[0] in ('get', 'control')]

    def function(self, k, f):
        self.m.u8(FUNCS + 2 * k, f)

    def hold_action(self, n, action):
        self.settings[HOLD_IDS[n - 1]] = action

    def virtual_function(self, n, value):
        self.settings[FUNCTION_IDS[n - 6]] = value

    def event(self, code, kind, source=1):
        self.m.write(EVENT, bytes([source, code, 0, 0]) + struct.pack('<I', kind))
        self.m.call(CODE + self.sym['lp_event'], EVENT, OBJ, STOCK | 1)

    def run(self, *events):
        """Each (code, type) through lp_event -> [(code, type)] the stock handler got, and the tuner requests."""
        self.seen.clear()
        self.m.log.clear()
        for code, kind in events:
            self.event(code, kind)
        assert all(src == 1 for src, _, _ in self.seen)
        return [(c, t) for _, c, t in self.seen], len(self.m.calls(REQUEST_TUNER))

    def requests(self):
        """The view and panel requests, in order."""
        return [('view' if at == REQUEST_VIEW else 'panel', regs[0]) for at, regs in self.m.log if at in (REQUEST_VIEW, REQUEST_PANEL)]


def tap(code):
    return [(code, PRESS), (code, RELEASE), (code, CLICK)]


def held(code):
    return [(code, PRESS), (code, HOLD), (code, RELEASE)]


@pytest.fixture
def h(m4emu):
    return Handler(m4emu)


def test_hold_settings():
    assert long_press.SETTINGS[:5] == long_press.HOLDS
    for n, s in zip((1, 2, 3, 4, 5), long_press.HOLDS):
        assert (s.key, s.label, s.default) == (f'fs{n}', f'Function\nFS{n} Hold'.encode(), n + 3), 'FS1..FS5 Hold default to FS6..FS10'
        assert s.values == (b'Off', b'Tuner', b'FS4', b'FS5', b'FS6', b'FS7', b'FS8', b'FS9', b'FS10')
        assert all(len(v) <= 8 for v in s.values)
    assert HOLD_IDS == [0xd2, 0xd3, 0xd4, 0xd5, 0xd6], 'a unit keeps a setting\'s value by ID: never move it once a build has used it'
    assert long_press.FLAG == 'HX_LONG_PRESS' and long_press.VIRTUAL_CC == 20


def test_function_settings():
    """FS6..FS10 Function: FS3..FS5 Function's values with Tuner for TAP/Tunr, Stomp N for this footswitch."""
    assert long_press.SETTINGS[5:] == long_press.FUNCTIONS
    for n, s in zip((6, 7, 8, 9, 10), long_press.FUNCTIONS):
        assert (s.key, s.label, s.default) == (f'fs{n}_function', f'Function\nFS{n}'.encode(), STOMP)
        assert s.values == (b'Tuner', f'Stomp {n}'.encode(), b'Bank Up', b'Bank Dn', b'PresetUp', b'PresetDn', b'SnpshtUp',
                            b'SnpshtDn', b'FS Mode>', b'<FS Mode', b'AllBypas', b'TogglEXP', b'GlobalEQ')
        assert all(len(v) <= 8 for v in s.values)
    assert FUNCTION_IDS == [0xda, 0xdb, 0xdc, 0xdd, 0xde], 'a unit keeps a setting\'s value by ID: never move it once a build has used it'


def test_xl_hold_settings_cover_eight_switches_and_five_virtual_functions():
    expected_ids = [0xd2, 0xd3, 0xd4, 0xd5, 0xd6, 0xed, 0xee, 0xef]
    keys = [f'long_press.fs{n}' if n <= 5 else f'long_press.fs{n}_hold' for n in range(1, 9)]
    assert [IDS[key] for key in keys] == expected_ids
    assert [setting_ids.packing()[setting_id] for setting_id in expected_ids[5:]] == [(116, 0, 4), (116, 4, 4), (116, 8, 4)]
    assert len(long_press.XL_HOLDS) == 8
    assert all(setting.default == 0 and setting.values == long_press.XL_HOLD_VALUES for setting in long_press.XL_HOLDS)
    assert [setting.label for setting in long_press.XL_FUNCTIONS] == [f'Function\nFS{n}'.encode() for n in range(9, 14)]
    assert all(setting.default == 1 and setting.values == long_press.XL_FUNCTION_VALUES for setting in long_press.XL_FUNCTIONS)
    assert not setting_ids.virtual_problems()
    include = pm.hxtra_inc(MODS, IDS, layout=pm.XL_MENU)
    assert '.equ SETTING_LONG_PRESS_FS8_HOLD, 239\n' in include
    assert '.equ VIRTUAL_FIRST, 9\n' == long_press.long_press_inc(pm.XL_MENU)


@pytest.mark.firmware
def test_xl_long_press_patches_the_event_handler_and_virtual_switch_hooks():
    path = os.environ.get('HX_STOMP_XL_HXF')
    if not path:
        pytest.skip('HX_STOMP_XL_HXF is not set')
    archive = pa.load_l6ia_from_any(path)[0]
    load = lambda n: pa.get_entry_swapped(archive, n)
    patch = pm.Patch(load(0), MODS, IDS, load=load, layout=pm.XL_MENU)
    patch.owner = 'long_press'
    long_press.apply(patch)
    patch.finish_chains()
    output = patch.output()
    module = patch.modules['src/m4/long_press_xl.s']
    assert branch_target(long_press.XL_HANDLER, patch.read(long_press.XL_HANDLER, 4)) == module['xl_hold_event']
    for site, stock, _what in long_press.XL_ASSIGNMENT_CALLS:
        assert patch.read(site, 4) != pm.bl(site, stock)
    assert patch.read(long_press.XL_MIDI_IN_FIRST, 2) == bytes.fromhex('1422')
    assert set(output) == {0}


@pytest.mark.firmware
def test_xl_long_press_registers_through_the_feature_gate():
    path = os.environ.get('HX_STOMP_XL_HXF')
    if not path:
        pytest.skip('HX_STOMP_XL_HXF is not set')
    archive = pa.load_l6ia_from_any(path)[0]
    load = lambda n: pa.get_entry_swapped(archive, n)
    output, on = pm.menu_entries(load, MODS, {'HX_LONG_PRESS': '1', 'HX_PRESET_COLOR': '1'}, IDS, layout=pm.XL_MENU)
    assert {'long_press', 'preset_color'} <= {features.name(module) for module in on}
    assert set(output) == {0, 7, 8}


def test_xl_holds_default_off_and_pass_all_native_switch_events(m4emu):
    code, symbols = m4emu.assemble('src/m4/long_press_xl.s', MODS, IDS, inc={
        'long_press_xl.inc': long_press.xl_long_press_inc()}, layout=pm.XL_MENU)
    machine = m4emu.M4(code, CODE)
    hold_ids = [IDS[f'long_press.fs{n}'] for n in range(1, 6)] + [IDS[f'long_press.fs{n}_hold'] for n in (6, 7, 8)]
    settings = {21: 0, **{pid: 0 for pid in hold_ids}}
    seen = []

    def get_setting(m):
        pid, output = m.reg('r0'), m.reg('r1')
        if pid not in settings:
            m.reg('r0', -1)
            return
        m.u8(output, 2)
        m.u32(output + 4, settings[pid])
        m.reg('r0', 0)

    machine.stub(pm.XL_MENU.get, get_setting)
    machine.stub(0x28d98ce4, lambda m: m.reg('r0', 0))
    machine.stub(long_press.XL_HANDLER + 4, lambda m: seen.append(m.read(m.reg('r0'), 8)),
                 code=bytes.fromhex('bde8f083'))

    def event(code, kind):
        machine.write(EVENT, bytes([1, code, 0, 0]) + struct.pack('<I', kind))
        machine.call(CODE + symbols['xl_hold_event'], EVENT, OBJ, 0)

    events = []
    for code in range(17, 25):
        events.extend((code, kind) for kind in (1, 5, 2, 3))
    for code in range(9, 17):
        events.extend((code, kind) for kind in (1, 5, 2))
    for code, kind in events:
        event(code, kind)
    assert [(item[1], struct.unpack_from('<I', item, 4)[0]) for item in seen] == events


@pytest.mark.parametrize('physical, action, cc', [(0, 2, 20), (1, 3, 21), (2, 4, 22), (3, 5, 23), (7, 6, 24)])
def test_xl_long_press_maps_physical_holds_to_virtual_ccs(m4emu, physical, action, cc):
    code, symbols = m4emu.assemble('src/m4/long_press_xl.s', MODS, IDS, inc={
        'long_press_xl.inc': long_press.xl_long_press_inc()}, layout=pm.XL_MENU)
    machine = m4emu.M4(code, CODE)
    holds = [IDS[f'long_press.fs{n}'] for n in range(1, 6)] + [IDS[f'long_press.fs{n}_hold'] for n in (6, 7, 8)]
    functions = [IDS[f'long_press.fs{n}_function'] for n in range(6, 11)]
    settings = {21: 0, holds[physical]: action, **{pid: 1 for pid in functions}}
    seen, controls = [], []
    manager, controllers = 0x28470000, 0x28480000

    def get_setting(m):
        pid, output = m.reg('r0'), m.reg('r1')
        if pid not in settings:
            m.reg('r0', -1)
            return
        m.u8(output, 2)
        m.u32(output + 4, settings[pid])
        m.reg('r0', 0)

    machine.stub(pm.XL_MENU.get, get_setting)
    machine.stub(0x28d98ce4, lambda m: m.reg('r0', 0))
    machine.stub(0x28d98c0c, lambda m: m.reg('r0', manager))
    machine.stub(0x28d98c14, lambda m: m.reg('r0', 0))
    machine.stub(0x28de05ac, lambda m: m.reg('r0', 0))
    machine.stub(0x28d98c1c, lambda m: m.reg('r0', controllers))
    machine.stub(0x28e2ae80)
    machine.stub(0x28e2aef8)
    machine.stub(0x28de40d0, lambda m: controls.append((m.reg('r0'), m.reg('r1'), m.reg('r2'), m.reg('r3'))))
    machine.stub(long_press.XL_HANDLER + 4, lambda m: seen.append(m.read(m.reg('r0'), 8)),
                 code=bytes.fromhex('bde8f083'))
    machine.u8(manager + 4 + physical * 2, 2)

    def event(kind):
        key_code = 17 + physical
        machine.write(EVENT, bytes([1, key_code, 0, 0]) + struct.pack('<I', kind))
        machine.call(CODE + symbols['xl_hold_event'], EVENT, OBJ, 0)

    event(1)
    event(5)
    event(2)
    assert controls == [(controllers, 11, cc, ON)]
    assert [(item[1], struct.unpack_from('<I', item, 4)[0]) for item in seen] == [(17 + physical, 2)]


def test_xl_hold_to_tuner_withholds_the_press_and_releases_stock(m4emu):
    code, symbols = m4emu.assemble('src/m4/long_press_xl.s', MODS, IDS, inc={
        'long_press_xl.inc': long_press.xl_long_press_inc()}, layout=pm.XL_MENU)
    machine = m4emu.M4(code, CODE)
    hold_id = IDS['long_press.fs8_hold']
    settings = {21: 0, hold_id: 1}
    seen, requests = [], []

    def get_setting(m):
        pid, output = m.reg('r0'), m.reg('r1')
        if pid not in settings:
            m.reg('r0', -1)
            return
        m.u8(output, 2)
        m.u32(output + 4, settings[pid])
        m.reg('r0', 0)

    machine.stub(pm.XL_MENU.get, get_setting)
    machine.stub(0x28d98ce4, lambda m: m.reg('r0', 0))
    machine.stub(0x28d98c0c, lambda m: m.reg('r0', 0x28470000))
    machine.stub(0x28d98c14, lambda m: m.reg('r0', 0))
    machine.stub(0x28de05ac, lambda m: m.reg('r0', 0))
    machine.stub(0x28d9919c, lambda m: requests.append('tuner'))
    machine.stub(long_press.XL_HANDLER + 4, lambda m: seen.append(m.read(m.reg('r0'), 8)),
                 code=bytes.fromhex('bde8f083'))
    machine.u8(0x28470000 + 4 + 7 * 2, 2)

    for kind in (1, 5, 2):
        machine.write(EVENT, bytes([1, 24, 0, 0]) + struct.pack('<I', kind))
        machine.call(CODE + symbols['xl_hold_event'], EVENT, OBJ, 0)
    assert requests == ['tuner']
    assert [(item[1], struct.unpack_from('<I', item, 4)[0]) for item in seen] == [(24, 2)]


def test_xl_virtual_snapshot_actions_use_eight_or_native_snapshot_stepper(m4emu):
    code, symbols = m4emu.assemble('src/m4/long_press_xl.s', MODS, IDS, inc={
        'long_press_xl.inc': long_press.xl_long_press_inc()}, layout=pm.XL_MENU)
    machine = m4emu.M4(code, CODE)
    manager, selected = 0x28470000, []
    machine.stub(0x28d98c34, lambda m: m.reg('r0', manager))
    machine.stub(0x28de8dcc, lambda m: selected.append((m.reg('r0'), m.reg('r1'))))
    for action, current, target in ((8, 3, 0), (9, 0, 3)):
        machine.u8(manager + 0xa03, current)
        machine.call(CODE + symbols['xl_step_snapshot'], action)
        assert selected[-1] == (manager, target)

    routed_code, routed_symbols = m4emu.assemble('src/m4/long_press_xl.s', MODS, IDS, inc={
        'long_press_xl.inc': long_press.xl_long_press_inc(0x28e50001)}, layout=pm.XL_MENU)
    routed = m4emu.M4(routed_code, CODE)
    values = []
    routed.stub(0x28e50000, lambda m: values.append((m.reg('r0'), m.reg('r1'))))
    for action in (8, 9):
        routed.call(CODE + routed_symbols['xl_step_snapshot'], action)
    assert values == [(69, 8), (69, 9)]


@pytest.mark.parametrize('action,current,target', [(11, 0, 1), (11, 3, 0), (12, 0, 3), (12, 2, 1)])
def test_xl_virtual_mode_actions_wrap_through_stock_modes(m4emu, action, current, target):
    code, symbols = m4emu.assemble('src/m4/long_press_xl.s', MODS, IDS, inc={
        'long_press_xl.inc': long_press.xl_long_press_inc()}, layout=pm.XL_MENU)
    machine = m4emu.M4(code, CODE)
    wrapper = 0x28e80000
    machine.load(wrapper, bytes.fromhex('20b50d46') + pm.bl(wrapper + 4, CODE + symbols['step_mode']) + bytes.fromhex('20bd'))
    changes, writes = [], []
    machine.stub(0x28dd9300, lambda m: changes.append((m.reg('r0'), m.reg('r1'))))
    machine.stub(0x28e0690c, lambda m: m.reg('r0', 0x28470000))
    machine.stub(0x28e25d20, lambda m: writes.append((m.reg('r0'), m.reg('r1'), m.u32(m.reg('r2') + 4), m.reg('r3'))))
    machine.u8(OBJ + 0x4d, current)
    machine.call(wrapper, action, OBJ)
    assert changes == [(OBJ, target)]
    assert writes == [(0x28470000, 21, target, 6)]


def test_xl_bypass_assign_labels_cc20_to_24_as_fs9_to_13(m4emu):
    code, symbols = m4emu.assemble('src/m4/long_press_xl.s', MODS, IDS, inc={
        'long_press_xl.inc': long_press.xl_long_press_inc()}, layout=pm.XL_MENU)
    machine = m4emu.M4(code, CODE)
    buffer = 0x28710000
    for cc, label in zip(range(20, 25), (b'FS9', b'FS10', b'FS11', b'FS12', b'FS13')):
        machine.write(buffer, b'CC00\0')
        machine.call(CODE + symbols['vfs_cc_text'], cc, buffer + 2)
        assert machine.read(buffer, len(label) + 1) == label + b'\0'


@pytest.mark.firmware
def test_the_values_follow_the_stock_ones_and_the_dispatch_switches_on_value_plus_one():
    """FS3 Function's stock value strings (20-byte slots) are FS6's values from Stomp on, each at its stock value, and the
    dispatch's bytes are as expected."""
    e0 = stock_e0()
    values = long_press.FUNCTIONS[0].values
    first = e0.index(b'TAP/Tunr' + b'\0' * 12 + b'Stomp 3\0')
    stock = [e0[first + 20 * i:].split(b'\0')[0] for i in range(12)]
    assert stock[0] == b'TAP/Tunr' and stock[1:] == [b'Stomp 3'] + list(values[2:GLOBAL_EQ])
    read = reader(e0)
    assert read(long_press.SWITCH, len(long_press.SWITCH_STOCK)) == long_press.SWITCH_STOCK
    assert read(long_press.TOGGLE_EXP, len(long_press.TOGGLE_EXP_STOCK)) == long_press.TOGGLE_EXP_STOCK


def test_with_no_hold_action_every_event_reaches_the_stock_handler_unchanged(h):
    events = tap(12) + held(13) + tap(14) + [(13, 4)]
    assert h.run(*events) == (events, 0)


def test_tap_with_a_hold_action_toggles_on_the_click(h):
    h.hold_action(1, TUNER)
    assert h.run((12, PRESS)) == ([], 0)
    assert h.run((12, RELEASE)) == ([(12, RELEASE)], 0)
    assert h.run((12, CLICK)) == ([(12, PRESS), (12, RELEASE)], 0)


def test_hold_opens_the_tuner_without_toggling(h):
    h.hold_action(2, TUNER)
    assert h.run(*held(13)) == ([(13, RELEASE)], 1)
    assert [5] == [v for v, *_ in h.m.calls(GUARD) if v != GLOBAL_EQ_VIEW]


def test_hold_does_not_open_the_tuner_when_the_guard_refuses(h):
    h.hold_action(3, TUNER)
    h.view = TUNER_VIEW
    assert h.run(*held(14)) == ([(14, RELEASE)], 0)


@pytest.mark.parametrize('action, code', [(FS4, 15), (FS5, 16)])
def test_hold_presses_fs4_or_fs5(h, action, code):
    h.hold_action(1, action)
    assert h.run(*held(12)) == ([(code, PRESS), (code, RELEASE), (12, RELEASE)], 0)


def test_each_footswitch_has_its_own_hold_action(h):
    h.hold_action(1, FS4)
    h.hold_action(3, FS5)
    assert h.run(*held(13)) == (held(13), 0)
    assert h.run(*held(14)) == ([(16, PRESS), (16, RELEASE), (14, RELEASE)], 0)
    assert h.run(*held(12)) == ([(15, PRESS), (15, RELEASE), (12, RELEASE)], 0)


@pytest.mark.parametrize('mode', [2, 3])
def test_preset_and_snapshot_modes_stay_stock(h, mode):
    h.hold_action(1, TUNER)
    h.settings[FS_MODE] = mode
    assert h.run(*held(12), *tap(12)) == (held(12) + tap(12), 0)


@pytest.mark.parametrize('function', [1, 5, 14])
def test_footswitches_that_are_not_stomps_stay_stock(h, function):
    h.hold_action(1, TUNER)
    h.function(0, function)
    assert h.run(*held(12)) == (held(12), 0)


def test_a_momentary_footswitch_stays_stock(h):
    h.hold_action(2, TUNER)
    h.momentary.add(1)
    assert h.run(*held(13)) == (held(13), 0)
    assert h.m.calls(GET_LISTS) and h.m.calls(MOMENTARY)[0][1] == 1


@pytest.mark.parametrize('model', LOOPERS)
def test_a_looper_footswitch_stays_stock(h, model):
    """The looper latches on the press and its hold (undo, clear) acts only then, so its switch keeps every event as stock."""
    h.hold_action(1, FS6)
    h.blocks(0, (1, 7))
    h.models[7] = model
    assert h.run(*held(12), *tap(12)) == (held(12) + tap(12), 0)
    assert not h.m.calls(CONTROL)


def test_a_looper_anywhere_in_the_list_counts(h):
    h.hold_action(3, TUNER)
    h.blocks(2, (1, 4), (2, 0), (1, 9))
    h.models.update({4: 100, 9: 505})
    assert h.run(*held(14)) == (held(14), 0)


@pytest.mark.parametrize('model', [0, 100, 503, 506, 569, 572, 615, 618])
def test_other_blocks_keep_the_hold_action(h, model):
    h.hold_action(1, TUNER)
    h.blocks(0, (1, 7))
    h.models[7] = model
    assert h.run(*held(12)) == ([(12, RELEASE)], 1)


def test_only_block_nodes_are_looked_up_and_a_failed_lookup_is_skipped(h):
    h.hold_action(1, TUNER)
    h.blocks(0, (2, 3), (1, 5), (1, 6))
    h.info_fails.add(5)
    h.models.update({3: 504, 5: 504})
    assert h.run(*held(12)) == ([(12, RELEASE)], 1)
    assert [o[1] for o in h.order if o[0] == 'info'] == [5, 6, 5, 6], 'press and hold each walk blocks 5 and 6 only'


def test_the_list_is_walked_under_the_widget_lock_with_a_cleared_info(h):
    h.hold_action(2, TUNER)
    h.blocks(1, (1, 5), (1, 6))
    h.run((13, PRESS))
    assert h.order == [('wlock',), ('info', 5, True), ('info', 6, True), ('wunlock',)]


def test_a_footswitch_with_no_hold_action_skips_the_walk(h):
    h.blocks(0, (1, 7))
    h.models[7] = 504
    h.run(*held(12))
    assert h.order == []


@pytest.mark.parametrize('n, code', [(4, 15), (5, 16)])
def test_external_footswitches_4_and_5_have_hold_actions(h, n, code):
    h.hold_action(n, TUNER)
    assert h.run(*held(code)) == ([(code, RELEASE)], 1)
    assert h.run(*tap(code)) == ([(code, RELEASE), (code, PRESS), (code, RELEASE)], 0)


def test_external_footswitch_holds_reach_virtual_footswitches(h):
    h.hold_action(5, FS6 + 4)
    h.node(2, kind=2, cc=24, block=6)
    h.bypassed[6] = 0
    assert h.hold(16) == [('get', 6), ('control', CONTROLLERS, 8, 24, OFF)]


def test_other_keys_and_sources_pass(h):
    for n in (1, 2, 3, 4, 5):
        h.hold_action(n, TUNER)
    events = held(17) + held(9) + held(11) + held(0)
    assert h.run(*events) == (events, 0)
    h.seen.clear()
    h.event(12, PRESS, source=2)
    assert h.seen == [(2, 12, PRESS)]


def test_a_hold_whose_action_went_away_gives_the_press_back(h):
    h.hold_action(1, TUNER)
    assert h.run((12, PRESS)) == ([], 0)
    h.hold_action(1, 0)
    assert h.run((12, HOLD), (12, RELEASE)) == ([(12, PRESS), (12, RELEASE), (12, RELEASE)], 0)


def test_stray_clicks_and_holds_pass(h):
    h.hold_action(1, TUNER)
    assert h.run((12, CLICK), (12, HOLD)) == ([(12, CLICK), (12, HOLD)], 0)


@pytest.mark.parametrize('bypassed, value', [(1, ON), (0, OFF)])
def test_virtual_footswitch_turns_its_blocks_to_the_opposite_of_the_first_ones_state(h, bypassed, value):
    h.hold_action(1, FS6)
    h.node(5, kind=2, cc=20, block=7)
    h.node(9, kind=2, cc=20, block=8)
    h.bypassed[7], h.bypassed[8] = bypassed, 1 - bypassed
    assert h.hold(12) == [('get', 7), ('control', CONTROLLERS, 8, 20, value)]
    assert h.seen == [(1, 12, RELEASE)]


@pytest.mark.parametrize('action, cc', [(FS6, 20), (FS6 + 1, 21), (FS6 + 4, 24)])
def test_each_virtual_footswitch_has_its_cc(h, action, cc):
    h.hold_action(2, action)
    h.node(3, kind=2, cc=cc, block=4)
    h.bypassed[4] = 1
    assert h.hold(13) == [('get', 4), ('control', CONTROLLERS, 8, cc, ON)]


def test_the_scan_skips_free_nodes_other_kinds_controllers_and_ccs(h):
    h.hold_action(1, FS6)
    h.node(0, kind=None, cc=20, block=1)
    h.node(1, kind=1, cc=20, block=2)
    h.node(2, kind=2, controller=3, cc=20, block=3)
    h.node(3, kind=2, cc=21, block=4)
    h.node(63, kind=2, cc=20, block=5)
    h.bypassed[5] = 0
    assert h.hold(12) == [('get', 5), ('control', CONTROLLERS, 8, 20, OFF)]


def test_the_scan_holds_only_the_controllers_lock_and_releases_it_before_the_calls(h):
    h.hold_action(1, FS6)
    h.node(4, kind=2, cc=20, block=9)
    h.bypassed[9] = 1
    h.hold(12)
    assert [o[0] for o in h.order] == ['wlock', 'wunlock', 'wlock', 'wunlock', 'lock', 'unlock', 'get', 'control'], \
        'the press and the hold each walk for a looper under the widget lock, released before the scan'
    assert h.order[4][1] == h.order[5][1] == CONTROLLERS + 4


def test_with_no_block_to_read_the_virtual_footswitch_alternates(h):
    h.hold_action(1, FS6)
    assert h.hold(12) == [('control', CONTROLLERS, 8, 20, ON)]
    assert h.hold(12) == [('control', CONTROLLERS, 8, 20, OFF)]
    h.node(6, kind=2, cc=20, block=11)          # assigned, but the getter does not know the block: alternate on
    assert h.hold(12) == [('get', 11), ('control', CONTROLLERS, 8, 20, ON)]
    h.bypassed[11] = 1                           # a read state wins over the alternation
    assert h.hold(12) == [('get', 11), ('control', CONTROLLERS, 8, 20, ON)]


@pytest.mark.parametrize('n, code', [(1, 12), (3, 14), (5, 16)])
def test_a_stored_value_out_of_range_reads_the_default(h, n, code):
    h.hold_action(n, 100)               # a value another build stored
    assert h.hold(code) == [('control', CONTROLLERS, 8, 20 + n - 1, ON)]


def test_an_unset_hold_reads_its_default(h):
    """A virtual setting no build has stored reads its default, so FS1..FS5 Hold start on FS6..FS10 with no first-boot write."""
    h.settings.pop(HOLD_IDS[2], None)
    assert h.hold(14) == [('control', CONTROLLERS, 8, 22, ON)]


def test_a_virtual_footswitch_on_stomp_toggles_its_cc_and_skips_the_dispatch(h):
    h.hold_action(1, FS6)
    h.virtual_function(6, STOMP)
    h.node(5, kind=2, cc=20, block=7)
    h.bypassed[7] = 1
    assert h.hold(12) == [('get', 7), ('control', CONTROLLERS, 8, 20, ON)]
    assert h.cases == []


@pytest.mark.parametrize('value', [BANK_UP, PRESET_UP, SNAPSHOT_DN, FS_MODE_UP, 10])
def test_a_virtual_footswitch_runs_its_function_as_a_press_and_release_of_the_held_footswitch(h, value):
    """The dispatch's switch, for footswitch k, with function value + 1: pressed, then released, as a stock press and release."""
    h.hold_action(2, FS6 + 2)
    h.virtual_function(8, value)
    assert h.hold(13) == []
    assert h.cases == [('switch', 1, value + 1, 1), ('switch', 1, value + 1, 0)]
    assert h.m.read(OBJ + 0x78 + 1, 1) == b'\0', 'footswitch 2 left unpressed, as its held-back press left it'
    assert h.seen == [(1, 13, RELEASE)]


@pytest.mark.parametrize('n, code', [(1, 12), (5, 16)])
def test_each_virtual_footswitch_has_its_own_function_and_runs_on_the_held_footswitch(h, n, code):
    h.hold_action(n, FS6 + 4)
    h.virtual_function(10, PRESET_UP)
    h.virtual_function(9, BANK_UP)
    h.hold(code)
    assert h.cases == [('switch', n - 1, PRESET_UP + 1, 1), ('switch', n - 1, PRESET_UP + 1, 0)]


def test_toggle_exp_switches_exp_unpressed_then_toggles_the_cc(h):
    """TogglEXP's body past its press check, unpressed so its stomp tail leaves the held footswitch's blocks alone, then CC 20 + n."""
    h.hold_action(3, FS6 + 1)
    h.virtual_function(7, TOGGLE_EXP)
    h.m.u8(OBJ + 0x78 + 2, 1)
    h.node(1, kind=2, cc=21, block=3)
    h.bypassed[3] = 0
    assert h.hold(14) == [('get', 3), ('control', CONTROLLERS, 8, 21, OFF)]
    assert h.cases == [('exp', 2, 0)]


def test_tuner_opens_the_tuner_as_a_tuner_hold_does(h):
    h.m.stub(TAP_CORE)
    h.hold_action(3, FS6 + 4)
    h.virtual_function(10, TUNER_FN)
    assert h.run(*held(14)) == ([(14, RELEASE)], 1)
    assert [5] == [v for v, *_ in h.m.calls(GUARD) if v != GLOBAL_EQ_VIEW] and not h.m.calls(TAP_CORE) and h.cases == []
    h.view = TUNER_VIEW
    assert h.run(*held(14)) == ([(14, RELEASE)], 0)


def test_a_stored_function_out_of_range_reads_stomp(h):
    h.hold_action(1, FS6)
    h.virtual_function(6, GLOBAL_EQ + 1)
    assert h.hold(12) == [('control', CONTROLLERS, 8, 20, ON)]
    assert h.cases == []


def test_global_eq_opens_global_eq_as_global_settings_does(h):
    """View gGlobalEQViewID, then its panel 8, as Global Settings' Global EQ item asks; no dispatch, no CC, no tuner."""
    h.hold_action(2, FS6 + 3)
    h.virtual_function(9, GLOBAL_EQ)
    h.node(0, kind=2, cc=23, block=4)
    assert h.run(*held(13)) == ([(13, RELEASE)], 0)
    assert h.requests() == [('view', GLOBAL_EQ_VIEW), ('panel', 8)]
    assert h.cases == [] and not h.m.calls(CONTROL)


@pytest.mark.parametrize('code', [12, 14, 16])
def test_in_global_eq_any_footswitch_press_goes_home_and_its_events_go_with_it(h, code):
    """As the Home key asks: view 0, then panel 1. The press, hold and release never reach the stock handler, so no block toggles
    and no tap counts; the click after the release passes, which the stock handler ignores."""
    h.view = GLOBAL_EQ_VIEW
    assert h.run(*held(code)) == ([], 0)
    assert h.requests() == [('view', HOME_VIEW), ('panel', 1)]
    h.view = HOME_VIEW
    assert h.run(*tap(code)) == (tap(code), 0), 'the next press is a normal one'


def test_global_eq_exit_holds_in_every_footswitch_mode_and_before_a_hold_action(h):
    h.settings[FS_MODE] = 3
    h.hold_action(1, TUNER)
    h.view = GLOBAL_EQ_VIEW
    assert h.run(*tap(12)) == ([(12, CLICK)], 0)
    assert h.requests() == [('view', HOME_VIEW), ('panel', 1)]


def test_outside_global_eq_presses_stay_as_they_were(h):
    h.view = TUNER_VIEW
    assert h.run(*tap(12)) == (tap(12), 0)
    assert h.requests() == []


def test_a_held_footswitchs_touch_hold_is_dropped(h):
    """Its touch hold would open "Assign block to FS?" in the Edit view, as the held-back press never cleared the touch."""
    h.hold_action(1, FS6)
    assert h.run((12, PRESS), (TOUCH1, HOLD)) == ([], 0)
    h.hold_action(2, 0)
    assert h.run((TOUCH1 + 1, PRESS), (TOUCH1 + 1, HOLD)) == ([(TOUCH1 + 1, PRESS), (TOUCH1 + 1, HOLD)], 0), 'a touch alone stays stock'


def test_a_hold_action_clears_its_touch_so_a_later_touch_hold_does_nothing(h):
    h.hold_action(3, FS6)
    h.m.u8(OBJ + TOUCHED + 2, 1)
    h.run(*held(14))
    assert h.m.read(OBJ + TOUCHED + 2, 1) == b'\0'
    h.hold_action(4, FS6)
    h.m.u8(OBJ + TOUCHED + 2, 1)
    h.run(*held(15))
    assert h.m.read(OBJ + TOUCHED + 2, 1) == b'\x01', 'FS4 has no touch'


def test_a_touch_hold_after_a_global_eq_exit_is_dropped(h):
    h.view = GLOBAL_EQ_VIEW
    assert h.run((13, PRESS), (TOUCH1 + 1, HOLD), (13, RELEASE)) == ([], 0)


def test_global_eq_leaves_the_tuner_alone(h):
    h.hold_action(1, FS6)
    h.virtual_function(6, GLOBAL_EQ)
    h.view = TUNER_VIEW
    assert h.run(*held(12)) == ([(12, RELEASE)], 0)
    assert h.requests() == []


@pytest.mark.firmware
def test_global_eq_requests_as_the_stock_global_eq_item_and_home_key_do():
    """Global Settings' Global EQ item ends with view 6 then a tail call of panel 8; the Home key with view 0 then panel 1."""
    read = reader(stock_e0())
    assert branch_target(0x28dce510, read(0x28dce510, 4)) == REQUEST_VIEW and read(0x28dce50e, 2) == bytes([GLOBAL_EQ_VIEW, 0x20])
    assert branch_target(0x28dce51c, read(0x28dce51c, 4)) == REQUEST_PANEL and read(0x28dce514, 2) == bytes([8, 0x20])
    assert branch_target(0x28dcfa1c, read(0x28dcfa1c, 4)) == REQUEST_VIEW and read(0x28dcfa1a, 2) == bytes([HOME_VIEW, 0x20])
    assert branch_target(0x28dcfa26, read(0x28dcfa26, 4)) == REQUEST_PANEL and read(0x28dcfa24, 2) == bytes([1, 0x20])


@pytest.mark.firmware
def test_the_looper_check_follows_the_stock_press():
    """The stock press clears a 0x34-byte info, looks each block up (0x28e0fe94) and, for a looper's category, tests the preset
    ID at info+1 with the 1 Switch and Shuffling Looper predicates; those take the IDs in LOOPERS."""
    read = reader(stock_e0())
    assert read(0x28dd1190, 4) == bytes.fromhex('0021 3422'), 'movs r1, #0; movs r2, #0x34'
    assert branch_target(0x28dd1196, read(0x28dd1196, 4)) == MEMSET
    assert branch_target(0x28dd11a2, read(0x28dd11a2, 4)) == BLOCK_INFO
    assert branch_target(0x28dd13b4, read(0x28dd13b4, 4)) == IS_LOOPER
    assert branch_target(0x28dd13c2, read(0x28dd13c2, 4)) == IS_SHUFFLING_LOOPER
    assert branch_target(0x28dd10e8, read(0x28dd10e8, 4)) == WIDGET_LOCK
    assert branch_target(0x28dd1110, read(0x28dd1110, 4)) == WIDGET_UNLOCK
    assert read(IS_LOOPER, 4) == bytes.fromhex('a0f5fc70'), 'sub.w r0, r0, #504'
    assert read(IS_SHUFFLING_LOOPER, 4) + read(IS_SHUFFLING_LOOPER + 8, 4) == bytes.fromhex('a0f23a23 a0f51a70'), \
        'subw r3, r0, #570; sub.w r0, r0, #616'


BUF = 0x28610000


def cc_text(h, cc):
    """The knob text after lp_cc_text runs on the stock "CC" + digits buffer, as at the three call sites."""
    h.m.write(BUF, b'CC' + str(cc).encode() + b'\0' * 7)
    h.m.call(CODE + h.sym['lp_cc_text'], cc, BUF + 2)
    return h.m.read(BUF, 9).split(b'\0')[0].decode()


@pytest.mark.parametrize('cc, text', [(20, 'FS6'), (21, 'FS7'), (22, 'FS8'), (23, 'FS9'), (24, 'FS10')])
def test_ccs_20_to_24_read_as_the_virtual_footswitches(h, cc, text):
    assert cc_text(h, cc) == text


@pytest.mark.parametrize('cc, text', [(20, 'FS9'), (21, 'FS10'), (22, 'FS11'), (23, 'FS12'), (24, 'FS13')])
def test_xl_ccs_read_as_virtual_footswitches(m4emu, cc, text):
    code, symbols = m4emu.assemble('src/m4/long_press.s', MODS, IDS,
                                   inc={'long_press.inc': long_press.long_press_inc(pm.XL_MENU)}, layout=pm.XL_MENU)
    m = m4emu.M4(code, CODE)
    m.write(BUF, b'CC' + str(cc).encode() + b'\0' * 7)
    m.call(CODE + symbols['lp_cc_text'], cc, BUF + 2)
    assert m.read(BUF, 9).split(b'\0')[0].decode() == text


@pytest.mark.parametrize('cc', [0, 4, 19, 25, 82, 127])
def test_other_ccs_keep_their_numbers(h, cc):
    assert cc_text(h, cc) == f'CC{cc}'


LABEL, NODE, MIDI_IN = 0x28dc63d0, 0x28620000, 0x28e3a0f4
MOV_R2_R5, MOV_R2_R4 = bytes.fromhex('2a46'), bytes.fromhex('2246')


def label(h, cc):
    """The label lp_label hands the knob label setter for a MIDI In node on cc, or for no node (Off) when cc is None."""
    h.m.stub(LABEL)
    h.m.log.clear()
    if cc is not None:
        h.m.u32(NODE + 0x14, cc)
    h.m.call(CODE + h.sym['lp_label'], 0, MIDI_IN, 0 if cc is None else NODE)
    [(knob, text)] = [regs[:2] for regs in h.m.calls(LABEL)]
    assert knob == 0
    return 'MIDI In' if text == MIDI_IN else h.m.read(text, 9).split(b'\0')[0].decode()


@pytest.mark.parametrize('cc', [20, 21, 22, 23, 24])
def test_the_virtual_footswitches_are_labelled_footswin(h, cc):
    assert label(h, cc) == 'FootswIn'


@pytest.mark.parametrize('cc', [None, 0, 4, 19, 25, 127])
def test_off_and_other_ccs_keep_the_midi_in_label(h, cc):
    assert label(h, cc) == 'MIDI In'


def test_each_label_entry_reads_its_callers_node(h, m4emu):
    """At the redraw's label call the MIDI In node is in r5; at the knob refresh's, in r4 (0 when MIDI In is Off)."""
    code, _ = m4emu.assemble('src/m4/long_press.s', MODS, IDS, inc={'long_press.inc': long_press.long_press_inc()})
    at = lambda name: h.sym[name] & ~1
    assert code[at('lp_label_redraw'):at('lp_label_redraw') + 2] == MOV_R2_R5
    assert code[at('lp_label_refresh'):at('lp_label_refresh') + 2] == MOV_R2_R4
    assert at('lp_label_refresh') + 2 == at('lp_label'), 'the refresh entry falls through into lp_label'


@pytest.mark.firmware
def test_build_owns_the_handler_and_hands_lp_event_the_stock_handler():
    read, on = built({'HX_LONG_PRESS': '1'})
    assert on == ['long_press', 'splash']
    veneer = branch_target(long_press.HANDLER, read(long_press.HANDLER, 4))
    hw = struct.unpack('<4H', read(veneer, 8))
    imm = lambda a, b: ((a & 0xf) << 12) | (((a >> 10) & 1) << 11) | (((b >> 12) & 7) << 8) | (b & 0xff)
    assert (hw[0] & 0xfbf0, hw[2] & 0xfbf0, (hw[1] >> 8) & 0xf, (hw[3] >> 8) & 0xf) == (0xf240, 0xf2c0, 2, 2)
    stock = imm(hw[0], hw[1]) | imm(hw[2], hw[3]) << 16
    assert stock & 1
    assert read(stock & ~1, 4) == long_press.HANDLER_STOCK
    assert branch_target((stock & ~1) + 4, read((stock & ~1) + 4, 4)) == long_press.HANDLER + 4
    lp_event = branch_target(veneer + 8, read(veneer + 8, 4))
    assert read(lp_event, 2) == bytes.fromhex('2de9')    # push.w {r4-r8,lr}
    assert read(HOME_CTOR_CALL, 4) == pm.bl(HOME_CTOR_CALL, HOME_CTOR), 'no boot hook: unset virtual settings read their defaults'
    assert read(long_press.SWITCH, len(long_press.SWITCH_STOCK)) == long_press.SWITCH_STOCK, 'the dispatch stays stock: lp enters it'
    assert read(long_press.MIDI_IN_FIRST, 2) == bytes([20, 0x22]), 'MIDI In: the first step up from Off is FS6\'s CC 20'
    for site in long_press.CC_TEXT_CALLS:
        assert read(site, 4) != pm.bl(site, long_press.ITOA), f'the CC text at {site:#x} is chained'
    for site, mov in zip((0x28dbb6c2, 0x28dbbce6), (MOV_R2_R5, MOV_R2_R4)):
        assert read(branch_target(site, read(site, 4)), 2) == mov, f'the label call at {site:#x} goes to its lp_label entry'


@pytest.mark.firmware
def test_build_serves_the_holds_and_functions_as_virtual_settings():
    e0 = built_e0({'HX_LONG_PRESS': '1'})
    for s in long_press.SETTINGS:
        assert_virtual(e0, long_press, s)


@pytest.mark.firmware
def test_without_the_flag_the_handler_stays_stock():
    read, on = built({})
    assert 'long_press' not in on
    assert read(long_press.HANDLER, 4) == long_press.HANDLER_STOCK
    assert read(long_press.MIDI_IN_FIRST, 2) == long_press.MIDI_IN_FIRST_STOCK
    for site in long_press.CC_TEXT_CALLS:
        assert read(site, 4) == pm.bl(site, long_press.ITOA)
    for site, _ in long_press.LABEL_CALLS:
        assert read(site, 4) == pm.bl(site, long_press.LABEL)


@pytest.mark.firmware
def test_builds_alongside_the_tuner_bpm_and_dsp_meter():
    _, on = built({'HX_LONG_PRESS': '1', 'HX_BPM': '1', 'HX_DSP_METER': '1', 'HX_TUNER': '1'})
    assert on == ['tuner', 'bpm', 'dsp_meter', 'long_press', 'splash']
