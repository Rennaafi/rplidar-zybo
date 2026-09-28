#include "lidar_parse.h"

#define FRONT_HALF_WINDOW_DEG 30

static void scan_clear(lidar_scan_t *s) {
    s->points = 0;
    s->valid = 0;
    s->nearest_mm = 0;
    s->nearest_deg = 0;
    s->front_mm = 0;
    for (int i = 0; i < LIDAR_BINS; i++) {
        s->bins_mm[i] = 0;
    }
}

void lidar_parser_init(lidar_parser_t *p) {
    p->have = 0;
    p->synced_rev = 0;
    p->good_run = 0;
    p->resync_drops = 0;
    p->nodes_total = 0;
    scan_clear(&p->cur);
}

int lidar_feed(lidar_parser_t *p, uint8_t b, lidar_node_t *node) {
    p->win[p->have++] = b;
    if (p->have < 5) {
        return 0;
    }

    uint8_t  s     = p->win[0] & 1;
    uint8_t  s_inv = (p->win[0] >> 1) & 1;
    uint8_t  c     = p->win[1] & 1;
    uint16_t ang   = ((uint16_t)p->win[2] << 7) | (p->win[1] >> 1);

    // Sync rule from the protocol: S != S-bar and C == 1. The angle range
    // check is extra and rejects most false locks on random data.
    if (s == s_inv || c != 1 || ang >= 360 * 64) {
        for (int i = 0; i < 4; i++) {
            p->win[i] = p->win[i + 1];
        }
        p->have = 4;
        p->resync_drops++;
        p->good_run = 0;
        return 0;
    }

    p->have = 0;
    if (p->good_run < LIDAR_LOCK_NODES) {
        p->good_run++;
    }
    if (p->good_run < LIDAR_LOCK_NODES) {
        return 0;   // plausible node, but not locked yet
    }
    node->quality  = p->win[0] >> 2;
    node->start    = s;
    node->angle_q6 = ang;
    node->dist_q2  = (uint16_t)p->win[3] | ((uint16_t)p->win[4] << 8);
    p->nodes_total++;
    return 1;
}

int lidar_scan_add(lidar_parser_t *p, const lidar_node_t *n, lidar_scan_t *done) {
    int finished = 0;
    lidar_scan_t *s = &p->cur;

    if (n->start) {
        if (p->synced_rev && s->points >= LIDAR_MIN_REV_PTS) {
            *done = *s;
            finished = 1;
        }
        p->synced_rev = 1;
        scan_clear(s);
    }

    s->points++;
    if (n->dist_q2 == 0) {
        return finished;
    }

    uint16_t mm  = n->dist_q2 >> 2;
    uint16_t deg = (uint16_t)(((uint32_t)n->angle_q6 + 32) >> 6);  // round to whole degree
    if (deg >= LIDAR_BINS) {
        deg -= LIDAR_BINS;
    }
    if (mm == 0) {
        mm = 1;   // sub-millimetre but valid; keep it distinguishable from "none"
    }

    s->valid++;
    if (s->nearest_mm == 0 || mm < s->nearest_mm) {
        s->nearest_mm = mm;
        s->nearest_deg = deg;
    }
    if (s->bins_mm[deg] == 0 || mm < s->bins_mm[deg]) {
        s->bins_mm[deg] = mm;
    }
    if (deg <= FRONT_HALF_WINDOW_DEG || deg >= LIDAR_BINS - FRONT_HALF_WINDOW_DEG) {
        if (s->front_mm == 0 || mm < s->front_mm) {
            s->front_mm = mm;
        }
    }
    return finished;
}
