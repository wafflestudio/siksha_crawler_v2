import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))
from common import run_api
from snuco.crawl import crawl_snuco_menu


def main() -> None:
    run_api("SNUCO", crawl_snuco_menu)


if __name__ == "__main__":
    main()
