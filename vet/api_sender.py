import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))
from common import run_api
from vet.crawl import crawl_vet_menu


def main() -> None:
    run_api("VET", crawl_vet_menu)


if __name__ == "__main__":
    main()
