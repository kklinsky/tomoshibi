# Bill of Materials

**Hardware revision:** `hw-rev-A` (draft)
**Enclosure:** [tomoshibi-enclosure](https://github.com/kklinsky/tomoshibi-enclosure), no release yet

This is the parts list for one Tomoshibi device. The enclosure is designed around the
**core parts** below. Substituting any of them may mean changing the enclosure, and
changing the core parts creates a new hardware revision.

Wiring is documented in [wiring.md](wiring.md).

## Required

### Core parts (the enclosure is designed around these)
| Part | Qty | Notes |
|---|---|---|
| Raspberry Pi 5 | 1 | **8 GB recommended** if you want the local fallback LLM; 4 GB is enough for local speech only |
| Jabra Speak 410 (USB) | 1 | Speakerphone with echo cancellation. Sits on top of the enclosure. Its USB cable is fixed and fairly long; plan strain relief and where the extra length coils inside |
| 30 mm arcade button with LED: [Adafruit #3491](https://www.adafruit.com/product/3491) (translucent clear), or the yellow LED version from the same family | 1 | 30 mm mounting hole, screw-in nut for panels up to ~20 mm thick. Micro-switch with a soft action (no strong click). **LED: 5 V, ~10 mA, 200 Ω resistor built in.** It's only ~2 mA (dim) at 3.3 V, so it's switched from 5 V through a transistor. 0.11" (2.8 mm) quick-connect terminals. Yellow is easier to see when unlit and suits the "lamplight" theme |
| 2.0" 320×240 IPS TFT, ST7789, with EYESPI breakout (Adafruit) | 1 | SPI display for the animated face. The microSD slot on the breakout isn't used |

### Power, cooling and timekeeping
| Part | Qty | Notes |
|---|---|---|
| Official Raspberry Pi 27 W USB-C power supply | 1 | 5 V / 5 A. **Don't substitute a phone charger.** On a weaker supply the Pi 5 limits total USB current to 600 mA, which can starve the Jabra and cause dropouts or reboots |
| Official Raspberry Pi 5 Active Cooler | 1 | Speech recognition loads the CPU heavily; without a cooler the Pi throttles |
| Raspberry Pi RTC battery (rechargeable, for the Pi 5 RTC connector) | 1 | Keeps the clock right through power cuts so reminders fire on time. **Must be the rechargeable type;** enable charging in `config.txt` (see [wiring.md](wiring.md)) |

### Storage (pick one)
| Part | Qty | Notes |
|---|---|---|
| **Option A:** high-endurance microSD, 64 GB (e.g. SanDisk High Endurance, Samsung PRO Endurance) | 1 | Simplest. Use an endurance-rated card: ordinary cards are the most common failure on an always-on Pi |
| **Option B (recommended):** Raspberry Pi M.2 HAT+ with a 256 GB NVMe SSD | 1 | More reliable and faster at loading speech models; room for a local LLM. Takes more space inside the enclosure |

### Electronics for the button LED and screen
| Part | Qty | Notes |
|---|---|---|
| NPN transistor (e.g. 2N2222 / PN2222) **or** logic-level N-channel MOSFET (e.g. 2N7000) | 1 | Low-side switch so a GPIO pin can turn on the button's 5 V LED (~10 mA, so any small-signal part works) |
| Resistors: 1 kΩ base resistor (NPN) **or** 220 Ω gate + 10 kΩ pull-down (MOSFET) | 1 each | No LED current-limiting resistor needed; it's built into the button. See [wiring.md](wiring.md) |
| Small protoboard or Raspberry Pi proto HAT | 1 | Holds the LED driver circuit and connectors |
| Adafruit EYESPI Pi Beret | 1 | Connects the display to the Pi with a flat cable instead of loose jumpers. Alternative: jumper wires to the breakout's header pins |
| EYESPI flat (FPC) cable, length to suit the enclosure | 1 | Only needed with the Pi Beret |

### Connectors and wiring
| Part | Qty | Notes |
|---|---|---|
| 0.11" (2.8 mm) quick-connect wire pairs (Adafruit sells pre-crimped pairs) | 2 pairs | One pair for the switch, one for the LED. Or crimp your own 2.8 mm female spade terminals |
| JST-XH or Dupont connector kit | 1 kit | So every part can be unplugged for service without desoldering |
| Hook-up wire (22–26 AWG) | — | |
| Heat-shrink tubing | — | |

### Enclosure hardware
| Part | Qty | Notes |
|---|---|---|
| Printed enclosure parts | 1 set | See [tomoshibi-enclosure](https://github.com/kklinsky/tomoshibi-enclosure) |
| M2.5 brass heat-set inserts | 4–8 | Pi mounting |
| M3 brass heat-set inserts | 6–10 | Panels and base |
| M2.5 standoffs and screws | 4 | Pi mounting |
| M3 screws | 6–10 | Panels and base |
| Rubber feet | 4 | Stops it sliding when the button is pressed |
| Base weight: steel washers or steel shot | ~300–500 g | Keeps it from tipping. Adjust to the final design |
| Panel-mount USB-C extension, **rated for 5 A** | 1 | So power plugs into the enclosure rather than directly into the Pi. Many panel-mount cables are not rated for 5 A and cause undervoltage warnings. Verify, or route the official PSU cable through a strain-relief grommet instead |

## Recommended
| Part | Qty | Why |
|---|---|---|
| **Second development unit** (Pi 5 + spare button + screen; a Jabra is optional) | 1 | Test changes on your bench, never on the device someone depends on. Matches the `beta` update channel |
| Spare storage, pre-imaged | 1 | A failed device can be fixed by swapping the card/SSD, without needing technical help on site |
| Ethernet cable | 1 | More reliable than Wi-Fi if there's a jack near where the device sits. If not, check Wi-Fi signal at that spot |

## Optional
| Part | Qty | Why |
|---|---|---|
| Presence sensor: mmWave (e.g. HLK-LD2410) or PIR | 1 | Hold a reminder until someone is in the room instead of using up retries on an empty room; greet him when he walks by. Far less invasive than a camera |
| Ambient light sensor, I2C (e.g. VEML7700 or BH1750) | 1 | Auto-dim the screen at night, brighten it in a sunny room |
| UPS HAT for Pi 5 | 1 | Ride out brief power blips and shut down cleanly in longer outages |

## Tools
- Soldering iron and solder
- Crimping tool for JST/Dupont and spade terminals
- Multimeter (check the button LED voltage before wiring)
- Heat-set insert tip for the soldering iron
- 3D printer (see the enclosure repo for material and settings)

## Open items for hw-rev-A
- [x] Button: Adafruit #3491 family. LED is 5 V / ~10 mA with built-in resistor; 0.11" terminals
- [ ] Button color: clear vs yellow
- [ ] Identify the LED's + and − terminals on the actual button (check the markings, or test with 5 V)
- [ ] Decide storage: high-endurance microSD or NVMe
- [ ] Decide Pi 5 RAM: 4 GB or 8 GB
- [ ] Find a panel-mount USB-C extension that's genuinely rated for 5 A, or use a grommet
- [ ] Decide on the presence and light sensors before the enclosure design is finalized (they need openings)
- [ ] Final quantities for inserts and screws once the enclosure is designed
