# Programs the Zybo over JTAG and starts the app, without the Vitis IDE's
# Run button (which did not always source ps7_init.tcl correctly).
# Boot jumper JP5 must be on JTAG.
#
#   <Vitis install>\settings64.bat
#   cd sw
#   xsdb run_on_board.tcl
#
# Then open the Zybo's COM port at 115200 (PuTTY) or run pc/lidar_view.py.
set here [file normalize [file dirname [info script]]]
set bit  [file normalize $here/../hw/lidar_zybo.bit]
set elf  $here/vitis_ws/lidar_app/build/lidar_app.elf
set init [lindex [glob -nocomplain $here/vitis_ws/lidar_platform/hw/sdt/ps7_init.tcl \
                                   $here/vitis_ws/lidar_platform/export/lidar_platform/hw/ps7_init.tcl] 0]

foreach f [list $bit $elf $init] {
    if {$f eq "" || ![file exists $f]} { error "Missing file: '$f' (build hw and sw first)" }
}

connect
targets -set -nocase -filter {name =~ "APU*"}
rst -system
after 1000
puts "Programming FPGA: $bit"
fpga -file $bit
targets -set -nocase -filter {name =~ "APU*"}
source $init
ps7_init
ps7_post_config
targets -set -nocase -filter {name =~ "*Cortex-A9 MPCore #0*"}
rst -processor
puts "Downloading: $elf"
dow $elf
con
puts "Running. Open the Zybo COM port at 115200 to see the output."
