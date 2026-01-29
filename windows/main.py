"""
Punto de entrada principal de VanCamera Windows
"""
import sys
import multiprocessing


def main():
    """Función principal"""
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
