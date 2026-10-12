# Only what the arm needs: the port's own startup modules (filesystem mount
# etc.) and the arm app, frozen so it runs from flash and leaves the Python
# heap for live data. www_data.py is generated from app/www by build.sh.
freeze("$(PORT_DIR)/modules")
freeze("$(BOARD_DIR)/../../../app", ("arm.py", "lump.py", "emg.py", "web.py", "www_data.py"))
