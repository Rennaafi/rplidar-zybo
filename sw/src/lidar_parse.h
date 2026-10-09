// RPLIDAR A1 scan-stream parser. Pure C, no Xilinx headers, so the same
// file builds in Vitis and on the PC (see ../host_test).
//
// Byte stream -> 5-byte measurement nodes -> one lidar_scan_t per revolution.
#ifndef LIDAR_PARSE_H
#define LIDAR_PARSE_H

#include <stdint.h>

#define LIDAR_BINS 360

// The protocol's sync check is only 2 bits (S != S-bar, C == 1), so random
// bytes pass it ~1 time in 4 (~1 in 5.7 with the angle check). Require this many good nodes in a row before
// trusting the alignment, and ignore "revolutions" shorter than the minimum
// (a real one has ~200-1000 points depending on motor speed).
#define LIDAR_LOCK_NODES   3
#define LIDAR_MIN_REV_PTS  100

// Request bytes (always prefixed with 0xA5)
#define LIDAR_CMD_STOP       0x25
#define LIDAR_CMD_RESET      0x40
#define LIDAR_CMD_SCAN       0x20
#define LIDAR_CMD_FORCE_SCAN 0x21
#define LIDAR_CMD_GET_INFO   0x50
#define LIDAR_CMD_GET_HEALTH 0x52

typedef struct {
    uint8_t  quality;   // 0..63
    uint8_t  start;     // 1 = first point of a new revolution
    uint16_t angle_q6;  // degrees * 64, 0..23039
    uint16_t dist_q2;   // millimetres * 4, 0 = no return
} lidar_node_t;

typedef struct {
    uint16_t points;              // nodes received in this revolution
    uint16_t valid;               // nodes with dist != 0
    uint16_t nearest_mm;          // 0 if no valid point
    uint16_t nearest_deg;
    uint16_t front_mm;            // nearest valid point within +/-30 deg of 0 deg
    uint16_t bins_mm[LIDAR_BINS]; // nearest distance per whole degree, 0 = none
} lidar_scan_t;

typedef struct {
    uint8_t      win[5];
    int          have;
    int          synced_rev;      // a start bit has been seen (first rev is partial)
    int          good_run;        // consecutive valid nodes, for the lock
    uint32_t     resync_drops;    // bytes thrown away while hunting for alignment
    uint32_t     nodes_total;
    lidar_scan_t cur;
} lidar_parser_t;

void lidar_parser_init(lidar_parser_t *p);

// Feed one byte. Returns 1 and fills *node when a valid node was decoded.
int lidar_feed(lidar_parser_t *p, uint8_t b, lidar_node_t *node);

// Add a node to the revolution in progress. When the node starts a new
// revolution the finished one is copied to *done and 1 is returned.
// The very first (partial) revolution and too-short ones are never reported.
int lidar_scan_add(lidar_parser_t *p, const lidar_node_t *n, lidar_scan_t *done);

#endif
