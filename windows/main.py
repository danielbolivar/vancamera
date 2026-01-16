"""
Punto de entrada principal de VanCamera Windows
"""
import sys
from ui_app import VanCameraApp


def main():
    """Función principal"""
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
    main()
