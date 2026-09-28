`timescale 1ns/1ps
// Simple PWM for the RPLIDAR MOTOCTL input.
// duty = 0 -> motor off, 255 -> fully on (constant high).
// Default 24 kHz carrier at 100 MHz FCLK_CLK0 -> PERIOD = 4166 clocks.
module motor_pwm #(
    parameter integer CLK_HZ = 100_000_000,
    parameter integer PWM_HZ = 24_000
)(
    input  wire       clk,
    input  wire       rst_n,
    input  wire [7:0] duty,
    output reg        pwm
);

    localparam integer PERIOD = CLK_HZ / PWM_HZ;

    reg  [15:0] cnt;
    wire [31:0] thresh = (duty * PERIOD) >> 8;

    always @(posedge clk) begin
        if (!rst_n) begin
            cnt <= 16'd0;
            pwm <= 1'b0;
        end else begin
            cnt <= (cnt == PERIOD - 1) ? 16'd0 : cnt + 16'd1;
            pwm <= (duty == 8'hFF) ? 1'b1 : (cnt < thresh);
        end
    end

endmodule
