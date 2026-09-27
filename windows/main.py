"""
Punto de entrada principal de VanCamera Windows
"""
import sys
import multiprocessing


def _already_running() -> bool:
    """True if another VanCamera is open (its window is brought to the front).

    Two instances would both connect to the phone and keep replacing each other's connection,
    freezing the video every second.
    """
    if sys.platform != "win32":
        return False
    import ctypes
    kernel32 = ctypes.windll.kernel32
    user32 = ctypes.windll.user32
    # Kept for the whole process lifetime; Windows releases it on exit.
    main._mutex = kernel32.CreateMutexW(None, False, "Local\\VanCamera.SingleInstance")
    if kernel32.GetLastError() != 183:  # ERROR_ALREADY_EXISTS
        return False
    hwnd = user32.FindWindowW(None, "VanCamera")
    if hwnd:
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        user32.SetForegroundWindow(hwnd)
    return True


def main():
    """Función principal"""
    if _already_running():
        return
    # Import here to avoid issues with PyInstaller multiprocessing
    from ui_app import VanCameraApp

    try:
        app = VanCameraApp()
        app.run()
    except KeyboardInterrupt:
        print("\nAplicación cerrada por el usuario")
        sys.exit(0)
    except Exception as e:
        print(f"Error fatal: {e}")
        sys.exit(1)


if __name__ == "__main__":
    # Required for PyInstaller on Windows to prevent multiple windows
    multiprocessing.freeze_support()
    main()
