#!/usr/bin/env python3
"""hx_input.py - the HX Stomp or HX Stomp XL's footswitches, knobs and buttons from this computer, on a build with HX_USB_INPUT=1
(tools/features/usb_input.py).

Each call is one request on HX Edit's editor service (command 0x51), so HX Edit must be closed. The unit queues the events as its
own controls queue theirs (src/m4/usb_input.s), so its UI cannot tell them apart.

    hx_input.py press fs2                 # a click: pressed, then released (fs1..fs5 on Stomp, fs1..fs8 on XL,
                                                                                # knob1..knob5, view, action, page_left, page_right)
  hx_input.py press view+action         # controls joined by + are pressed together and released together: Save
  hx_input.py hold fs1 [--seconds 1.5]  # held: the hold comes after 1 s, as the unit's own
  hx_input.py turn knob3 -4             # four clicks anticlockwise
    hx_input.py touch fs1 [--seconds 1]   # FS1..FS3's touch sensors on Stomp, FS1..FS6 on XL

A script uses Input(ctl): with an hx_mirror.Session, Input(s.ctl) presses while the mirror records, its calls taking turns with
the frames.
"""
import argparse
import os
import struct
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hx_ctl  # noqa: E402
from hx_dfu_reboot import PID_HX_STOMP, PID_HX_STOMP_XL  # noqa: E402
from hx_mirror import STOMP  # noqa: E402

PRESS, RELEASE, RELEASED, HOLD = 1, 2, 3, 5     # key events' types; RELEASED follows a release that came before the hold
HOLD_S = 1.0                                    # every key's hold, docs/research/m4/footswitches.md
CLICK_S = 0.08
GAP_S = 0.05        # between clicks: the queue drops a key event equal to one still in it, so the same press twice needs a gap
MAX = 16            # events a request (src/m4/usb_input.s)
XL = {**STOMP,
    **{f'fs{n}': {'press': [1, 16 + n]} for n in range(1, 9)},
    **{f'fs{n}': {'press': [1, 16 + n], 'touch': [1, 8 + n]} for n in range(1, 7)}}


def event(cls, code, value=0):
    """An 8-byte UI event {class, code, 0, 0, value}: a key's type or a knob's clicks."""
    return bytes([cls, code, 0, 0]) + struct.pack('<i', value)


def keys(names, typ, part='press', controls=STOMP):
    """The key events of the controls in names, joined by + when pressed together."""
    return [key(n, typ, part, controls) for n in names.split('+')]


def key(name, typ, part='press', controls=STOMP):
    """The key event of control name's press (or its touch) of type typ."""
    try:
        cls, code = controls[name][part]
    except KeyError:
        raise ValueError(f'{name} has no {part}: one of ' +
                         ', '.join(n for n in controls if part in controls[n] and controls[n][part][0] == 1)) from None
    if cls != 1:
        raise ValueError(f'{name} is not a key')
    return event(cls, code, typ)


class Input:
    """The controls of the unit an hx_ctl session (or an hx_mirror.Session's s.ctl) talks to."""

    def __init__(self, ctl, sleep=time.sleep):
        self.ctl, self.sleep = ctl, sleep
        pid = getattr(getattr(getattr(ctl, 'link', None), 'dev', None), 'idProduct', None)
        if pid not in (None, PID_HX_STOMP, PID_HX_STOMP_XL):
            raise ValueError(f'unsupported USB product id: {pid:#x}')
        self.controls = XL if pid == PID_HX_STOMP_XL else STOMP

    def send(self, *events):
        for i in range(0, len(events), MAX):
            self.ctl.send_events(b''.join(events[i:i + MAX]))

    def key(self, name, typ, part='press'):
        return key(name, typ, part, self.controls)

    def press(self, name, seconds=CLICK_S):
        """A click of a footswitch, a knob or a button, released before its hold; 'view+action' presses them together."""
        if seconds >= HOLD_S:
            return self.hold(name, seconds)
        self.send(*keys(name, PRESS, controls=self.controls))
        self.sleep(seconds)
        self.send(*keys(name, RELEASE, controls=self.controls), *keys(name, RELEASED, controls=self.controls))
        self.sleep(GAP_S)

    def hold(self, name, seconds=1.5):
        """Held for seconds (at least HOLD_S): pressed, its hold after HOLD_S, released; 'fs1+fs2' holds them together."""
        self.send(*keys(name, PRESS, controls=self.controls))
        self.sleep(HOLD_S)
        self.send(*keys(name, HOLD, controls=self.controls))
        self.sleep(max(0.0, seconds - HOLD_S))
        self.send(*keys(name, RELEASE, controls=self.controls))
        self.sleep(GAP_S)

    def turn(self, name, clicks):
        """clicks of a knob, clockwise when positive."""
        if not clicks:
            return
        cls, code, sign = self.controls[name]['turn']
        self.send(event(cls, code, clicks * sign))
        self.sleep(GAP_S)

    def touch(self, name, seconds=CLICK_S):
        """A foot on a touch sensor for seconds; 'fs1+fs2' touches both."""
        self.send(*keys(name, PRESS, 'touch', self.controls))
        self.sleep(seconds)
        self.send(*keys(name, RELEASE, 'touch', self.controls))
        self.sleep(GAP_S)


def main(argv=None):
    ap = argparse.ArgumentParser(description='Press, hold and turn the HX Stomp or HX Stomp XL controls over USB (HX_USB_INPUT=1).')
    sub = ap.add_subparsers(dest='what', required=True)
    for what in ('press', 'hold', 'touch'):
        a = sub.add_parser(what)
        a.add_argument('control')
        a.add_argument('--seconds', type=float, default=1.5 if what == 'hold' else CLICK_S)
    a = sub.add_parser('turn')
    a.add_argument('control')
    a.add_argument('clicks', type=int)
    ap.add_argument('-v', '--verbose', action='store_true')
    args = ap.parse_args(argv)
    with hx_ctl.HxCtl(verbose=args.verbose) as ctl:
        i = Input(ctl)
        if args.what == 'turn':
            i.turn(args.control, args.clicks)
        else:
            getattr(i, args.what)(args.control, args.seconds)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, hx_ctl.HxError) as e:
        sys.exit(f'hx_input: {e}')
