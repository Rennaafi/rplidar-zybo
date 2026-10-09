# Build it with the Vivado and Vitis GUI

Same result as the command-line flow in the README, done with the mouse.
Written for **Vivado / Vitis 2025.1** and a **Digilent Zybo Z7-10**. Other
versions move the menus around; the settings are still the same.

> **Status:** the settings below are taken straight from `hw/build_hw.tcl`,
> `sw/build_sw.py` and `sw/run_on_board.tcl`, which are tested on hardware.
> The exact menu wording was not yet checked click by click in a fresh install.
> If a menu differs, trust the *values*, and please open an issue.
> `<!-- SCREENSHOT -->` marks the spots where a picture should go.

**Before you start**
- Vivado + Vitis 2025.1 installed, with Zynq-7000 device support.
- Digilent board files installed (Vivado: *Tools → Settings → Board Repository*,
  or *Tools → Vivado Store → Boards*). You need `zybo-z7-10`.
- Zybo connected by the **PROG/UART** micro-USB port, jumper **JP5 on JTAG**.
- **Work in a folder path with no spaces** (`D:\lidar_build`, not
  `D:\to github\...`). Vitis platform creation fails on spaces.
- Copy this repo there first.

**Shortcuts**
- *Just want it running?* Skip Part 1 and use `hw/lidar_zybo.xsa` and
  `hw/lidar_zybo.bit` from the repo. Go to Part 2.
- *Want Part 1 but fast?* See [Option A](#option-a--one-click-script) and skip the
  manual clicking.

---

## Part 1 — Hardware in Vivado

### Option A — one-click script

1. Open Vivado → **Tools → Run Tcl Script…** → pick `hw/build_hw.tcl` → OK.
2. Wait (a few minutes). It creates the project, the block design, runs
   synthesis and implementation, and writes `hw/lidar_zybo.xsa` and
   `hw/lidar_zybo.bit`.
3. Open `hw/vivado_proj/lidar_zybo.xpr` afterwards to look around.

If it errors with *"Zybo Z7-10 board files not found"*, install the board files
(see above). Then continue with Part 2.

### Option B — build it yourself (to learn what each block does)

**1. Project**
1. *Create Project* → name `lidar_zybo` → RTL Project, do not specify sources yet.
2. Choose the **Boards** tab → **Zybo Z7-10** (part `xc7z010clg400-1`).
3. *Add Sources → Add or create design sources* → `hw/motor_pwm.v`.
4. *Add Sources → Add or create constraints* → `hw/lidar_zybo.xdc`.
   <!-- SCREENSHOT: Sources window with motor_pwm.v and the XDC -->

**2. Block design**
1. *Create Block Design* → name `system`.
2. **Add IP → ZYNQ7 Processing System.** Click *Run Block Automation*, tick
   **Apply Board Preset**, OK. (This connects DDR and FIXED_IO.)
3. Double-click the Zynq block → *Clock Configuration* → *PL Fabric Clocks*:
   **FCLK_CLK0 = 100 MHz**. *PS-PL Configuration* → **M_AXI_GP0 interface enabled**.
4. **Add IP → AXI Uartlite.** Double-click: **Baud 115200, 8 data bits, no parity.**
5. **Add IP → AXI GPIO.** Double-click:
   - **Enable Dual Channel**
   - Channel 1: **All Outputs**, width **8**
   - Channel 2: **All Outputs**, width **4**
6. **Right-click the canvas → Add Module → `motor_pwm`.** Double-click it
   and check `CLK_HZ = 100000000`, `PWM_HZ = 24000`.
   <!-- SCREENSHOT: block design before connecting -->
7. Click **Run Connection Automation** → tick *All Automation*. This adds the
   AXI interconnect and the processor-system-reset block and wires
   `axi_uartlite_0` and `axi_gpio_0` to `M_AXI_GP0`.

**3. Ports and wires**
1. Right-click the UART pin of `axi_uartlite_0` → **Make External**, rename
   the port to **`lidar_uart`**. (The XDC expects `lidar_uart_rxd` and
   `lidar_uart_txd`, which Vivado derives from this name.)
2. Right-click `motor_pwm_0/pwm` → **Create Port**: name **`motoctl`**,
   direction Output.
3. Right-click `axi_gpio_0/gpio2_io_o` → **Create Port**: name **`leds`**,
   output, width **[3:0]**.
4. Draw these wires:
   | From | To |
   |---|---|
   | `FCLK_CLK0` | `motor_pwm_0/clk` |
   | `proc_sys_reset_0/peripheral_aresetn` | `motor_pwm_0/rst_n` |
   | `axi_gpio_0/gpio_io_o` | `motor_pwm_0/duty` |
   | `motor_pwm_0/pwm` | port `motoctl` |
   | `axi_gpio_0/gpio2_io_o` | port `leds` |
   <!-- SCREENSHOT: finished block design -->

**4. Addresses** — *Address Editor* tab
- `axi_uartlite_0` → **0x42C00000**, 64K
- `axi_gpio_0` → **0x41200000**, 64K

(`main.c` falls back to these fixed values, so keep them.)

**5. Check, wrap, build**
1. **Validate Design** (F6) → should say successful.
2. In *Sources*: right-click `system` → **Create HDL Wrapper** → *Let Vivado
   manage*. Right-click the wrapper → **Set as Top**.
3. *Flow Navigator* → **Generate Bitstream**. Wait for it to finish.
4. *Window → Timing → Report Timing Summary*: worst setup slack should be
   positive (about +2.4 ns for the reference build).
5. **File → Export → Export Hardware** → choose **Include bitstream** →
   save as `lidar_zybo.xsa`.
   <!-- SCREENSHOT: Export Hardware dialog with Include bitstream ticked -->
6. Copy the bitstream
   `lidar_zybo.runs/impl_1/system_wrapper.bit` next to it as `lidar_zybo.bit`.

---

## Part 2 — Software in Vitis

1. Start **Vitis 2025.1** and pick a workspace folder (no spaces).
2. **File → New Component → Platform.**
   - Name `lidar_platform`
   - Hardware design: your `lidar_zybo.xsa`
   - Operating system **standalone**, processor **ps7_cortexa9_0**
   - Leave *Generate DTB* off.
   <!-- SCREENSHOT: platform creation page -->
3. Select the platform → **Build**. Wait for *Build finished*.
4. **File → New Component → Application.**
   - Name `lidar_app`
   - Platform: `lidar_platform`, domain `standalone_ps7_cortexa9_0`
5. Copy `main.c`, `lidar_parse.c` and `lidar_parse.h` from `sw/src/` into the
   new app's `src` folder (drag them in the Explorer, replace the template file).
6. Select `lidar_app` → **Build**. You get `build/lidar_app.elf`.
   <!-- SCREENSHOT: Build finished with 0 errors -->

> If the platform build ends with a missing `scugic` / BSP error, open a
> terminal in `…\standalone_ps7_cortexa9_0\bsp\libsrc\build_configs\gen_bsp` and
> run `cmake .` then `ninja`, then rebuild the application.

---

## Part 3 — Wire it up

Do this with the Zybo **unpowered**.

| Lidar | Zybo |
|---|---|
| TX | Pmod **JE1** |
| RX | Pmod **JE2** |
| MOTOCTL | Pmod **JE3** |
| GND | Pmod **JE5** and the 5 V supply GND |
| VS5.0, VMOTO | external **5 V** (the Pmod is 3.3 V only) |

Leave any USB-TTL adapter's TXD off the lidar TX wire: two outputs on one wire
means nothing arrives.

---

## Part 4 — Run

1. Open a serial terminal on the Zybo's COM port at **115200 8N1**
   (PuTTY, Tera Term, or Vitis' own *Serial Terminal*). Do this first.
2. Program the board. The most reliable way is the same script the
   project uses; from a Vitis command prompt (**cmd**, not PowerShell):
   ```bat
   cd /d <your folder>\sw
   xsdb run_on_board.tcl
   ```
   It resets the system, loads the bitstream, runs `ps7_init`, downloads the
   ELF and starts it.
3. In the Vitis GUI instead: **Flow → Program Device** (the `.bit`), then
   **Run** `lidar_app`. If the console stays empty, use the script above
   (the IDE's Run did not always run `ps7_init`).
4. You should see the lidar handshake, then lines with the revolution rate and
   points per revolution (about 6–7 Hz, 280 points). LD0 blinks once per
   revolution and LD1 lights while scanning.
5. Keys in the terminal: `+` / `-` motor duty, `m` motor on/off, `r` restart.
6. For the live polar plot: `pip install -r pc/requirements.txt`, close the
   terminal, then `python pc\lidar_view.py --zybo COMx`.

## If nothing happens

| Symptom | Likely cause |
|---|---|
| Console completely silent | JP5 not on JTAG, wrong COM port, or `ps7_init` skipped |
| Hangs after "Motor on, waiting" | Zynq timer not started: `usleep(1000)` must be the first call in `main()` |
| Handshake times out | TX/RX swapped, no common GND, lidar not at 5 V |
| Platform creation fails | Space in the path |
| *Board files not found* | Install the Digilent board files |
