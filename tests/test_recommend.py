import json
from pathlib import Path

import pytest

from starcoach.recommend import detect_platform, pick_plan, recommend

DEMO = Path(__file__).resolve().parents[1] / "examples" / "demo-node"


def make(tmp_path, files):
    for name, text in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return tmp_path


@pytest.mark.parametrize("files,platform", [
    ({"composer.json": json.dumps({"require": {"laravel/framework": "^11"}})}, "laravel"),
    ({"index.php": "<?php"}, "php"),
    ({"requirements.txt": "Django==5.0\n"}, "django"),
    ({"requirements.txt": "flask\n"}, "flask"),
    ({"requirements.txt": "requests\n"}, "python"),
    ({"package.json": json.dumps({"dependencies": {"next": "15"}})}, "next"),
    ({"package.json": json.dumps({"dependencies": {"react": "18"}, "devDependencies": {"vite": "5"}})}, "react"),
    ({"package.json": json.dumps({"scripts": {"start": "node a"}})}, "node"),
    ({"go.mod": "module x"}, "go"),
    ({"Dockerfile": "FROM nginx"}, "docker"),
    ({"index.html": "<h1>hi</h1>"}, "static"),
    ({"liara.json": json.dumps({"platform": "flask"}), "index.html": ""}, "flask"),
])
def test_detect_platform(tmp_path, files, platform):
    assert detect_platform(make(tmp_path, files))[0] == platform


def test_utf16_requirements(tmp_path):
    (tmp_path / "requirements.txt").write_text("Django==5\n", encoding="utf-16")
    assert detect_platform(tmp_path)[0] == "django"


def test_warnings_catch_known_failures(tmp_path):
    make(tmp_path, {"package.json": json.dumps({"name": "x"}), ".env": "SECRET=1"})
    w = " ".join(recommend(tmp_path).warnings)
    assert "start" in w and ".env" in w


def test_demo_app_has_no_warnings():
    a = recommend(DEMO)
    assert (a.platform, a.port, a.warnings) == ("node", 3000, [])


PLANS = {
    "free": {"available": True, "region": "iran", "price": 0, "RAM": {"amount": 0.25}, "CPU": {"amount": 0.1}},
    "g2-small": {"available": True, "region": "iran", "price": 100, "RAM": {"amount": 0.5}, "CPU": {"amount": 0.5}},
    "g2-medium": {"available": True, "region": "iran", "price": 200, "RAM": {"amount": 1}, "CPU": {"amount": 1}},
    "g2-old": {"available": False, "region": "iran", "price": 50, "RAM": {"amount": 4}, "CPU": {"amount": 2}},
    "legacy": {"available": True, "region": "iran", "price": 10, "RAM": {"amount": 8}, "CPU": {"amount": 4}},
}
BUNDLES = {"g2-small": {"bronze": {"available": True, "displayPrice": 0},
                        "gold": {"available": True, "displayPrice": 500000}}}


def test_pick_cheapest_plan_meeting_ram():
    assert pick_plan(PLANS, 512, BUNDLES) == {
        "id": "g2-small", "ram_gb": 0.5, "cpu": 0.5, "disk_gb": None,
        "price_per_hour": 100, "price_per_month": 72000, "bundle": "bronze", "bundle_price_per_month": 0}
    assert pick_plan(PLANS, 1024)["id"] == "g2-medium"
    assert pick_plan(PLANS, 64000) is None
