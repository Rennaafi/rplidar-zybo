# Creates the Vitis 2025.1 workspace from ../hw/lidar_zybo.xsa and builds the
# bare-metal app. API calls follow the journal the Vitis 2025.1 IDE writes
# (_ide/workspace_journal.py) for the same actions.
#
# Run (after build_hw.tcl has produced the .xsa):
#   <Vitis install>\settings64.bat      (e.g. C:\Xilinx\2025.1\Vitis)
#   cd sw
#   vitis -s build_sw.py
#
# Afterwards you can open the same workspace in the Vitis IDE:
#   vitis -w vitis_ws
import os
import shutil
import vitis

here = os.path.dirname(os.path.abspath(__file__))
ws = os.path.join(here, "vitis_ws")
xsa = os.path.normpath(os.path.join(here, "..", "hw", "lidar_zybo.xsa"))
src = os.path.join(here, "src")
domain = "standalone_ps7_cortexa9_0"

if not os.path.isfile(xsa):
    raise SystemExit("Missing " + xsa + " - run hw/build_hw.tcl first")

def _clear_readonly(func, path, exc_info):
    # Xilinx's generated headers land read-only; clear that so rmtree can proceed.
    os.chmod(path, 0o666)
    func(path)


if os.path.isdir(ws):
    shutil.rmtree(ws, onerror=_clear_readonly)   # always start clean; sources live in ./src
os.makedirs(ws)

client = vitis.create_client()
client.set_workspace(path=ws)

advanced_options = client.create_advanced_options_dict(dt_overlay="0")
platform = client.create_platform_component(
    name="lidar_platform",
    hw_design=xsa,
    os="standalone",
    cpu="ps7_cortexa9_0",
    domain_name=domain,
    generate_dtb=False,
    advanced_options=advanced_options,
    compiler="gcc",
)
platform.build()

xpfm = os.path.join(ws, "lidar_platform", "export", "lidar_platform", "lidar_platform.xpfm")
app = client.create_app_component(name="lidar_app", platform=xpfm, domain=domain)
app.import_files(
    from_loc=src,
    files=["main.c", "lidar_parse.c", "lidar_parse.h"],
    dest_dir_in_cmp="src",
)
app.build()

elf = os.path.join(ws, "lidar_app", "build", "lidar_app.elf")
print("ELF:", elf, "exists" if os.path.isfile(elf) else "NOT FOUND")
vitis.dispose()
