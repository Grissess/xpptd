from evdev import UInput, AbsInfo, InputDevice, ecodes as e, categorize

tab = InputDevice('/dev/input/event20')

def map_axis(v, ai):
    return (float(v) - ai.min) / float(ai.max - ai.min)

class Model(object):
    MAX = 0xffff
    CAPS = {
            e.EV_ABS: [
                (e.ABS_X, AbsInfo(value=0, min=0, max=MAX, fuzz=0, flat=0, resolution=0)),
                (e.ABS_Y, AbsInfo(value=0, min=0, max=MAX, fuzz=0, flat=0, resolution=0)),
                (e.ABS_PRESSURE, AbsInfo(value=0, min=0, max=MAX, fuzz=0, flat=0, resolution=0)),
            ],
            e.EV_KEY: [e.BTN_LEFT],
    }

    @classmethod
    def from_tablet(cls, tab):
        axes = tab.capabilities()[e.EV_ABS]
        aix, aiy, aip = None, None, None
        for axis, absin in axes:
            if axis == e.ABS_X:
                aix = absin
            elif axis == e.ABS_Y:
                aiy = absin
            elif axis == e.ABS_PRESSURE:
                aip = absin
        assert aix and aiy and aip
        return cls(aix, aiy, aip)

    def __init__(self, aix, aiy, aip):
        self.aix, self.aiy, self.aip = aix, aiy, aip
        self.down = False
        self.x = 0.0
        self.y = 0.0
        self.p = 0.0
        self.out = UInput(self.CAPS, name = 'python-htd')

    def emit(self):
        self.out.write(e.EV_ABS, e.ABS_X, int(self.MAX * self.x))
        self.out.write(e.EV_ABS, e.ABS_Y, int(self.MAX * self.y))
        self.out.write(e.EV_ABS, e.ABS_PRESSURE, int(self.MAX * self.p))
        self.out.write(e.EV_KEY, e.BTN_LEFT, 1 if self.down else 0)
        self.out.syn()

    def take(self, ev):
        if ev.type == e.EV_KEY and ev.code == e.BTN_TOUCH:
            self.down = True if ev.value else False
        elif ev.type == e.EV_ABS:
            if ev.code == e.ABS_X:
                self.x = map_axis(ev.value, self.aix)
            elif ev.code == e.ABS_Y:
                self.y = map_axis(ev.value, self.aiy)
            elif ev.code == e.ABS_PRESSURE:
                self.p = map_axis(ev.value, self.aip)
        elif ev.type == e.EV_SYN:
            self.emit()

mdl = Model.from_tablet(tab)

with tab.grab_context():
    for ev in tab.read_loop():
        print(categorize(ev))
        mdl.take(ev)
