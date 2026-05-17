import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))
from common import run_api
from snudorm.crawl import crawl_snudorm_menu


def main() -> None:
    run_api("SNUDORM", crawl_snudorm_menu)


if __name__ == "__main__":
    main()
