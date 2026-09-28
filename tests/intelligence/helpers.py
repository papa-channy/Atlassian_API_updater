import json
import pathlib

FIXTURE_DIR = pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "openapi"


def load_fixture(name: str) -> dict:
    with (FIXTURE_DIR / f"{name}-openapi.json").open("r", encoding="utf-8") as handle:
        return json.load(handle)
