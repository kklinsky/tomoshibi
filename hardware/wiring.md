# Wiring

**Hardware revision:** `hw-rev-A` (draft)

How the display, button and button light connect to the Raspberry Pi 5. Parts are listed in
[BOM.md](BOM.md). Shut the Pi down and unplug it before changing any wiring.

## Pin map

| Pi 5 pin | Pi 5 signal | Goes to |
|---|---|---|
| 1 | 3.3V | Display pin 2 (VDD) |
| 2 | 5V | Button LED + |
| 6 | GND | Display pin 1 (VSS) |
| 9 | GND | Display pin 40 (VSS) |
| 12 | GPIO18 | Display pin 29 (BL_ON/OFF), once the backlight is checked (below) |
| 13 | GPIO27 | Display pin 21 (/RESET_NC) |
| 14 | GND | Button switch, LED driver |
| 15 | GPIO22 | Button switch |
| 16 | GPIO23 | LED driver input |
| 17 | 3.3V | Display pin 29 (BL_ON/OFF), until the backlight is checked |
| 19 | GPIO10 (SPI0 MOSI) | Display pin 27 (LCD_SDI) |
| 22 | GPIO25 | Display pin 25 (/WR(D/C)) |
| 23 | GPIO11 (SPI0 SCLK) | Display pin 24 (D/C(SCL)) |
| 24 | GPIO8 (SPI0 CE0) | Display pin 23 (LCD_/CS) |

## Display

ER-TFT032IPS-3.2-4334, ordered as `ER-TFT032IPS-3.2-4334-3662-4SPI-3.3V`: a 3.2" 240×320 IPS
panel with an ST7789 controller on a breakout board, set up for 4-wire SPI at 3.3 V. It's
mounted in portrait.

| Display pin | Datasheet name | In 4-wire SPI | Pi 5 pin |
|---|---|---|---|
| 1, 40 | VSS | Ground | 6, 9 |
| 2 | VDD | 3.3 V power | 1 |
| 21 | /RESET_NC | Reset, active low | 13 |
| 23 | LCD_/CS | Chip select, active low | 24 |
| 24 | D/C(SCL) | **SPI clock** | 23 |
| 25 | /WR(D/C) | **Data/command select** | 22 |
| 27 | LCD_SDI | SPI data in | 19 |
| 29 | BL_ON/OFF | Backlight: high = on, low = off | 17 for now, then 12 |

**Pins 24 and 25 are easy to swap.** Their names come from the parallel interface, and in SPI
pin 24 is the clock and pin 25 is data/command. Leave every other display pin unconnected,
including 32–39 (touch, microSD, flash and font chips).

The header (JP1) is two rows of 2.54 mm pins on the back of the board, numbered in pairs: 1–2,
3–4, up to 39–40. Hold the board with the header at the top and the back facing you. Pin 1 is
at the top right, pin 2 just below it, and the numbers rise toward the left. Odd pins are in
the row nearer the board's edge. Female-to-female jumpers fit it directly. To check you have the right end, unplug
everything and use a multimeter on continuity: pins 1 and 40 should connect (both are ground),
and pins 1 and 2 should not.

### Check before powering on

The datasheet says boards ship as 8080 16-bit parallel at 3.3 V by default, so confirm an
SPI board really is set for SPI:

| Item | 4-wire SPI at 3.3 V |
|---|---|
| JP | Shorted (open means 5 V supply) |
| J2, J3, J4 | Shorted |
| J1, J5, J6 | Open |
| R3–R10, R19, R21–R28 | Fitted, 0 Ω |
| R17, R18, R20 | Not fitted |

**Leave J5 open.** A note under the datasheet's electrical table says "Short J5 if VDD=3.3V",
which contradicts its interface table. A board ordered as 4SPI at 3.3 V came from the factory
with J5 open and JP shorted, so the note most likely means JP.

The PCB is marked ER-TFTM032-3 Ver 2.2, the breakout shared with EastRising's non-IPS 3.2"
display. The flex cable behind it is marked ER-TFT032IPS-3.2. J7, J9, J10 and J11 may also be
shorted; they only affect touch pins, which aren't used.

Logic is 3.3 V, with a 3.6 V maximum. Never connect a 5 V signal to the display. That includes
pin 2: with JP shorted the board expects 3.3 V there, not 5 V.

### Backlight

**Unconfirmed: BL current.** The datasheet calls pin 29 a control input but gives no current
for it. Whole-module current is 95 mA typical and 110 mA maximum at 3.3 V. The board has its
own backlight driver parts (Q1, U5, R30–R32), so the pin probably draws little, but that hasn't
been traced or measured.

Start with pin 29 on 3.3 V (Pi pin 17), which is how the vendor's sample code wires it. To
dim or turn off the backlight, it has to move to GPIO18 (Pi pin 12):

1. Measure the current from 3.3 V into pin 29 with a multimeter.
2. If it's a few mA or less, connect pin 29 straight to Pi pin 12.
3. If it's more, drive it through a transistor instead of the GPIO pin.

### First test

Wire ground and power first, then RES, CS, SCK, DC and SDI, and BL last. Recheck pins 1, 2 and
40 before powering up. The backlight should come on, but the panel shows no picture until
software drives it. If the backlight stays off, unplug it and check the wiring.

The sample code uses SPI mode 0 and the panel's native 240×320 portrait layout (`0x36` =
`0x00`) with 16-bit color (`0x3A` = `0x05`). Start at a moderate SPI speed, because long jumper
wires can garble the data.

## Button

The switch connects GPIO22 (Pi pin 15) to GND (Pi pin 14). The software uses the Pi's internal
pull-up, so no resistor is needed. A press reads low.

## Button light

The LED needs 5 V, and a GPIO pin only gives 3.3 V, so a transistor switches it. The 200 Ω
resistor is built into the button. Identify the LED's + and − terminals on the actual button
first. Build one of these:

**NPN transistor (2N2222 / PN2222)**

| From | To |
|---|---|
| Pi pin 2 (5V) | LED + |
| LED − | Collector |
| Emitter | GND (Pi pin 14) |
| GPIO23 (Pi pin 16) | 1 kΩ resistor, then base |

**N-channel MOSFET (2N7000)**

| From | To |
|---|---|
| Pi pin 2 (5V) | LED + |
| LED − | Drain |
| Source | GND (Pi pin 14) |
| GPIO23 (Pi pin 16) | 220 Ω resistor, then gate |
| Gate | 10 kΩ resistor, then GND |

## RTC battery

Plug the rechargeable battery into the Pi 5's RTC connector and enable charging in
`/boot/firmware/config.txt`:

```ini
dtparam=rtc_bbat_vchg=3000000
```
