"""Look at a project folder and suggest how to run it on Liara (research 02 §6, §8)."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

# Default ports per platform (liara-cloud/cli@14ec35f:src/utils/get-port.ts:5-28).
DEFAULT_PORTS = {"static": 80, "python": 80, "react": 80, "vue": 80, "angular": 80, "laravel": 80,
                 "wordpress": 80, "django": 80, "flask": 80, "php": 80, "next": 3000,
                 "node": 3000, "docker": 3000, "dotnet": 80, "go": 8080}

# RAM need in MB per platform class. Our own design choice; refine with real usage (F facts).
RAM_NEED_MB = {"static": 256, "react": 256, "vue": 256, "angular": 256,
               "node": 512, "python": 512, "flask": 512, "go": 512, "php": 512,
               "django": 1024, "laravel": 1024, "wordpress": 1024, "dotnet": 1024,
               "next": 1024, "docker": 1024}


@dataclass
class Advice:
    platform: str
    port: int
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    ram_need_mb: int = 512
    plan: dict | None = None
    deploy_methods: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _read_text(path: Path) -> str:
    try:
        raw = path.read_bytes()
    except OSError:
        return ""
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16", "replace")
    return raw.decode("utf-8", "replace")


def detect_platform(root: Path) -> tuple[str, str]:
    """Return (platform, reason). Same order as the official CLI detector."""
    liara_json = _read_json(root / "liara.json")
    if liara_json.get("platform"):
        return liara_json["platform"], "liara.json sets the platform"
    if (root / "composer.json").is_file():
        req = _read_json(root / "composer.json").get("require", {})
        if "laravel/framework" in req or "laravel/lumen-framework" in req:
            return "laravel", "composer.json requires laravel/framework"
        return "php", "composer.json found"
    if (root / "index.php").is_file():
        return "php", "index.php found"
    if (root / "pyproject.toml").is_file():
        return "python", "pyproject.toml found"
    for name in ("requirements.txt", "Pipfile"):
        if (root / name).is_file():
            text = _read_text(root / name).lower()
            if "django" in text:
                return "django", f"{name} lists Django"
            if "flask" in text:
                return "flask", f"{name} lists Flask"
            return "python", f"{name} found"
    if (root / "package.json").is_file():
        pkg = _read_json(root / "package.json")
        deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
        dev = pkg.get("devDependencies", {})
        if "next" in deps:
            return "next", "package.json depends on next"
        if "@angular/core" in deps:
            return "angular", "package.json depends on @angular/core"
        if "@vue/cli-service" in dev or ("vue" in deps and "vite" in dev):
            return "vue", "package.json is a Vue app"
        if "react-scripts" in deps or ("vite" in dev and "react" in deps) or "preact" in deps:
            return "react", "package.json is a React app"
        return "node", "package.json found"
    if (root / "wp-content").is_dir():
        return "wordpress", "wp-content/ found"
    if (root / "go.mod").is_file():
        return "go", "go.mod found"
    if (root / "Dockerfile").is_file():
        return "docker", "Dockerfile found"
    return "static", "no framework files; serving files as a static site"


def check_project(root: Path, platform: str) -> list[str]:
    """Known deploy failures we can catch before uploading."""
    warnings = []
    pkg = _read_json(root / "package.json")
    if platform == "node" and "start" not in pkg.get("scripts", {}):
        warnings.append("package.json has no \"start\" script. Liara runs `npm start`, so the deploy will fail.")
    if platform == "next":
        cfg = "".join(_read_text(p) for p in root.glob("next.config.*"))
        if "standalone" not in cfg:
            warnings.append("next.config has no `output: 'standalone'`. Liara tries to add it; add it yourself to be safe.")
    if platform in ("django", "flask") and not (root / "requirements.txt").is_file():
        warnings.append("No requirements.txt. Liara needs it to install Python packages.")
    if any(root.glob(".env*")) and not all(p.name == ".env.example" for p in root.glob(".env*")):
        warnings.append("A .env file is here. We never upload it. Set those values as Liara env vars instead.")
    if platform == "node" and (root / "package.json").is_file():
        src = " ".join(_read_text(p) for p in list(root.glob("*.js"))[:20])
        if re.search(r"listen\(\s*\d{4}", src) and "process.env.PORT" not in src:
            warnings.append("The app listens on a fixed port. Make sure it matches the port Liara uses.")
    if not any(p for p in root.iterdir() if p.name not in (".git", "liara.json")):
        warnings.append("The folder is empty.")
    return warnings


def deploy_methods(root: Path, platform: str) -> list[dict]:
    """Ways to put this project on Liara, best first. Sources: research 02 (API flow, liara.json),
    docs.liara.ir deploy guides (console zip upload, CLI, GitHub)."""
    has_git = (root / ".git").exists()
    methods = [
        {"id": "starcoach", "name": "StarCoach deploy (this tool)",
         "when": "Simplest: one command or one chat message; shows build progress, explains failures, never uploads .env.",
         "how": f"starcoach deploy {root} --app <name>"},
        {"id": "console", "name": "Liara console upload",
         "when": "No tools at all: zip the folder and drag it into the app page (docs: nodejs/how-tos/deploy-app).",
         "how": "console.liara.ir → app → Deploy → upload zip"},
        {"id": "cli", "name": "Liara CLI",
         "when": "You already use Node.js tools and want liara.json settings in the repo.",
         "how": "npm i -g @liara/cli && liara deploy"},
    ]
    if has_git:
        methods.append({"id": "github", "name": "GitHub (CI)",
                        "when": "The project is in git: deploy on every push from GitHub Actions with the CLI.",
                        "how": "a workflow step running `liara deploy` with LIARA_API_TOKEN as a secret"})
    if platform == "docker":
        methods[0]["when"] += " Your Dockerfile is built on Liara."
    return methods


def pick_plan(plans: dict, ram_need_mb: int, bundles: dict | None = None) -> dict | None:
    """Cheapest plan whose RAM meets the need.

    `plans` is /v1/me -> plans.projects; `bundles` is plans.projectBundlePlans.
    Like the official CLI, only available Iran plans named `g2*` are offered
    (liara-cloud/cli@14ec35f:src/commands/app/create.ts:200-213). The free plan is skipped:
    it allows one app and few platforms.
    """
    options = []
    for plan_id, p in (plans or {}).items():
        if not isinstance(p, dict) or not p.get("available") or "g2" not in plan_id:
            continue
        if p.get("region", "iran") != "iran":
            continue
        ram_gb = (p.get("RAM") or {}).get("amount")
        price = p.get("price")
        if ram_gb is None or price is None:
            continue
        if ram_gb * 1024 >= ram_need_mb:
            options.append((price, ram_gb, plan_id, p))
    if not options:
        return None
    price, ram_gb, plan_id, p = min(options, key=lambda o: (o[0], o[1]))
    pick = {"id": plan_id, "ram_gb": ram_gb, "cpu": (p.get("CPU") or {}).get("amount"),
            "disk_gb": p.get("volume"), "price_per_hour": price, "price_per_month": round(price * 720)}
    # Feature bundle (structure from create.ts:156-172): bundles[plan_id][bundle] = {available, displayPrice}.
    choices = [(b.get("displayPrice") or 0, name) for name, b in ((bundles or {}).get(plan_id) or {}).items()
               if isinstance(b, dict) and b.get("available")]
    if choices:
        bundle_price, bundle = min(choices)
        pick.update(bundle=bundle, bundle_price_per_month=bundle_price)
    # Totals the user actually pays (plan + bundle). An LLM reading only the plan price under-quotes (F13).
    bundle_monthly = pick.get("bundle_price_per_month", 0)
    pick["total_per_hour"] = round(price + bundle_monthly / 720, 2)
    pick["total_per_month"] = round(price * 720 + bundle_monthly)
    return pick


def hourly_cost(plans: dict, bundles: dict | None, plan_id: str, bundle: str | None) -> float | None:
    """Toman per hour: plan `price` is hourly; bundle `displayPrice` is monthly (÷ 720), per F11."""
    plan = (plans or {}).get(plan_id) or {}
    if plan.get("price") is None:
        return None
    monthly_bundle = (((bundles or {}).get(plan_id) or {}).get(bundle or "") or {}).get("displayPrice") or 0
    return round(plan["price"] + monthly_bundle / 720, 2)


def recommend(root: Path, plans: dict | None = None, bundles: dict | None = None) -> Advice:
    root = Path(root)
    if not root.is_dir():
        raise FileNotFoundError(f"Folder not found: {root}")
    platform, reason = detect_platform(root)
    port = _read_json(root / "liara.json").get("port") or DEFAULT_PORTS.get(platform, 3000)
    advice = Advice(platform=platform, port=int(port), reasons=[reason],
                    ram_need_mb=RAM_NEED_MB.get(platform, 512))
    advice.reasons.append(f"Port {advice.port} is the Liara default for {platform}.")
    advice.warnings = check_project(root, platform)
    advice.deploy_methods = deploy_methods(root, platform)
    if plans:
        advice.plan = pick_plan(plans, advice.ram_need_mb, bundles)
        if advice.plan:
            advice.reasons.append(
                f"Plan {advice.plan['id']} is the cheapest with at least {advice.ram_need_mb} MB RAM.")
    return advice
