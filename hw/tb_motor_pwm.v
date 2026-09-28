`timescale 1ns/1ps
// Testbench for motor_pwm: measures the high time over one full PWM period
// for several duty values and checks it against duty*PERIOD/256.
module tb_motor_pwm;

    localparam integer CLK_HZ = 100_000_000;
    localparam integer PWM_HZ = 24_000;
    localparam integer PERIOD = CLK_HZ / PWM_HZ;   // 4166

    reg        clk = 0;
    reg        rst_n = 0;
    reg  [7:0] duty = 0;
    wire       pwm;

    integer high_cnt;
    integer expected;
    integer i;
    integer errors = 0;

    motor_pwm #(.CLK_HZ(CLK_HZ), .PWM_HZ(PWM_HZ)) dut (
        .clk(clk), .rst_n(rst_n), .duty(duty), .pwm(pwm)
    );

    always #5 clk = ~clk;   // 100 MHz

    task check_duty;
        input [7:0] d;
        begin
            duty = d;
            // let the new duty settle for two full periods
            repeat (2 * PERIOD) @(posedge clk);
            high_cnt = 0;
            for (i = 0; i < PERIOD; i = i + 1) begin
                @(posedge clk);
                if (pwm) high_cnt = high_cnt + 1;
            end
            expected = (d == 8'hFF) ? PERIOD : (d * PERIOD) / 256;
            if (high_cnt == expected)
                $display("PASS duty=%3d high=%4d / %4d", d, high_cnt, PERIOD);
            else begin
                $display("FAIL duty=%3d high=%4d expected %4d", d, high_cnt, expected);
                errors = errors + 1;
            end
        end
    endtask

    initial begin
        $dumpfile("tb_motor_pwm.vcd");
        $dumpvars(0, tb_motor_pwm);

        repeat (10) @(posedge clk);
        if (pwm !== 1'b0) begin
            $display("FAIL pwm not low during reset");
            errors = errors + 1;
        end
        rst_n = 1;

        check_duty(8'd0);
        check_duty(8'd1);
        check_duty(8'd64);
        check_duty(8'd128);
        check_duty(8'd200);
        check_duty(8'd254);
        check_duty(8'd255);

        if (errors == 0) $display("ALL TESTS PASSED");
        else             $display("%0d TEST(S) FAILED", errors);
        $finish;
    end

endmodule
