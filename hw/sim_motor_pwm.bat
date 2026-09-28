@echo off
rem Runs tb_motor_pwm with Vivado's xsim (no Icarus needed).
rem Usage: double-click, or run from this folder in cmd.
rem Set VIVADO_SETTINGS first if Vivado is installed somewhere else.
if "%VIVADO_SETTINGS%"=="" set VIVADO_SETTINGS=C:\Xilinx\2025.1\Vivado\settings64.bat
call "%VIVADO_SETTINGS%"
cd /d %~dp0
if not exist sim_out mkdir sim_out
cd sim_out
call xvlog ..\motor_pwm.v ..\tb_motor_pwm.v || goto :err
call xelab -debug typical tb_motor_pwm -s tb_motor_pwm_sim || goto :err
call xsim tb_motor_pwm_sim -runall || goto :err
goto :eof
:err
echo SIMULATION BUILD FAILED
exit /b 1
