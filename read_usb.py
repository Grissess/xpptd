import array
import usb
import libevdev as e
from libevdev import InputAbsInfo, InputEvent, Device

class Tablet(object):
    VENDOR = 0x28bd
    PRODUCT = 0x094a

    SETUP_CMD1 = array.array('B',
            [0x02, 0xb0, 0x04] + 7 * [0]
    )
    SETUP_CMD2 = array.array('B',
            [0x02, 0xb4, 0x01, 0x00, 0x01] + 7 * [0]
    )

    B1_REPORT = 0x02

    B2_MASK = 0xf0
    B2_BUTTONS = 0xf0
    B2_MOTION = 0xa0
    B2_LIFT = 0xc0
    B2_BT_MASK = 0x07
    B2_BT_TOUCH = 0x01
    B2_BT_LOWER = 0x02
    B2_BT_UPPER = 0x04

    B_TILT_HORIZ = 8
    B_TILT_VERT = 9
    T_MIN = -61
    T_MAX = 60

    B_X = 2
    B_Y = 4
    B_P = 6
    # You can override these if you have a tablet that isn't mine
    X_MAX = 0xcd9e
    Y_MAX = 0x73b0
    P_BIAS = 0x2000
    P_MAX = 0x1fff

    def __init__(self):
        self.dev = usb.core.find(idVendor = self.VENDOR, idProduct = self.PRODUCT)
        try:
            self.dev.set_configuration()
        except usb.core.USBError:
            print("Couldn't set configuration--the interface might already be claimed")
        self.cfg = self.dev.get_active_configuration()
        for intf in self.cfg.interfaces():
            try:
                self.dev.detach_kernel_driver(intf.bInterfaceNumber)
            except usb.core.USBError:
                print(f"Failed to detach interface {intf.bInterfaceNumber}--no kernel driver?")
        self.int = self.cfg[2, 0]
        self.int.set_altsetting()
        self.epi, self.epo = self.int.endpoints()
        self.epo.write(self.SETUP_CMD1)
        self.epo.write(self.SETUP_CMD2)
        self.buf = array.array('B', range(12))

        self.buttons = 0  # bitmask of all 8 buttons, "top left" LSB and in order down the side
        self.stylus = 0  # bitmask of B2_BT_*
        self.tracking = False  # is the stylus being tracked?
        self.tilt = (0, 0)  # horiz/vert tilt of the stylus, both as signed bytes, 0 = approximate orthogonal
        # (NOTE: LIFT always includes a 1,1 message for tilt that we ignore)
        self.pos = (0.0, 0.0)  # normalized X, Y of the stylus
        self.raw_pos = (0, 0)  # actually reported X, Y of stylus, no remapping done
        self.pressure = 0.0  # normalized pressure of stylus tip
        self.raw_pressure = 0  # unmapped pressure (NOTE: there's a bias to this, see the constants)

    def process(self):
        buf = self.buf
        while True:
            try:
                self.epi.read(buf)
            except usb.core.USBTimeoutError:
                continue

            if buf[0] != self.B1_REPORT:
                continue

            kind = buf[1] & self.B2_MASK

            if kind == self.B2_BUTTONS:
                self.buttons = buf[2]
            
            elif kind == self.B2_MOTION or kind == self.B2_LIFT:
                self.tracking = kind == self.B2_MOTION
                self.stylus = buf[1] & self.B2_BT_MASK

                # Ignore spurious (1,1) tilt on lift
                if kind == self.B2_MOTION:
                    self.tilt = (
                            int.from_bytes(buf[self.B_TILT_HORIZ:self.B_TILT_HORIZ+1], byteorder = 'little', signed = True),
                            int.from_bytes(buf[self.B_TILT_VERT:self.B_TILT_VERT+1], byteorder = 'little', signed = True)
                    )

                self.raw_pos = (
                        int.from_bytes(buf[self.B_X:self.B_X+2], byteorder = 'little', signed = False),
                        int.from_bytes(buf[self.B_Y:self.B_Y+2], byteorder = 'little', signed = False),
                )
                self.pos = (float(self.raw_pos[0]) / self.X_MAX, float(self.raw_pos[1]) / self.Y_MAX)
                self.raw_pressure = int.from_bytes(buf[self.B_P:self.B_P+2], byteorder = 'little', signed = False)
                self.pressure = float(self.raw_pressure - self.P_BIAS) / self.P_MAX

            yield self  # Some state changed, probably

    def __repr__(self):
        return f'<Tablet prox {1 if self.tracking else 0} x,y,p,tx,ty = {self.pos[0]:.03f},{self.pos[1]:.03f},{self.pressure:.03f},{self.tilt[0]},{self.tilt[1]} ({self.raw_pos[0]:04x},{self.raw_pos[1]:04x},{self.raw_pressure:04x}) s = {self.stylus:x} b = {self.buttons:02x}>'

class InputModel(object):
    MAX = 0xffff

    def set_caps(self, dev):
        dev.enable(e.INPUT_PROP_POINTER)
        dev.enable(e.INPUT_PROP_DIRECT)

        k = e.EV_KEY
        for btn in [
                k.BTN_TOOL_PEN,
                k.BTN_TOUCH, k.BTN_STYLUS, k.BTN_STYLUS2,
                k.BTN_0, k.BTN_1, k.BTN_2, k.BTN_3,
                k.BTN_4, k.BTN_5, k.BTN_6, k.BTN_7,
        ]:
            dev.enable(btn)

        # TODO: find the meaning of an arbitrary resolution, required by libinput
        ai = InputAbsInfo(value=0, minimum=0, maximum=self.MAX, fuzz=0, flat=0, resolution=300)
        ait = InputAbsInfo(value=0, minimum=Tablet.T_MIN, maximum=Tablet.T_MAX, fuzz=0, flat=0, resolution=0)
        dev.enable(e.EV_ABS.ABS_X, ai)
        dev.enable(e.EV_ABS.ABS_Y, ai)
        dev.enable(e.EV_ABS.ABS_PRESSURE, ai)
        dev.enable(e.EV_ABS.ABS_TILT_X, ait)
        dev.enable(e.EV_ABS.ABS_TILT_Y, ait)

    def __init__(self):
        self.ui = Device()
        self.ui.name = 'python-htd'
        self.set_caps(self.ui)
        self.ui = self.ui.create_uinput_device()
        # Mostly to avoid redundancy
        self.mbs = 0  # mouse button state
        self.bts = 0  # pad button state
        self.ts = False  # tracking state

    def update(self, tab):
        eq = []
        ts = tab.tracking
        mbs = tab.stylus
        bts = tab.buttons

        if ts != self.ts:
            eq.append(InputEvent(e.EV_KEY.BTN_TOOL_PEN, 1 if ts else 0))
            self.ts = ts

        if self.mbs != mbs:
            eq.append(InputEvent(e.EV_KEY.BTN_TOUCH, 1 if mbs & Tablet.B2_BT_TOUCH else 0))
            eq.append(InputEvent(e.EV_KEY.BTN_STYLUS, 1 if mbs & Tablet.B2_BT_LOWER else 0))
            eq.append(InputEvent(e.EV_KEY.BTN_STYLUS2, 1 if mbs & Tablet.B2_BT_UPPER else 0))
            self.mbs = mbs

        if self.bts != bts:
            for i in range(8):
                pot = 2**i
                eq.append(InputEvent(getattr(e.EV_KEY, f'BTN_{i}'), 1 if pot & bts else 0))
            self.bts = bts

        eq.extend((
            InputEvent(e.EV_ABS.ABS_X, int(self.MAX * tab.pos[0])),
            InputEvent(e.EV_ABS.ABS_Y, int(self.MAX * tab.pos[1])),
            InputEvent(e.EV_ABS.ABS_PRESSURE, int(self.MAX * tab.pressure)),
            InputEvent(e.EV_ABS.ABS_TILT_X, tab.tilt[0]),
            InputEvent(e.EV_ABS.ABS_TILT_Y, tab.tilt[1]),
            InputEvent(e.EV_SYN.SYN_REPORT, 0),
        ))
        self.ui.send_events(eq)

if __name__ == '__main__':
    t = Tablet()
    m = InputModel()
    print(f'Device at {m.ui.devnode}, {m.ui.syspath}')
    for tab in t.process():
        print(tab)
        m.update(tab)
