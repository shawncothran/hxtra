"""Path A Out's DSP side (issues #81, #93): src/sharc/usb_monitor.asm in ssim (the Level gain's control function taking the mode
out of USB Input Trim, the Send jacks' writer silenced in USB Only), what the transport relies on in the stock app, its place in
Block 3, the registry and build.py's steps."""
import importlib.util
import os
import re
import struct
import sys
from pathlib import Path

import pytest

import block3
import patch_amp as pa
import patch_usbmon as pu
import sasm
import ssim

ROOT = Path(__file__).resolve().parent.parent
QUIET = dict(log=lambda *_: None)
WRITER, CTRL = 0x90100, 0x90300           # stand-ins for the Send writer's stock process code and the gain's control function
SRC, COPY = 0x7000, 0x7100                # the stand-in writer copies its 16-sample input (I1) to COPY
VALUE = 0x5000                            # the value slot R8 points at
f2u = lambda f: struct.unpack('<I', struct.pack('<f', f))[0]
u2f = lambda u: struct.unpack('<f', struct.pack('<I', u))[0]


# ---- the DSP code, in ssim

def dsp():
    src = pu.dsp_asm(0xe7a00, 0xe5200)
    for k, v in (('ORIG_2AAA', WRITER), ('ORIG_CTRL_80', CTRL)):
        src, n = re.subn(r'(\.equ %s,\s*)0x[0-9a-fA-F]+' % k, r'\g<1>%#x' % v, src)
        assert n == 1, k
    src += f"""
.section dm 0x6f00
SEEN: .space 4
.section pm {WRITER:#x}
    I4 = {COPY:#x};
    LCNTR = 16, DO fw UNTIL LCE;
      R0 = DM(I1, 1);
fw:   DM(I4, 1) = R0;
    RTS;
.section pm {CTRL:#x}
    R0 = 0x777;
    DM(SEEN) = R0;
    DM(SEEN + 1) = R4;
    DM(SEEN + 2) = R8;
    I4 = R8;
    R0 = DM(0, I4);
    DM(SEEN + 3) = R0;
    RTS;
"""
    secs, syms = sasm.assemble(src, 'usb_monitor_test')
    s = ssim.Sim()
    s.load(secs)
    return s, syms


def ctrl(s, syms, pid, word):
    """The control function as the framework calls it: pid R4, a pointer to the value R8, the gain's state R12 -> (pid, pointer,
    value word) the stock function got, None when it was not called."""
    s.wr(VALUE, word & 0xffffffff)
    s.u[4], s.u[8], s.u[12], s.u[3] = pid, VALUE, 0x6000, 0x1234
    s.wr(syms['SEEN'], 0)
    s.call(syms['CTRL_80'])
    assert (s.u[3], s.u[12]) == (0x1234, 0x6000)
    if s.rd(syms['SEEN']) != 0x777:
        return None
    return tuple(s.rd(syms['SEEN'] + k) for k in (1, 2, 3))


def code(mode, trim):
    """What the M4 sends for a mode: trim + 1000 * (mode + 1)."""
    return f2u(trim + 1000 * (mode + 1))


def write(s, syms):
    """One call of the wrapped Send writer on samples 1..16: what reached the stock writer, and I1 after."""
    for k in range(16):
        s.wr(SRC + k, k + 1)
    s.u[0x11] = SRC
    s.call(syms['ENTRY_2AAA'])
    return [s.rd(COPY + k) for k in range(16)], s.u[0x11]


@pytest.mark.parametrize('mode', [0, 1, 3])
def test_other_modes_write_the_send_jacks(mode):
    s, syms = dsp()
    ctrl(s, syms, 1, code(mode, 0.0))
    samples, i1 = write(s, syms)
    assert samples == list(range(1, 17)) and i1 == SRC


def test_usb_only_writes_silence_to_the_send_jacks():
    s, syms = dsp()
    ctrl(s, syms, 1, code(2, 0.0))
    samples, i1 = write(s, syms)
    assert samples == [0] * 16 and i1 == SRC, 'silence, and I1 back as it came'
    ctrl(s, syms, 1, code(1, 0.0))
    assert write(s, syms)[0] == list(range(1, 17)), 'back to stock'


def test_the_mode_starts_stock():
    s, syms = dsp()
    assert s.rd(syms['USB_MODE']) == 0
    assert write(s, syms)[0] == list(range(1, 17))


@pytest.mark.parametrize('mode', range(pu.MODE_MAX + 1))
@pytest.mark.parametrize('trim', [-60.0, -12.5, 0.0, 18.0])
def test_the_mode_comes_out_and_the_trim_goes_on(mode, trim):
    s, syms = dsp()
    pid, ptr, word = ctrl(s, syms, 1, code(mode, trim))
    assert s.rd(syms['USB_MODE']) == mode
    assert (pid, ptr) == (1, VALUE) and u2f(word) == trim, 'the stock function gets the trim alone'


@pytest.mark.parametrize('pid, word', [(1, f2u(v)) for v in (0.0, -12.5, -120.0, 20.0, 500.0, 5000.0, -3000.0)]
                         + [(p, code(2, 0.0)) for p in (0, 2, 3, 100)] + [(1, f2u(1e30)), (1, f2u(-1e30)), (2, 7)])
def test_everything_else_reaches_the_stock_control_function_unchanged(pid, word):
    """0x80 is in many blocks: any pid but 1, and pid 1 at or below 500 or above the last mode, goes on as it came."""
    s, syms = dsp()
    s.wr(syms['USB_MODE'], 1)
    assert ctrl(s, syms, pid, word) == (pid, VALUE, word)
    assert s.rd(syms['USB_MODE']) == 1, 'the mode as it was'


def test_dsp_is_under_the_gr_meter_in_block3():
    assert block3.FEATURES[3] == ('HX_USB_MONITOR', 'patch_usbmon')
    env = {'HX_CLICK': '1', 'HX_FX_GATE': '1', 'HX_GR': '1', 'HX_USB_MONITOR': '1'}
    dm, pm = block3.place('HX_USB_MONITOR', env)
    n_dm, n_pm = pu.dsp_size()
    gr_dm, gr_pm = block3.place('HX_GR', env)
    assert dm + n_dm == block3.nw(pm) and block3.nw(pm + n_pm) <= gr_dm and pm % 2 == 0
    assert dm >= block3.room(block3.slots(env))[0]
    assert pu.mode_word(env) == dm, 'USB_MODE is the first data word'


# ---- the firmware tools/patch_usbmon.py builds, and the stock app it relies on

def stock_l6ia():
    stock = os.environ.get('HX_STOMP_HXF')
    if not stock:
        pytest.skip('HX_STOMP_HXF is not set')
    return pa.load_l6ia_from_any(stock)[0]


@pytest.fixture(scope='module')
def patched():
    data = stock_l6ia()
    return data, pu.patch_dsp(data, **QUIET)


def ldr_blocks(data):
    e = pa.l6ia.parse(data)[2]
    raw = data[e['payload_off']: e['payload_off'] + e['payload_len']]
    w = struct.unpack('<%dI' % (len(raw) // 4), raw)
    size = {5: lambda c: ((c + 1) & ~1) * 3 // 2, 4: lambda c: c, 3: lambda c: (c + 1) // 2,
            6: lambda c: c * 2, 10: lambda c: c, 9: lambda c: c}
    i, out = 384, []
    while w[i] != 0:
        tag, cnt, addr = w[i:i + 3]
        n = size.get(tag, lambda c: 0)(cnt)
        out.append((tag, addr, tuple(w[i + 3:i + 3 + n])))
        i += 3 + n
    return out


@pytest.mark.firmware
def test_the_writers_and_the_gain_enter_the_dsp_code(patched):
    _, new = patched
    dm, pm = pu.dsp_place()
    _, syms = pa.sasm.assemble(pu.dsp_asm(dm, pm), 'usb_monitor.asm')
    rows = {b[0]: b for t, a, b in ldr_blocks(new) if t == 4 and len(b) == 8}
    assert rows[pu.SEND][4:6] == (0x60a5ed, syms['ENTRY_2AAA']), 'the writer\'s process code, its control function stock'
    assert rows[pu.GAIN][4:6] == (syms['CTRL_80'], pu.GAIN_PROC), 'the gain\'s control function, its process code stock'
    assert rows[pu.MAIN][4:6] == (0x60a5ed, syms['ENTRY_2AA8']), 'the Main writer\'s process code (Main+Snd), its control stock'
    assert rows[pu.PHONES][4:6] == (0x60a5ed, syms['ENTRY_2AAB']), 'the phones writer\'s process code, its control stock'
    assert rows[pu.USB_OUT][4:6] == (0x60a5ed, syms['ENTRY_2AAC']), 'USB out\'s process code (USB 3/4), its control stock'


@pytest.mark.firmware
def test_only_entry2_changes(patched):
    """Blob 1 cannot change at all (one word of it hangs the unit at boot): the transport needs no other entry."""
    data, new = patched
    old, now = pa.l6ia.parse(data), pa.l6ia.parse(new)
    assert len(old) == len(now)
    for k, (a, b) in enumerate(zip(old, now)):
        if k != 2:
            assert data[a['payload_off']: a['payload_off'] + a['payload_len']] == \
                new[b['payload_off']: b['payload_off'] + b['payload_len']], f'entry {k}'


@pytest.mark.firmware
def test_xl_monitor_uses_the_same_dsp_payload(patched):
    path = os.environ.get('HX_STOMP_XL_HXF')
    if not path:
        pytest.skip('HX_STOMP_XL_HXF is not set')
    xl = pa.load_l6ia_from_any(path)[0]
    out = pu.patch_dsp(xl, **QUIET)
    assert pa.get_entry_swapped(out, 2) == pa.get_entry_swapped(patched[1], 2)
    assert all(pa.get_entry_swapped(out, index) == pa.get_entry_swapped(xl, index) for index in (0, 3, 4))


@pytest.mark.firmware
def test_usb_input_trim_reaches_two_level_gains_as_it_comes():
    """usbInGain0_1 (string 4209, slot 56): a float input node straight to writers [99] and [105], pid 1, members the root's 98 and
    104 in blob 0, both 0x80; blob 1 does not override them."""
    data = stock_l6ia()
    info = pa.parse_entry3_full(pa.get_entry_swapped(data, 3))
    app = info['models'][0]
    trim, = [p for p in app['params'] if p['name'] == 'usbInGain0_1']
    assert info['strings'].index('usbInGain0_1') == 4209 and trim['slot'] == 56
    e4 = pa.get_entry_swapped(data, 4)
    w4 = struct.unpack('<%dI' % (len(e4) // 4), e4)
    b = pa.entry4_blob.blob(w4, app['blob_index'])
    pm = b[b[6]: b[6] + b[7]]
    nodes = [pm[pm[0] + 10 * k: pm[0] + 10 * k + 10] for k in range(pm[18])]
    ct = [pm[pm[4] + 4 * k: pm[4] + 4 * k + 4] for k in range(pm[20])]
    dt = [pm[pm[6] + 4 * k: pm[6] + 4 * k + 4] for k in range(pm[21])]
    node, = [r[0] for r in dt if r[2] == 56]
    assert nodes[node][3] == 0x0a, 'a float input node'
    writes = set()
    for to in [r[1] for r in ct if r[0] == node]:
        assert nodes[to][3] == 1, 'nothing between the input and its writers'
        p, pid = pm[nodes[to][0]: nodes[to][0] + 2]
        writes.add((tuple(b[p + 1: p + 1 + b[p]]), pid))
    assert writes == {((99,), 1), ((105,), 1)}
    root = b[b[2]: b[2] + 4]
    overridden = {b[root[2] + 4 * k] for k in range(root[3]) if b[root[2] + 4 * k + 1] != 0xffffffff}
    assert not overridden & {99, 105}
    b0 = pa.entry4_blob.blob(w4, 0)
    n, at = b0[0xa], b0[0xb]
    members = [b0[at + 20 * k: at + 20 * k + 20] for k in range(n)]
    assert [m[0] for m in members] == list(range(n))
    assert members[98][6] == members[104][6] == pu.GAIN, 'slot k is member k - 1'
    assert members[82][6] == 0x600009, 'as blob 1 overrides slot 83 with the output block 0x60000a'


def build_steps(tmp_path, monkeypatch, unit, env):
    spec = importlib.util.spec_from_file_location('hxtra_build', ROOT / 'build.py')
    build = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build)
    stock = tmp_path / 'stock.hxf'
    stock.write_bytes(b'not firmware')
    import hashlib
    monkeypatch.setattr(build, 'STOCK_MD5', {hashlib.md5(stock.read_bytes()).hexdigest(): unit})
    for k in ('HX_GR', 'HX_CLICK', 'HX_FX_GATE', 'HX_USB_MONITOR'):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(build.os, 'replace', lambda *a: None)
    monkeypatch.setattr(build.os, 'remove', lambda *a: None)
    monkeypatch.setattr(sys, 'argv', ['build.py', str(stock), '-o', str(tmp_path / 'out.hxf'), '--no-check'])
    ran = []
    monkeypatch.setattr(build, 'run', lambda *a: ran.append(a[1:]) or 'ALL OK')
    build.main()
    return [a[0] for a in ran]


def test_build_order(tmp_path, monkeypatch):
    ran = build_steps(tmp_path, monkeypatch, 'HX_Stomp', {k: '1' for k in ('HX_CLICK', 'HX_FX_GATE', 'HX_GR', 'HX_USB_MONITOR')})
    assert ran.index('tools/patch_click.py') < ran.index('tools/patch_gate.py') < ran.index('tools/patch_usbmon.py') \
        < ran.index('tools/patch_comp.py')


def test_build_without_the_flag(tmp_path, monkeypatch):
    assert 'tools/patch_usbmon.py' not in build_steps(tmp_path, monkeypatch, 'HX_Stomp', {})
