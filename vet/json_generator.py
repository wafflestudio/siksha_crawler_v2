# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "requests",
#     "beautifulsoup4",
#     "pytz",
# ]
# ///

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))
from common import run_json
from vet.crawl import crawl_vet_menu


def main() -> None:
    run_json("VET", crawl_vet_menu, "vet_payload.json")


if __name__ == "__main__":
    main()
