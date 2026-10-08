// RPLIDAR A1 on Zybo Z7-10, bare-metal (Stage 2B).
//
//   lidar  --UART 115200-->  AXI UART Lite (PL, Pmod JE1/JE2)  --> this app
//   this app --> AXI GPIO ch1 duty --> motor_pwm (PL) --> MOTOCTL (Pmod JE3)
//   this app --> AXI GPIO ch2      --> LD0..LD3
//   this app --> PS UART1 (USB console, 115200) --> PuTTY / pc/lidar_view.py
//
// Why no xil_printf in the main loop: the UART Lite RX FIFO is only 16 bytes
// (about 1.4 ms of lidar data). xil_printf blocks until every character is
// out, so a long print overflows the FIFO. Here every console write goes into
// a RAM ring buffer that is drained a few bytes at a time between lidar
// polls, so nothing ever blocks. Overruns are still counted ("ovr") so you
// can prove it on the console.
//
// Console keys:  + / -  motor duty +-10    m  motor on/off
//                f      toggle frame output for pc/lidar_view.py (F on, x off)
//                r      restart scan       h  help
#include "xparameters.h"
#include "xil_io.h"
#include "xil_types.h"
#include "xuartlite_l.h"
#include "xgpio_l.h"
#include "xuartps_hw.h"
#include "sleep.h"
#include "lidar_parse.h"

// Stage 1 "fake" build: 1 = take the scan bytes from the console UART (sent
// by pc/lidar_view.py --bridge) instead of the lidar UART. No handshake, no
// motor, no keys; frames are always on. Set back to 0 for the real lidar.
#define FAKE_SRC 0

#ifdef SDT
#include "xiltimer.h"      // 2023.2+ System Device Tree flow
#else
#include "xtime_l.h"       // classic flow
#endif

// ---------------------------------------------------------------- addresses
// Names differ between the SDT flow and the classic flow; the final fallback
// is the fixed address build_hw.tcl assigns.
#if defined(XPAR_AXI_UARTLITE_0_BASEADDR)
#define LIDAR_UART_BASE XPAR_AXI_UARTLITE_0_BASEADDR
#elif defined(XPAR_XUARTLITE_0_BASEADDR)
#define LIDAR_UART_BASE XPAR_XUARTLITE_0_BASEADDR
#elif defined(XPAR_UARTLITE_0_BASEADDR)
#define LIDAR_UART_BASE XPAR_UARTLITE_0_BASEADDR
#else
#define LIDAR_UART_BASE 0x42C00000
#endif

#if defined(XPAR_AXI_GPIO_0_BASEADDR)
#define GPIO_BASE XPAR_AXI_GPIO_0_BASEADDR
#elif defined(XPAR_XGPIO_0_BASEADDR)
#define GPIO_BASE XPAR_XGPIO_0_BASEADDR
#else
#define GPIO_BASE 0x41200000
#endif

#if defined(STDOUT_BASEADDRESS)
#define CONSOLE_BASE STDOUT_BASEADDRESS
#else
#define CONSOLE_BASE 0xE0001000   // PS UART1 = Zybo USB-UART
#endif

#ifndef COUNTS_PER_SECOND
#if defined(XPAR_CPU_CORE_CLOCK_FREQ_HZ)
#define COUNTS_PER_SECOND (XPAR_CPU_CORE_CLOCK_FREQ_HZ / 2)
#else
#define COUNTS_PER_SECOND (XPAR_CPU_CORTEXA9_0_CPU_CLK_FREQ_HZ / 2)
#endif
#endif

#define DUTY_DEFAULT        120     // ~47 %: 6.35 Hz, 312 pts/rev (sweep in README)
#define DUTY_STEP           10
#define NO_DATA_TIMEOUT_MS  1500    // restart the scan if the stream stops
#define FRONT_NEAR_MM       1000    // LD2
#define FRONT_DANGER_MM     300     // LD3

#define LED_HEARTBEAT 0x1
#define LED_SCANNING  0x2
#define LED_NEAR      0x4
#define LED_DANGER    0x8

// ---------------------------------------------------------------- time
static u64 now_ticks(void) {
    XTime t;
    XTime_GetTime(&t);
    return (u64)t;
}

static u32 ticks_to_ms(u64 dt) {
    return (u32)(dt / (COUNTS_PER_SECOND / 1000));
}

// ---------------------------------------------------------------- console (non-blocking)
#define CON_RING_SIZE 4096
static char con_ring[CON_RING_SIZE];
static u32  con_head, con_tail;   // head = write, tail = read
static u32  con_dropped;

static u32 con_free(void) {
    return CON_RING_SIZE - 1 - ((con_head - con_tail) & (CON_RING_SIZE - 1));
}

static void con_putc(char c) {
    if (con_free() == 0) {
        con_dropped++;
        return;
    }
    con_ring[con_head] = c;
    con_head = (con_head + 1) & (CON_RING_SIZE - 1);
}

static void con_puts(const char *s) {
    while (*s) {
        con_putc(*s++);
    }
}

// Right-aligned unsigned decimal, padded with spaces to 'width'
static void con_putu(u32 v, int width) {
    char buf[11];
    int n = 0;
    do {
        buf[n++] = '0' + (v % 10);
        v /= 10;
    } while (v && n < 10);
    for (int i = n; i < width; i++) {
        con_putc(' ');
    }
    while (n) {
        con_putc(buf[--n]);
    }
}

static void con_puthex(u32 v, int digits) {
    static const char hex[] = "0123456789ABCDEF";
    for (int i = digits - 1; i >= 0; i--) {
        con_putc(hex[(v >> (4 * i)) & 0xF]);
    }
}

// Move as many bytes as the PS UART TX FIFO accepts right now
static void con_pump(void) {
    while (con_tail != con_head && !XUartPs_IsTransmitFull(CONSOLE_BASE)) {
        XUartPs_WriteReg(CONSOLE_BASE, XUARTPS_FIFO_OFFSET, (u8)con_ring[con_tail]);
        con_tail = (con_tail + 1) & (CON_RING_SIZE - 1);
    }
}

static void con_flush(void) {
    while (con_tail != con_head) {
        con_pump();
    }
}

static int con_getc(void) {
    if (!XUartPs_IsReceiveData(CONSOLE_BASE)) {
        return -1;
    }
    return (int)(XUartPs_ReadReg(CONSOLE_BASE, XUARTPS_FIFO_OFFSET) & 0xFF);
}

// ---------------------------------------------------------------- GPIO
static u8 motor_duty;
static u8 led_state;

static void motor_set(u8 duty) {
    motor_duty = duty;
    Xil_Out32(GPIO_BASE + XGPIO_DATA_OFFSET, duty);
}

static void leds_set(u8 v) {
    led_state = v & 0xF;
    Xil_Out32(GPIO_BASE + XGPIO_DATA2_OFFSET, led_state);
}

// ---------------------------------------------------------------- lidar UART
static u32 lidar_overruns;
static u32 lidar_rx_count;     // raw bytes received, for wiring diagnosis
static u8  lidar_rx_first[8];  // first bytes seen since the count was reset

static void lidar_rx_reset(void) {
    XUartLite_WriteReg(LIDAR_UART_BASE, XUL_CONTROL_REG_OFFSET, XUL_CR_FIFO_RX_RESET);
}

// Returns a byte, or -1 if the FIFO is empty. Also counts overruns
// (reading the status register clears the error bits).
static int lidar_getc(void) {
#if FAKE_SRC
    return con_getc();
#endif
    u32 st = XUartLite_GetStatusReg(LIDAR_UART_BASE);
    if (st & XUL_SR_OVERRUN_ERROR) {
        lidar_overruns++;
    }
    if (!(st & XUL_SR_RX_FIFO_VALID_DATA)) {
        return -1;
    }
    int b = (int)(XUartLite_ReadReg(LIDAR_UART_BASE, XUL_RX_FIFO_OFFSET) & 0xFF);
    if (lidar_rx_count < sizeof lidar_rx_first) {
        lidar_rx_first[lidar_rx_count] = (u8)b;
    }
    lidar_rx_count++;
    return b;
}

static void lidar_cmd(u8 cmd) {
    XUartLite_SendByte(LIDAR_UART_BASE, 0xA5);
    XUartLite_SendByte(LIDAR_UART_BASE, cmd);
}

// Busy-wait that keeps the console moving
static void wait_ms(u32 ms) {
    u64 t0 = now_ticks();
    while (ticks_to_ms(now_ticks() - t0) < ms) {
        con_pump();
    }
}

// Reads one byte, waiting until 'deadline' (an absolute now_ticks() value).
// A single deadline shared across a whole search bounds the TOTAL time even
// when a noisy/miswired RX line delivers garbage back-to-back forever: each
// byte arriving resets nothing, so the search can't be stalled indefinitely
// the way a fresh per-byte timeout could be.
static int lidar_getc_before(u64 deadline) {
    for (;;) {
        int b = lidar_getc();
        if (b >= 0) {
            return b;
        }
        con_pump();
        if (now_ticks() >= deadline) {
            return -1;
        }
    }
}

// Waits for A5 5A + 5 descriptor bytes. Returns 0 on success.
static int lidar_read_descriptor(u32 *len, u8 *type, u32 timeout_ms) {
    u64 deadline = now_ticks() + (u64)timeout_ms * (COUNTS_PER_SECOND / 1000);
    int b;
    for (;;) {
        b = lidar_getc_before(deadline);
        if (b < 0) return -1;
        if (b != 0xA5) continue;
        b = lidar_getc_before(deadline);
        if (b < 0) return -1;
        if (b == 0x5A) break;
    }
    u8 d[5];
    for (int i = 0; i < 5; i++) {
        b = lidar_getc_before(deadline);
        if (b < 0) return -1;
        d[i] = (u8)b;
    }
    *len  = d[0] | (d[1] << 8) | (d[2] << 16) | ((u32)(d[3] & 0x3F) << 24);
    *type = d[4];
    return 0;
}

static int lidar_read_payload(u8 *buf, u32 n) {
    u64 deadline = now_ticks() + (u64)100 * (COUNTS_PER_SECOND / 1000) * (n ? n : 1);
    for (u32 i = 0; i < n; i++) {
        int b = lidar_getc_before(deadline);
        if (b < 0) return -1;
        buf[i] = (u8)b;
    }
    return 0;
}

static void lidar_stop(void) {
    lidar_cmd(LIDAR_CMD_STOP);
    wait_ms(10);
    lidar_rx_reset();
}

static int lidar_print_info(void) {
    u32 len; u8 type; u8 info[20];
    lidar_stop();
    lidar_cmd(LIDAR_CMD_GET_INFO);
    if (lidar_read_descriptor(&len, &type, 500) != 0 || len != 20 || lidar_read_payload(info, 20) != 0) {
        return -1;
    }
    con_puts("Model ");  con_putu(info[0], 0);
    con_puts("  FW ");   con_putu(info[2], 0); con_putc('.'); con_putu(info[1], 0);
    con_puts("  HW ");   con_putu(info[3], 0);
    con_puts("  SN ");
    for (int i = 4; i < 20; i++) con_puthex(info[i], 2);
    con_puts("\r\n");
    return 0;
}

// Returns 0 good, 1 warning, 2 error, -1 no answer
static int lidar_health(void) {
    u32 len; u8 type; u8 h[3];
    lidar_stop();
    lidar_cmd(LIDAR_CMD_GET_HEALTH);
    if (lidar_read_descriptor(&len, &type, 500) != 0 || len != 3 || lidar_read_payload(h, 3) != 0) {
        return -1;
    }
    static const char *names[] = { "Good", "Warning", "Error" };
    con_puts("Health: ");
    con_puts(h[0] <= 2 ? names[h[0]] : "?");
    con_puts("  error code 0x");
    con_puthex(h[1] | (h[2] << 8), 4);
    con_puts("\r\n");
    return h[0];
}

// Full bring-up: info, health (reset on error), SCAN. Retries forever.
static void lidar_start(void) {
#if FAKE_SRC
    con_puts("FAKE source: scan bytes come from the console UART\r\n");
    leds_set(LED_SCANNING);
    return;
#endif
    for (int attempt = 1;; attempt++) {
        leds_set(0);
        lidar_rx_count = 0;
        int health = -1;
        if (lidar_print_info() == 0) {
            health = lidar_health();
        }
        if (health < 0) {
            con_puts("No answer from lidar (attempt ");
            con_putu(attempt, 0);
            con_puts("). Check: lidar TX->JE1, RX->JE2, GND->JE5, 5 V on VS5.0\r\n");
            con_puts("   bytes received from lidar: ");
            con_putu(lidar_rx_count, 0);
            for (u32 i = 0; i < lidar_rx_count && i < sizeof lidar_rx_first; i++) {
                con_putc(' ');
                con_puthex(lidar_rx_first[i], 2);
            }
            con_puts(lidar_rx_count ? "\r\n" : "  (nothing arrives on JE1)\r\n");
            wait_ms(1000);
            continue;
        }
        if (health == 2) {
            con_puts("Health error, sending RESET\r\n");
            lidar_cmd(LIDAR_CMD_RESET);
            wait_ms(1000);
            lidar_rx_reset();
            continue;
        }

        u32 len; u8 type;
        lidar_cmd(LIDAR_CMD_SCAN);
        if (lidar_read_descriptor(&len, &type, 1000) != 0) {
            con_puts("No SCAN descriptor, retrying\r\n");
            continue;
        }
        con_puts("Scan descriptor len=");
        con_putu(len, 0);
        con_puts(" type=0x");
        con_puthex(type, 2);
        con_puts(len == 5 && type == 0x81 ? "  (ok)\r\n" : "  (UNEXPECTED)\r\n");
        leds_set(LED_SCANNING);
        return;
    }
}

// ---------------------------------------------------------------- output
static int frames_on;
static u32 frames_skipped;
static u32 rev_count;

static void print_help(void) {
    con_puts("Keys: +/- duty  m motor on/off  f frames toggle (F on, x off)  r restart scan  h help\r\n");
}

static void print_summary(const lidar_scan_t *s, u32 hz_x100, const lidar_parser_t *p) {
    con_puts("rev ");     con_putu(rev_count, 5);
    con_puts("  ");       con_putu(hz_x100 / 100, 2); con_putc('.');
    con_putc('0' + (hz_x100 / 10) % 10); con_putc('0' + hz_x100 % 10);
    con_puts(" Hz  pts "); con_putu(s->points, 4);
    con_puts(" valid ");   con_putu(s->valid, 4);
    con_puts("  near ");   con_putu(s->nearest_mm, 5);
    con_puts(" mm @ ");    con_putu(s->nearest_deg, 3);
    con_puts(" deg  front "); con_putu(s->front_mm, 5);
    con_puts(" mm  duty "); con_putu(motor_duty, 3);
    con_puts("  ovr ");    con_putu(lidar_overruns, 0);
    con_puts(" sync ");    con_putu(p->resync_drops, 0);
    con_puts("\r\n");
}

// One line per revolution for pc/lidar_view.py:
//   F <hz_x100> <duty> <points> <valid> <360 x 4 hex digits, mm per degree>
static void print_frame(const lidar_scan_t *s, u32 hz_x100) {
    if (con_free() < 1500) {     // console can't keep up: skip whole frame
        frames_skipped++;
        return;
    }
    con_puts("F ");
    con_putu(hz_x100, 0);  con_putc(' ');
    con_putu(motor_duty, 0); con_putc(' ');
    con_putu(s->points, 0); con_putc(' ');
    con_putu(s->valid, 0);  con_putc(' ');
    for (int i = 0; i < LIDAR_BINS; i++) {
        con_puthex(s->bins_mm[i], 4);
    }
    con_puts("\r\n");
}

static void handle_key(int c, lidar_parser_t *p) {
    static u8 duty_before_off = DUTY_DEFAULT;
    switch (c) {
    case '+':
        motor_set(motor_duty > 255 - DUTY_STEP ? 255 : motor_duty + DUTY_STEP);
        break;
    case '-':
        motor_set(motor_duty < DUTY_STEP ? 0 : motor_duty - DUTY_STEP);
        break;
    case 'm':
        if (motor_duty) {
            duty_before_off = motor_duty;
            motor_set(0);
        } else {
            motor_set(duty_before_off);
        }
        break;
    case 'f':               // toggle (for typing in PuTTY)
    case 'F':               // force on  (sent by pc/lidar_view.py)
    case 'x':               // force off (sent by pc/lidar_view.py on exit)
        frames_on = (c == 'f') ? !frames_on : (c == 'F');
        con_puts(frames_on ? "frames ON\r\n" : "frames OFF\r\n");
        return;
    case 'r':
        con_puts("restarting scan\r\n");
        lidar_start();
        lidar_parser_init(p);
        return;
    case 'h':
    case '?':
        print_help();
        return;
    default:
        return;
    }
    con_puts("duty ");
    con_putu(motor_duty, 0);
    con_puts(motor_duty ? "\r\n" : "  (motor off, watchdog paused)\r\n");
}

// ---------------------------------------------------------------- main
int main(void) {
    static lidar_parser_t parser;
    static lidar_scan_t   done;
    lidar_node_t node;

    // The SDT xiltimer BSP only starts the global timer inside the first
    // sleep()/usleep() call, and a JTAG boot (ps7_init, no FSBL) leaves it
    // stopped. Without this, XTime_GetTime() never advances and every
    // wait_ms()/timeout below spins forever.
    usleep(1000);

    motor_set(0);
    leds_set(0);

    con_puts("\r\n=== RPLIDAR A1 on Zybo Z7-10 ===\r\n");
    print_help();
    con_flush();

#if !FAKE_SRC
    motor_set(DUTY_DEFAULT);
    con_puts("Motor on, waiting 2 s for speed to settle\r\n");
    wait_ms(2000);
#else
    frames_on = 1;
#endif

    lidar_start();
    lidar_parser_init(&parser);

    u64 last_node = now_ticks();
    u64 last_rev  = 0;

    for (;;) {
        int b;
        while ((b = lidar_getc()) >= 0) {
            if (!lidar_feed(&parser, (u8)b, &node)) {
                continue;
            }
            last_node = now_ticks();
            if (!lidar_scan_add(&parser, &node, &done)) {
                continue;
            }

            u64 t = now_ticks();
            u32 hz_x100 = 0;
            if (last_rev != 0 && t > last_rev) {
                hz_x100 = (u32)(((u64)COUNTS_PER_SECOND * 100) / (t - last_rev));
            }
            last_rev = t;
            rev_count++;

            u8 leds = LED_SCANNING | ((rev_count & 1) ? LED_HEARTBEAT : 0);
            if (done.front_mm && done.front_mm < FRONT_NEAR_MM)   leds |= LED_NEAR;
            if (done.front_mm && done.front_mm < FRONT_DANGER_MM) leds |= LED_DANGER;
            leds_set(leds);

            print_summary(&done, hz_x100, &parser);
            if (frames_on) {
                print_frame(&done, hz_x100);
            }
        }

        con_pump();

#if !FAKE_SRC   // in the fake build the console UART carries scan bytes, not keys
        int c = con_getc();
        if (c >= 0) {
            handle_key(c, &parser);
            last_node = now_ticks();
        }
#endif

        if (motor_duty && ticks_to_ms(now_ticks() - last_node) > NO_DATA_TIMEOUT_MS) {
            con_puts("No scan data for 1.5 s, restarting\r\n");
            lidar_start();
            lidar_parser_init(&parser);
            last_node = now_ticks();
            last_rev = 0;
        }
    }
    return 0;
}
