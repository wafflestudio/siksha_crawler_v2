import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))
from common import run_json
from snuco.crawl import crawl_snuco_menu


def main() -> None:
    run_json("SNUCO", crawl_snuco_menu, "snuco_payload.json")


if __name__ == "__main__":
    main()
