"""PmuSim entry point."""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    # Check Tk version before creating the real App
    import tkinter as tk
    tk_ver = tk.TkVersion
    if tk_ver < 8.6:
        print(f"WARNING: Tk {tk_ver} detected. GUI may not render on macOS dark mode.")
        print("Fix: brew install python-tk@3.12 && /opt/homebrew/bin/python3.12 main.py")
        print()

    from ui.app import App
    app = App()
    app.run()


if __name__ == "__main__":
    main()
