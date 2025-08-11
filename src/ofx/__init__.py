from ofx.commands import app as main
from ofx._version import __version__


class MainApp:
    @classmethod
    def main(cls):
        main()


if __name__ == "__main__":
    main()
