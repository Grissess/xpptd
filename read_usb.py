import array
import usb
from evdev import UInput, AbsInfo, ecodes as e

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
        return f'<Tablet x,y,p,tx,ty = {self.pos[0]},{self.pos[1]},{self.pressure},{self.tilt[0]},{self.tilt[1]} ({self.raw_pos[0]:04x},{self.raw_pos[1]:04x},{self.raw_pressure:04x}) s = {self.stylus:x} b = {self.buttons:02x}>'

class InputModel(object):
    MAX = 0xffff

    @classmethod
    def make_caps(cls):
        # TODO: find the meaning of an arbitrary resolution, required by libinput
        ai = AbsInfo(value=0, min=0, max=cls.MAX, fuzz=0, flat=0, resolution=300)
        ait = AbsInfo(value=0, min=Tablet.T_MIN, max=Tablet.T_MAX, fuzz=0, flat=0, resolution=0)
        caps = {
                e.EV_ABS: [
                    (e.ABS_X, ai),
                    (e.ABS_Y, ai),
                    (e.ABS_PRESSURE, ai),
                    (e.ABS_TILT_X, ait),
                    (e.ABS_TILT_Y, ait),
                ],
                e.EV_KEY: [
                    e.BTN_TOUCH, e.BTN_STYLUS, e.BTN_STYLUS2,
                    e.BTN_0, e.BTN_1, e.BTN_2, e.BTN_3,
                    e.BTN_4, e.BTN_5, e.BTN_6, e.BTN_7,
                ],
        }
        return caps

    def __init__(self):
        self.ui = UInput(self.make_caps(), name = 'python-htd', input_props = [
            e.INPUT_PROP_POINTER, e.INPUT_PROP_DIRECT,
        ])
        # Mostly to avoid redundancy
        self.mbs = 0  # mouse button state
        self.bts = 0  # pad button state

    def update(self, tab):
        mbs = tab.stylus
        bts = tab.buttons

        if self.mbs != mbs:
            self.ui.write(e.EV_KEY, e.BTN_TOUCH, 1 if mbs & Tablet.B2_BT_TOUCH else 0)
            self.ui.write(e.EV_KEY, e.BTN_STYLUS, 1 if mbs & Tablet.B2_BT_LOWER else 0)
            self.ui.write(e.EV_KEY, e.BTN_STYLUS2, 1 if mbs & Tablet.B2_BT_UPPER else 0)
            self.mbs = mbs

        if self.bts != bts:
            for i in range(8):
                pot = 2**i
                self.ui.write(e.EV_KEY, getattr(e, f'BTN_{i}'), 1 if pot & bts else 0)
            self.bts = bts

        self.ui.write(e.EV_ABS, e.ABS_X, int(self.MAX * tab.pos[0]))
        self.ui.write(e.EV_ABS, e.ABS_Y, int(self.MAX * tab.pos[1]))
        self.ui.write(e.EV_ABS, e.ABS_PRESSURE, int(self.MAX * tab.pressure))
        self.ui.write(e.EV_ABS, e.ABS_TILT_X, tab.tilt[0])
        self.ui.write(e.EV_ABS, e.ABS_TILT_Y, tab.tilt[1])
        self.ui.syn()

if __name__ == '__main__':
    t = Tablet()
    m = InputModel()
    for tab in t.process():
        print(tab)
        m.update(tab)
