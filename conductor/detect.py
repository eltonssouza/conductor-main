"""Best-effort project type + technology detection from root manifests.

Used by `cdt init` to pick the role subset and seed the stack file;
the user's Claude finalizes the stack from the real manifests afterwards.

Monorepo-aware: scans the project root plus subdirectories up to two levels
deep (skipping vendored/build noise), so a fullstack repo with `backend/` and
`frontend/` manifests is detected even when the root holds only a thin shell
package.json.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

# Canonical monorepo subtree walk; shared with project.py (one source of truth).
from .project import search_roots as _search_roots

VALID_TYPES = ("backend", "frontend", "mobile", "fullstack", "library",
               "data", "unknown")


def _read_json(path: Path) -> dict:
    try:
        # utf-8-sig: tolerate a BOM (Windows editors / PowerShell Out-File add one,
        # which would otherwise make json.loads choke and the manifest read as {}).
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (ValueError, OSError) as exc:
        # Keep the {} contract (callers depend on it) but, when a manifest
        # actually exists yet fails to parse, surface why detection missed it.
        if path.exists():
            print(f"cdt: warning: could not parse {path.name}: {exc}",
                  file=sys.stderr)
        return {}


def _rel(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.name


class _Lookup:
    """Manifest lookups bound to a project's search roots (root + subtree).

    Centralizes the three search primitives the detection phases share, so each
    phase stays a flat sequence of "does this manifest exist?" checks.
    """

    def __init__(self, root: Path, search: List[Path]) -> None:
        self.root = root
        self.search = search

    def find(self, name: str) -> str | None:
        """First search root containing `name`; returns its relative path."""
        for r in self.search:
            p = r / name
            if p.exists():
                return _rel(p, self.root)
        return None

    def glob_first(self, pattern: str) -> str | None:
        for r in self.search:
            for m in r.glob(pattern):
                return _rel(m, self.root)
        return None

    def has_dir(self, name: str) -> bool:
        return self.find(name) is not None


class _Signals:
    """Accumulator for one detection pass: techs/evidence plus the type flags."""

    def __init__(self) -> None:
        self.techs: List[str] = []
        self.evidence: List[str] = []
        self.front = False
        self.back = False
        self.mobile = False

    def ptype(self) -> str:
        """Conservative classification: mobile wins, then mixed -> fullstack."""
        if self.mobile:
            return "mobile"
        if self.front and self.back:
            return "fullstack"
        if self.front:
            return "frontend"
        if self.back:
            return "backend"
        return "unknown"


def _merge_js_deps(lk: _Lookup, sig: _Signals) -> dict:
    """Merge deps from every package.json across the tree; record them as evidence."""
    deps: dict = {}
    pkg_paths: List[str] = []
    for r in lk.search:
        p = r / "package.json"
        if p.exists():
            pkg = _read_json(p)
            if pkg:
                deps.update(pkg.get("dependencies", {}))
                deps.update(pkg.get("devDependencies", {}))
                pkg_paths.append(_rel(p, lk.root))
    if pkg_paths:
        sig.evidence.extend(pkg_paths)
    return deps


def _detect_js(lk: _Lookup, sig: _Signals, deps: dict) -> None:
    """JS/TS ecosystem signals from the merged package.json deps + config files."""
    if lk.has_dir("angular.json") or "@angular/core" in deps:
        sig.front = True; sig.techs.append("Angular")
    if "react" in deps:
        if "react-native" in deps:
            sig.mobile = True; sig.techs.append("React Native")
        else:
            sig.front = True; sig.techs.append("React")
    if "vue" in deps:
        sig.front = True; sig.techs.append("Vue")
    if "svelte" in deps:
        sig.front = True; sig.techs.append("Svelte")
    if "next" in deps:
        sig.front = True; sig.techs.append("Next.js")
    if lk.glob_first("vite.config.js") or lk.glob_first("vite.config.ts"):
        sig.front = True; sig.techs.append("Vite")
    # Node backend. NestJS/Fastify are unambiguous. Express, however, also ships
    # as the SSR server of an Angular Universal app (@angular/ssr); in that case
    # it is not a separate backend, so only count it when no Angular SSR is present.
    if "@nestjs/core" in deps or "fastify" in deps:
        sig.back = True; sig.techs.append("Node.js")
    elif "express" in deps and not ("@angular/ssr" in deps or "@angular/core" in deps):
        sig.back = True; sig.techs.append("Node.js")


def _detect_backend(lk: _Lookup, sig: _Signals) -> None:
    """Non-JS backend manifests (JVM, Go, Ruby, PHP, Rust, Python, .NET)."""
    for f, tech in (("pom.xml", "Java/Maven"), ("build.gradle", "Java/Gradle"),
                    ("go.mod", "Go"), ("Gemfile", "Ruby"),
                    ("composer.json", "PHP"), ("Cargo.toml", "Rust")):
        hit = lk.find(f)
        if hit:
            sig.back = True; sig.techs.append(tech); sig.evidence.append(hit)
    py = lk.find("requirements.txt") or lk.find("pyproject.toml") or lk.find("manage.py")
    if py:
        sig.back = True; sig.techs.append("Python"); sig.evidence.append(py)
    csproj = lk.glob_first("*.csproj")
    if csproj:
        sig.back = True; sig.techs.append(".NET"); sig.evidence.append(csproj)
    php = lk.glob_first("*.php")  # composer.json is already handled above
    if php:
        sig.back = True; sig.techs.append("PHP"); sig.evidence.append(php)


def _detect_mobile(lk: _Lookup, sig: _Signals) -> None:
    """Mobile manifests: Flutter, native Android+iOS pair, Xcode project."""
    flutter = lk.find("pubspec.yaml")
    if flutter:
        sig.mobile = True; sig.techs.append("Flutter"); sig.evidence.append(flutter)
    if lk.has_dir("android") and lk.has_dir("ios"):
        sig.mobile = True; sig.evidence.append("android/+ios/")
    xcode = lk.glob_first("*.xcodeproj")
    if xcode:
        sig.mobile = True; sig.techs.append("iOS/Xcode"); sig.evidence.append(xcode)


def _detect_static_html(lk: _Lookup, sig: _Signals, deps: dict) -> None:
    """Hand-written static site: HTML present but no package.json anywhere (so it
    is not an unbuilt JS app). `index.html` is the strong signal; fall back to
    any *.html at a search root. Guarded by `not deps` so real frontend
    frameworks are never tagged "Static HTML".
    """
    if not sig.front and not deps:
        html = lk.find("index.html") or lk.glob_first("*.html")
        if html:
            sig.front = True; sig.techs.append("Static HTML"); sig.evidence.append(html)


def detect(root: Path) -> Tuple[str, List[str], List[str]]:
    """Returns (type, technologies, evidence) from root + subdir manifests.

    Conservative: mixed front+back signals -> fullstack; nothing recognized ->
    unknown, so the command/owner can classify. Evidence entries are paths
    relative to the project root, so monorepo locations are visible.
    """
    lk = _Lookup(root, _search_roots(root))
    sig = _Signals()

    deps = _merge_js_deps(lk, sig)   # JS/TS first: deps gate the later phases
    _detect_js(lk, sig, deps)
    _detect_backend(lk, sig)
    _detect_mobile(lk, sig)
    _detect_static_html(lk, sig, deps)

    return (sig.ptype(),
            list(dict.fromkeys(sig.techs)),
            list(dict.fromkeys(sig.evidence)))


# --- library stack mapping ---------------------------------------------------
# Maps a detected technology (from detect()) to the Conductor library `stack` id
# of the books that teach it — and only ids that actually have books in the
# corpus. `cdt up` uses this to auto-select what to ingest for the current project.
_TECH_STACK = {
    "Angular": "angular",
    "React Native": "react-native",
    "Node.js": "node",
    "Go": "go",
    "Python": "python",
    "Ruby": "ruby",
    "Java/Maven": "java",
    "Java/Gradle": "java",
    "React": "react",              # plain React (react dep without react-native)
    "Vue": "vue",
    "Svelte": "svelte",
    "Next.js": "nextjs",
    "PHP": "php",
    "Rust": "rust",
    ".NET": "dotnet",
    "Flutter": "flutter",
    "iOS/Xcode": "swift",
}

# Framework label prefix (as profile() writes it) -> stack id. profile() knows
# the version, so these resolve to `id@major`. Order: more-specific prefix first.
# react-native uses 0.x, so its "major" is not an edition -> id only (no version).
_FW_STACK = (
    ("react native", "react-native"),
    ("angular", "angular"), ("react", "react"), ("vue", "vue"),
    ("svelte", "svelte"), ("next", "nextjs"), ("nestjs", "nestjs"),
    ("express", "express"), ("fastify", "fastify"), ("spring boot", "spring"),
    ("django", "django"), ("fastapi", "fastapi"), ("flask", "flask"),
)
_FW_NO_VERSION = {"react-native"}


def library_stacks(root: Path) -> List[str]:
    """The library `stack` ids matching a project's detected technologies.

    Drives `cdt up`'s auto-selection: a Java/Spring + Angular project resolves to
    `java@<v>`, `spring@<v>`, `angular@<v>` (+ `javascript`). Languages and
    frameworks are versioned (`id@major`) when the profile knows the version, so
    the nearest book edition is picked. Techs with no book still map to nothing.
    """
    _, techs, _ = detect(root)
    ids = {sid for t in techs if (sid := _TECH_STACK.get(t))}

    deps: dict = {}
    pkg_seen = False
    for r in _search_roots(root):
        p = r / "package.json"
        if p.exists():
            pkg = _read_json(p)
            if pkg:
                pkg_seen = True
                deps.update(pkg.get("dependencies", {}))
                deps.update(pkg.get("devDependencies", {}))
    if any(k in deps for k in ("graphql", "@apollo/client", "@apollo/server", "apollo-server")):
        ids.add("graphql")
    if pkg_seen:                      # a JS/TS ecosystem -> the general JavaScript books
        ids.add("javascript")
    if "ruby" in ids:                 # Rails when the Gemfile asks for it
        for r in _search_roots(root):
            g = r / "Gemfile"
            if g.exists() and "rails" in _read_text(g).lower():
                ids.add("rails")
                break

    # Frameworks (incl. backend ones that aren't detect() techs: Spring Boot,
    # NestJS, Django, …) come from profile(), which also carries their version.
    # That gives `id@major` so `cdt up` pins the nearest book edition; languages
    # add Java/Python majors. Ids with no known version stay bare.
    def first_major(s: str):
        m = re.search(r"(\d+)", s)    # first number in e.g. "Angular 21"
        return m.group(1) if m else None

    ver: dict = {}
    prof = profile(root)
    for fw in prof.get("frameworks", []):
        low = fw.lower()
        for prefix, sid in _FW_STACK:
            if low.startswith(prefix):
                ids.add(sid)
                v = first_major(fw)
                if v and sid not in _FW_NO_VERSION:
                    ver[sid] = v
                break
    for lang in prof.get("languages", []):
        low = lang.lower()
        if low.startswith("java "):
            ver["java"] = first_major(lang)
        elif low.startswith("python "):
            ver["python"] = first_major(lang)
    return sorted(f"{sid}@{ver[sid]}" if ver.get(sid) else sid for sid in ids)


# --- rich profile ------------------------------------------------------------
# detect() answers "what type"; profile() answers "what exactly" — the frameworks,
# versions, datastore, build/test tooling and notable libraries written into the
# .cdt/stack/<type>.md so the file is actually filled in, not a blank skeleton.

PROFILE_FIELDS = ("languages", "frameworks", "datastores", "build", "testing",
                  "tooling", "libraries")

# docker-compose / pom image or driver substring -> datastore label.
_DATASTORES = (
    ("pgvector", "PostgreSQL (pgvector)"), ("postgres", "PostgreSQL"),
    ("mariadb", "MariaDB"), ("mysql", "MySQL"), ("mongo", "MongoDB"),
    ("redis", "Redis"), ("minio", "MinIO / S3"), ("keycloak", "Keycloak (auth)"),
    ("elasticsearch", "Elasticsearch"), ("opensearch", "OpenSearch"),
    ("rabbitmq", "RabbitMQ"), ("kafka", "Kafka"), ("cassandra", "Cassandra"),
    ("clickhouse", "ClickHouse"),
)


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig", errors="replace")  # strip a BOM if present
    except OSError:
        return ""


def _clean_ver(v: str) -> str:
    """`^21.2.14` / `~5.9.2` -> `21.2.14`."""
    return re.sub(r"^[\^~>=<\s]+", "", (v or "").strip())


def _major(v: str) -> str:
    m = re.match(r"(\d+)", _clean_ver(v))
    return m.group(1) if m else _clean_ver(v)


def _parse_pom(text: str, prof: Dict[str, List[str]]) -> None:
    pm = re.search(
        r"spring-boot-starter-parent</artifactId>\s*<version>([^<]+)</version>", text)
    if pm:
        prof["frameworks"].append(f"Spring Boot {pm.group(1)}")
    jm = (re.search(r"<java\.version>([^<]+)</java\.version>", text)
          or re.search(r"<maven\.compiler\.(?:source|release)>([^<]+)<", text))
    if jm:
        prof["languages"].append(f"Java {jm.group(1)}")
    arts = set(re.findall(r"<artifactId>([^<]+)</artifactId>", text))

    def art(*subs: str) -> bool:
        return any(any(s in a for s in subs) for a in arts)

    if art("spring-boot-starter-webflux"):
        prof["frameworks"].append("Spring WebFlux")
    elif art("spring-boot-starter-web"):
        prof["frameworks"].append("Spring Web (REST)")
    if art("spring-boot-starter-data-jpa") or art("hibernate"):
        prof["libraries"].append("Spring Data JPA / Hibernate")
    if art("spring-boot-starter-security"):
        prof["libraries"].append("Spring Security")
    if art("spring-boot-starter-validation"):
        prof["libraries"].append("Bean Validation")
    if art("spring-boot-starter-mail"):
        prof["libraries"].append("Spring Mail")
    if art("spring-boot-starter-actuator"):
        prof["libraries"].append("Spring Actuator (observability)")
    if art("springdoc", "swagger"):
        prof["libraries"].append("OpenAPI (springdoc/Swagger)")
    if art("micrometer"):
        prof["libraries"].append("Micrometer (metrics)")
    if art("flyway"):
        prof["libraries"].append("Flyway (migrations)")
    if art("liquibase"):
        prof["libraries"].append("Liquibase (migrations)")
    if art("postgresql"):
        prof["datastores"].append("PostgreSQL")
    if art("mysql-connector", "mariadb"):
        prof["datastores"].append("MySQL/MariaDB")
    if art("spring-boot-starter-data-mongodb"):
        prof["datastores"].append("MongoDB")
    if art("spring-boot-starter-data-redis"):
        prof["datastores"].append("Redis")
    if art("jjwt", "java-jwt"):
        prof["libraries"].append("JWT (jjwt)")
    if art("bucket4j"):
        prof["libraries"].append("Bucket4j (rate limiting)")
    if art("lombok"):
        prof["libraries"].append("Lombok")
    if art("awssdk", "aws-java-sdk") or "s3" in arts:
        prof["libraries"].append("AWS SDK (S3)")
    if art("mapstruct"):
        prof["libraries"].append("MapStruct")
    if art("spring-boot-starter-test"):
        prof["testing"].append("Spring Boot Test (JUnit)")
    if "testcontainers" in text:  # groupId org.testcontainers, not an artifactId
        prof["testing"].append("Testcontainers")
    prof["build"].append("Maven")


def _parse_pkg(pkg: dict, prof: Dict[str, List[str]]) -> None:
    deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
    if "@angular/core" in deps:
        ssr = " (SSR + Express)" if "@angular/ssr" in deps else ""
        prof["frameworks"].append(f"Angular {_major(deps['@angular/core'])}{ssr}")
    if "react" in deps and "react-native" not in deps:
        prof["frameworks"].append(f"React {_major(deps['react'])}")
    if "react-native" in deps:
        prof["frameworks"].append(f"React Native {_major(deps['react-native'])}")
    if "vue" in deps:
        prof["frameworks"].append(f"Vue {_major(deps['vue'])}")
    if "next" in deps:
        prof["frameworks"].append(f"Next.js {_major(deps['next'])}")
    if "svelte" in deps:
        prof["frameworks"].append(f"Svelte {_major(deps['svelte'])}")
    if "@nestjs/core" in deps:
        prof["frameworks"].append(f"NestJS {_major(deps['@nestjs/core'])}")
    elif "express" in deps and not ("@angular/ssr" in deps or "@angular/core" in deps):
        prof["frameworks"].append(f"Express {_major(deps['express'])}")
    elif "fastify" in deps:
        prof["frameworks"].append(f"Fastify {_major(deps['fastify'])}")
    if "vite" in deps:
        prof["build"].append(f"Vite {_major(deps['vite'])}")
    if "typescript" in deps:
        prof["languages"].append(f"TypeScript {_clean_ver(deps['typescript'])}")
    for name, label in (("bootstrap", "Bootstrap"),
                        ("@ng-bootstrap/ng-bootstrap", "ng-bootstrap"),
                        ("@angular/material", "Angular Material"),
                        ("@angular/cdk", "Angular CDK"),
                        ("@angular/localize", "Angular i18n (localize)"),
                        ("tailwindcss", "Tailwind CSS"), ("rxjs", "RxJS"),
                        ("@ngrx/store", "NgRx"), ("redux", "Redux"),
                        ("axios", "Axios"), ("sharp", "sharp (image processing)")):
        if name in deps:
            prof["libraries"].append(label)
    for name, label in (("vitest", "Vitest"), ("jest", "Jest"), ("karma", "Karma"),
                        ("jasmine", "Jasmine"), ("cypress", "Cypress"),
                        ("@playwright/test", "Playwright"), ("playwright", "Playwright")):
        if name in deps:
            prof["testing"].append(label)
    if any(k in deps for k in ("@vitest/coverage-v8", "karma-coverage", "nyc")):
        prof["testing"].append("coverage")
    # tooling: lint / format / library packaging
    if any(k in deps for k in ("eslint", "angular-eslint", "typescript-eslint",
                               "@eslint/js")):
        prof["tooling"].append("ESLint")
    for name, label in (("prettier", "Prettier"), ("stylelint", "Stylelint"),
                        ("ng-packagr", "ng-packagr"), ("husky", "Husky"),
                        ("storybook", "Storybook")):
        if name in deps:
            prof["tooling"].append(label)
    pm = pkg.get("packageManager")
    if pm:
        prof["build"].append(pm.replace("@", " "))
    elif "@angular/cli" in deps:
        prof["build"].append("npm (Angular CLI)")


def _parse_compose(text: str, prof: Dict[str, List[str]]) -> None:
    for img in re.findall(r"image:\s*['\"]?([^\s'\"]+)", text):
        low = img.lower()
        for key, label in _DATASTORES:
            if key in low:
                prof["datastores"].append(label)
                break


def _parse_python(blob: str, prof: Dict[str, List[str]]) -> None:
    rp = re.search(r"requires-python\s*=\s*[\"']([^\"']+)", blob)
    if rp:
        prof["languages"].append(f"Python {rp.group(1)}")
    low = blob.lower()
    for key, label in (("django", "Django"), ("fastapi", "FastAPI"),
                       ("flask", "Flask")):
        if key in low:
            prof["frameworks"].append(label)
    if "pytest" in low:
        prof["testing"].append("pytest")


def profile(root: Path) -> Dict[str, List[str]]:
    """Extracts a filled stack profile from the manifests across the tree.

    Returns a dict with the PROFILE_FIELDS keys, each a deduped list (possibly
    empty). Best-effort and never raises — unknown corners simply stay empty.
    """
    prof: Dict[str, List[str]] = {k: [] for k in PROFILE_FIELDS}
    py_blob = ""
    for r in _search_roots(root):
        if (r / "pom.xml").exists():
            _parse_pom(_read_text(r / "pom.xml"), prof)
        if (r / "build.gradle").exists() or (r / "build.gradle.kts").exists():
            prof["build"].append("Gradle")
        if (r / "package.json").exists():
            pkg = _read_json(r / "package.json")
            if pkg:
                _parse_pkg(pkg, prof)
        for cf in ("docker-compose.yml", "docker-compose.yaml", "compose.yml"):
            if (r / cf).exists():
                _parse_compose(_read_text(r / cf), prof)
                prof["tooling"].append("Docker Compose")
        if (r / "Dockerfile").exists():
            prof["tooling"].append("Docker")
        for pf in ("pyproject.toml", "requirements.txt"):
            if (r / pf).exists():
                py_blob += _read_text(r / pf) + "\n"
        if (r / "go.mod").exists():
            prof["languages"].append("Go")
    if py_blob.strip():
        _parse_python(py_blob, prof)
    return {k: list(dict.fromkeys(v)) for k, v in prof.items()}
