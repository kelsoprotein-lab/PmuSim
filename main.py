"""PmuSim entry point."""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _check_tk_version():
    """Warn if system Tk is too old for macOS dark mode."""
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        tk_version = root.tk.call('info', 'patchlevel')
        root.destroy()
        if str(tk_version).startswith('8.5'):
            print(f"WARNING: Tk {tk_version} detected. GUI may not render on macOS dark mode.")
            print("Fix: brew install python-tk@3.12 && /opt/homebrew/bin/python3.12 main.py")
            print()
    except Exception:
        pass


def main():
    _check_tk_version()
    from ui.app import App
    app = App()
    app.run()


if __name__ == "__main__":
    main()
