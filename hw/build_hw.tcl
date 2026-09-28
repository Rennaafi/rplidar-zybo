# Builds the whole Stage 2B hardware in one go:
#   Zynq PS7 (Zybo preset, FCLK0 = 100 MHz)
#   AXI UART Lite  115200 8N1   -> lidar_uart_rxd / lidar_uart_txd (Pmod JE1/JE2)
#   AXI GPIO ch1 (8 bit out)    -> motor_pwm.duty -> motoctl       (Pmod JE3)
#   AXI GPIO ch2 (4 bit out)    -> leds[3:0]                       (LD0..LD3)
# then synth + impl + bitstream and exports lidar_zybo.xsa (with bitstream).
#
# Run from a Vivado 2025.1 shell (or any cmd after settings64.bat):
#   cd hw
#   vivado -mode batch -source build_hw.tcl
# Open the result in the GUI afterwards with:
#   vivado vivado_proj\lidar_zybo.xpr

set hw_dir   [file normalize [file dirname [info script]]]
set proj_dir $hw_dir/vivado_proj
set proj     lidar_zybo
set bd_name  system

create_project $proj $proj_dir -part xc7z010clg400-1 -force
# Use the newest installed Zybo Z7-10 board file (1.1 on this machine)
set board [lindex [lsort [get_board_parts -quiet digilentinc.com:zybo-z7-10:*]] end]
if {$board eq ""} {
    error "Zybo Z7-10 board files not found. Install Digilent board files first."
}
puts "Using board part: $board"
set_property board_part $board [current_project]
set_property target_language Verilog [current_project]

add_files -norecurse $hw_dir/motor_pwm.v
add_files -fileset constrs_1 -norecurse $hw_dir/lidar_zybo.xdc
add_files -fileset sim_1 -norecurse $hw_dir/tb_motor_pwm.v
set_property top tb_motor_pwm [get_filesets sim_1]
update_compile_order -fileset sources_1

# ---------------------------------------------------------------- block design
create_bd_design $bd_name

set ps [create_bd_cell -type ip -vlnv xilinx.com:ip:processing_system7 processing_system7_0]
apply_bd_automation -rule xilinx.com:bd_rule:processing_system7 \
    -config {make_external "FIXED_IO, DDR" apply_board_preset "1" Master "Disable" Slave "Disable"} $ps
set_property -dict [list \
    CONFIG.PCW_FPGA0_PERIPHERAL_FREQMHZ {100} \
    CONFIG.PCW_USE_M_AXI_GP0 {1} \
] $ps

set uart [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_uartlite axi_uartlite_0]
set_property -dict [list \
    CONFIG.C_BAUDRATE {115200} \
    CONFIG.C_DATA_BITS {8} \
    CONFIG.C_USE_PARITY {0} \
] $uart

set gpio [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_gpio axi_gpio_0]
set_property -dict [list \
    CONFIG.C_GPIO_WIDTH {8} \
    CONFIG.C_ALL_OUTPUTS {1} \
    CONFIG.C_DOUT_DEFAULT {0x00000000} \
    CONFIG.C_IS_DUAL {1} \
    CONFIG.C_GPIO2_WIDTH {4} \
    CONFIG.C_ALL_OUTPUTS_2 {1} \
] $gpio

set pwm [create_bd_cell -type module -reference motor_pwm motor_pwm_0]
set_property -dict [list CONFIG.CLK_HZ {100000000} CONFIG.PWM_HZ {24000}] $pwm

# AXI hookup (creates the interconnect and proc_sys_reset)
foreach slv [list axi_uartlite_0/S_AXI axi_gpio_0/S_AXI] {
    apply_bd_automation -rule xilinx.com:bd_rule:axi4 -config [list \
        Clk_master {Auto} Clk_slave {Auto} Clk_xbar {Auto} \
        Master {/processing_system7_0/M_AXI_GP0} Slave "/$slv" \
        ddr_seg {Auto} intc_ip {New AXI Interconnect} master_apm {0}] \
        [get_bd_intf_pins $slv]
}

# External ports: names here must match lidar_zybo.xdc
create_bd_intf_port -mode Master -vlnv xilinx.com:interface:uart_rtl:1.0 lidar_uart
connect_bd_intf_net [get_bd_intf_ports lidar_uart] [get_bd_intf_pins axi_uartlite_0/UART]

create_bd_port -dir O motoctl
create_bd_port -dir O -from 3 -to 0 leds

set rst [lindex [get_bd_cells -filter {VLNV =~ "*proc_sys_reset*"}] 0]
connect_bd_net [get_bd_pins processing_system7_0/FCLK_CLK0] [get_bd_pins motor_pwm_0/clk]
connect_bd_net [get_bd_pins $rst/peripheral_aresetn]        [get_bd_pins motor_pwm_0/rst_n]
connect_bd_net [get_bd_pins axi_gpio_0/gpio_io_o]           [get_bd_pins motor_pwm_0/duty]
connect_bd_net [get_bd_pins motor_pwm_0/pwm]                [get_bd_ports motoctl]
connect_bd_net [get_bd_pins axi_gpio_0/gpio2_io_o]          [get_bd_ports leds]

# Fixed addresses (the C code falls back to these if xparameters.h names differ)
assign_bd_address
foreach {pat off} {*axi_uartlite_0* 0x42C00000 *axi_gpio_0* 0x41200000} {
    set seg [get_bd_addr_segs -quiet -of_objects [get_bd_addr_spaces processing_system7_0/Data] -filter "NAME =~ $pat"]
    if {$seg ne ""} {
        set_property offset $off $seg
        set_property range 64K $seg
    }
}

regenerate_bd_layout
validate_bd_design
save_bd_design

# ---------------------------------------------------------------- wrapper + build
set bd_file [get_files $bd_name.bd]
generate_target all $bd_file
set wrapper [make_wrapper -files $bd_file -top]
add_files -norecurse $wrapper
set_property top ${bd_name}_wrapper [current_fileset]
update_compile_order -fileset sources_1

launch_runs impl_1 -to_step write_bitstream -jobs 4
wait_on_run impl_1

if {[get_property PROGRESS [get_runs impl_1]] ne "100%"} {
    error "Implementation failed, open $proj_dir/$proj.xpr and check the run logs."
}

open_run impl_1
report_utilization -file $hw_dir/utilization.rpt
report_timing_summary -file $hw_dir/timing.rpt
set wns [get_property SLACK [get_timing_paths -max_paths 1 -nworst 1 -setup]]
puts "Worst setup slack (WNS): $wns ns"

write_hw_platform -fixed -include_bit -force -file $hw_dir/lidar_zybo.xsa
file copy -force $proj_dir/$proj.runs/impl_1/${bd_name}_wrapper.bit $hw_dir/lidar_zybo.bit
puts "DONE: $hw_dir/lidar_zybo.xsa"
