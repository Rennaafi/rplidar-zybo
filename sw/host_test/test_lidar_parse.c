// PC-side test for src/lidar_parse.c (the exact file that runs on the Zybo).
// Build + run from this folder:
//   gcc -std=c99 -Wall -Wextra -I../src test_lidar_parse.c ../src/lidar_parse.c -o test_lidar_parse
//   ./test_lidar_parse
#include <stdio.h>
#include <stdlib.h>
#include "lidar_parse.h"

static int errors;

#define CHECK(cond, ...) do { \
    if (cond) { printf("PASS "); } else { printf("FAIL "); errors++; } \
    printf(__VA_ARGS__); printf("\n"); \
} while (0)

static uint8_t stream[200000];
static int n_stream;

static void put_node(int start, int quality, double deg, double mm) {
    uint16_t a = (uint16_t)(deg * 64.0 + 0.5);
    uint16_t d = (uint16_t)(mm * 4.0 + 0.5);
    stream[n_stream++] = (uint8_t)((quality << 2) | ((!start) << 1) | (start ? 1 : 0));
    stream[n_stream++] = (uint8_t)(((a & 0x7F) << 1) | 1);
    stream[n_stream++] = (uint8_t)(a >> 7);
    stream[n_stream++] = (uint8_t)(d & 0xFF);
    stream[n_stream++] = (uint8_t)(d >> 8);
}

// One revolution: 'pts' points evenly spaced, object at 90 deg (500 mm),
// wall at 2000 mm everywhere else, every 10th point invalid (dist 0).
static void put_rev(int pts, double offset) {
    for (int i = 0; i < pts; i++) {
        double deg = offset + i * 360.0 / pts;
        if (deg >= 360.0) deg -= 360.0;
        double mm = (deg > 85 && deg < 95) ? 500.0 : 2000.0;
        if (deg > 355 || deg < 5) mm = 800.0;   // something in front
        if (i % 10 == 9) mm = 0;
        put_node(i == 0, 40, deg, mm);
    }
}

int main(void) {
    lidar_parser_t p;
    lidar_scan_t done;
    lidar_node_t node;

    // Leading garbage (e.g. tail of the SCAN descriptor + noise), then
    // half a revolution, then 3 full revolutions, one byte dropped mid-way.
    const uint8_t junk[] = { 0x5A, 0x05, 0x00, 0x00, 0x40, 0x81, 0x13, 0x77, 0xFF };
    for (unsigned i = 0; i < sizeof junk; i++) stream[n_stream++] = junk[i];
    for (int i = 180; i < 360; i++) put_node(0, 40, i, 1500);
    put_rev(360, 0.3);
    int drop_at = n_stream + 5 * 100 + 2;   // lose one byte inside revolution 2
    put_rev(362, 0.1);
    put_rev(358, 0.5);
    put_node(1, 40, 0.2, 1000);              // closes revolution 3

    lidar_parser_init(&p);
    int revs = 0;
    lidar_scan_t first;
    uint16_t pts[8];
    for (int i = 0; i < n_stream; i++) {
        if (i == drop_at) continue;
        if (lidar_feed(&p, stream[i], &node) && lidar_scan_add(&p, &node, &done)) {
            if (revs == 0) first = done;
            if (revs < 8) pts[revs] = done.points;
            revs++;
        }
    }

    CHECK(revs == 3, "3 complete revolutions reported (got %d), partial first one skipped", revs);
    CHECK(first.points == 360, "rev1 points = 360 (got %u)", first.points);
    CHECK(first.valid == 324, "rev1 valid = 324 (got %u)", first.valid);
    CHECK(first.nearest_mm == 500, "rev1 nearest = 500 mm (got %u)", first.nearest_mm);
    CHECK(first.nearest_deg >= 85 && first.nearest_deg <= 95, "rev1 nearest angle ~90 deg (got %u)", first.nearest_deg);
    CHECK(first.front_mm == 800, "rev1 front = 800 mm (got %u)", first.front_mm);
    CHECK(first.bins_mm[180] == 2000, "rev1 bin 180 = 2000 mm (got %u)", first.bins_mm[180]);
    CHECK(first.bins_mm[90] == 500, "rev1 bin 90 = 500 mm (got %u)", first.bins_mm[90]);
    CHECK(revs >= 2 && pts[1] >= 355 && pts[1] <= 362, "rev2 survives a dropped byte (points %u)", pts[1]);
    CHECK(revs >= 3 && pts[2] == 358, "rev3 points = 358 after resync (got %u)", pts[2]);
    printf("info: resync drops = %u, nodes = %u\n", (unsigned)p.resync_drops, (unsigned)p.nodes_total);

    // Pure noise must not produce a revolution storm
    lidar_parser_init(&p);
    srand(1);
    int noise_revs = 0;
    for (int i = 0; i < 100000; i++) {
        if (lidar_feed(&p, (uint8_t)rand(), &node) && lidar_scan_add(&p, &node, &done)) noise_revs++;
    }
    CHECK(noise_revs == 0, "random noise gives no revolutions (%u nodes leaked, %d revs)",
          (unsigned)p.nodes_total, noise_revs);

    if (errors == 0) printf("ALL TESTS PASSED\n");
    else             printf("%d TEST(S) FAILED\n", errors);
    return errors != 0;
}
