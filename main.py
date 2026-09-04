from main_window import MainWindow
import ttkbootstrap as ttkb
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) if not getattr(
    sys, 'frozen', False) else os.path.dirname(sys.executable))


def main():
    root = ttkb.Window(themename="bootstrap-light")
    root.title("HSS串口助手")
    root.geometry("1250x900")

    app = MainWindow(root)

    root.mainloop()


if __name__ == '__main__':
    main()
