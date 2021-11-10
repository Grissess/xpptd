# What is it?

This is software for interacting with my XP-PEN tablets, particularly an Artist
12 (Gen 2)--but you might find use of it with their other products, if needed.
(Be prepared to change the USB IDs, of course--or open an issue to tell me.)

# Why?

The native driver doesn't appear to have source available (it ships with an
empty "LGPL" file presumably because of Qt), and it doesn't work in Wayland. In
addition, the way the tablet presents itself by default seems to prevent
libinput from determining it's actually a tablet (it thinks it's a touchscreen,
and that tool is your finger, or somesuch), which causes it to kill
"unreliable" pressure data (since most touchpads base pressure on contact area,
which is notoriously flaky).

Despite all this, though, I *will* say it's good hardware at an excellent
value, and I am happy to see that the manufacturer made an (abortive) attempt
to support the Linux ecosystem--arguably, by making a device that's too simple
to be unsupported.

# Dependencies

Since I'm still bad at packaging Python, I'll just tell you you need:

- [PyUSB][pyusb], for the `usb` module; and
- [(python-)evdev][evdev], for the `evdev` module.

You'll also need to make sure your kernel supports `uinput`, the "User level
driver support" `CONFIG_INPUT_UINPUT`. Most prebuilt kernels for typical linux
distros have this, but you might need to, e.g., take care of this on Gentoo,
LFS, Exherbo, or the like. In addition, you might need to (`sudo`) `modprobe
uinput` if it was built as a kernel module--this script intentionally doesn't
run with rights to load it automatically. (Speaking of not running with rights,
check that you have permissions to the `/dev/uinput` node as well; it has come
to my attention that some distributions restrict this, as it confers an ability
to believably simulate any user input--persons concerned about this should give
pause to that consideration, and consider one of the LSMs.)

# What's the Main Program?

Oh, sorry. It's `read_usb.py`. The `uinput_xlate.py` was an early attempt at
doing evdev-to-evdev translation, but the default USB HID Interface doesn't
provide crucial data, like pressure, tilt, or position while hovering.

Run it *after* plugging in the device. That should be all you need to do.

# Troubleshooting

If you're one of the poor souls who, like me, has a tablet but isn't getting it
working, try running `libinput debug-events` in your shell (perhaps as root?
You may need access to the evdev nodes). A properly-configured tablet should be
generating `TABLET_TOOL_*` events. If that's not the case, try this.

Bear in mind that I'm no USB expert, and don't claim to be. The USB protocol
done here was determined experimentally, and there's a solid chance I don't do
enough due diligence in protocol setup. As usual, feel free to report issues or
submit PRs.

# What About Input Mappings?

I chose a mapping according to the [kernel's input guidelines][kig], which you
can probably find in a newer documentation tree. Adherence to this protocol
seems necessary to convince libinput to treat the device as a drawing tablet
proper.

If you're referring to axis mapping, check your compositor's documentation. In
particular, under X, look at

	xinput map-to-output <devname> <outname>

... where `<devname>` can be read from `xinput` alone, and `<outname>` from
`xrandr`.

The situation is muddier with Wayland, since each compositor is their own
domain. On my Sway system, for example, I can execute

	input <identifier> map_to_output <output>

via `swaymsg` or my config file, where `<identifier>` is shown in `swaymsg -t
get_inputs` and `<output>` in `swaymsg -t get_outputs`.

For trickier cases, like calibration or otherwise using only parts of the
screen, the tools above have more advanced settings. Check their respective
documentation.

## But I want the pad buttons to simulate keypresses!

I usually don't! Software worth its salt should be able to bind *any* event,
including those odd extranumary buttons on your mouse, to a function you
desire. If it costs a one-time setup to get the usual tools to be on the
buttons you like, so be it.

Plus, there's no consensus as to *which* tools should be on which buttons,
anyway. Tablets seem to come preconfigured with an interesting, eclectic array
probably suitable for PhotoShop (and possibly Krita by extension). I refuse to
force the skeumorphisms of one design onto users who may prefer another.

Nonetheless, there is no *technical* reason it couldn't be done; the script
simply uses `BTN_n` for `n` in 0-7 out of convenience, but these can just as
readily be any of the `KEY_` events (though simulating keyboard *chords* is
left as an exercise to the reader). I may be inclined to accept a PR that
allows for more straightforward configuration of what events are actually sent
(than hacking on the source)--*but only if the defaults here are preserved*.

# ... But Actually

I'm working on getting these merged into [DIGIMend's kernel drivers][dmkd]; see [issue 578][dmkd578].

In the meantime, @kurikaesu has made a [userspace tablet driver daemon][utdd]
based on this work, and with essentially the same APIs, but in C++ (and broader
device support). As of this writing support for *this* tablet is experimental
and has some bugs, but you should check that out for yourself. (These drivers
are scheduled for merging into the kernel drivers above; see [pull
557][dmkd557].)

In any case, if you find this device isn't supported in software you'd like it
to be, feel free to tell me (or take the constants herefrom and merge it on my
behalf :) .

# Licensing

Ah, administrivia... This code uses the `GPL-3` (see `COPYING`)--not because
I'm vindictive, but because I'd rather have the onus of maintenance be on the
community rather than some poor software engineer who doesn't generally know or
care about Linux. (Of course, that's not to say there might not be someone
passionate about that there--but still, why make them do all the work?)

[dmkd]: https://github.com/DIGImend/digimend-kernel-drivers
[dmkd578]: https://github.com/DIGImend/digimend-kernel-drivers/issues/578
[dmkd557]: https://github.com/DIGImend/digimend-kernel-drivers/pull/557
[utdd]: https://github.com/kurikaesu/userspace-tablet-driver-daemon
[kig]: https://www.kernel.org/doc/html/v4.18/input/event-codes.html
[pyusb]: https://pyusb.github.io/pyusb/
[evdev]: https://pypi.org/project/evdev/
