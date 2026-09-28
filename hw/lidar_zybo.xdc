## RPLIDAR A1 on Zybo Z7-10, Pmod JE (top row)
## Pins verified against Vivado 2025.1 board file digilentinc.com:zybo-z7-10:1.1
##   JE1 = V12  lidar TX  -> FPGA RX
##   JE2 = W16  FPGA TX   -> lidar RX
##   JE3 = J15  MOTOCTL (PWM out)
##   JE5 = GND  (join to lidar GND and the external 5 V supply GND)
set_property -dict { PACKAGE_PIN V12 IOSTANDARD LVCMOS33 } [get_ports lidar_uart_rxd]
set_property -dict { PACKAGE_PIN W16 IOSTANDARD LVCMOS33 } [get_ports lidar_uart_txd]
set_property -dict { PACKAGE_PIN J15 IOSTANDARD LVCMOS33 } [get_ports motoctl]
set_property PULLUP true [get_ports lidar_uart_rxd]

## Status LEDs (AXI GPIO channel 2)
##   LD0 = revolution heartbeat, LD1 = health good + scanning,
##   LD2 = object inside 1 m in front, LD3 = object inside 30 cm in front
set_property -dict { PACKAGE_PIN M14 IOSTANDARD LVCMOS33 } [get_ports {leds[0]}]
set_property -dict { PACKAGE_PIN M15 IOSTANDARD LVCMOS33 } [get_ports {leds[1]}]
set_property -dict { PACKAGE_PIN G14 IOSTANDARD LVCMOS33 } [get_ports {leds[2]}]
set_property -dict { PACKAGE_PIN D18 IOSTANDARD LVCMOS33 } [get_ports {leds[3]}]
