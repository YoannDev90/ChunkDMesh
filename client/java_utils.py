import os
import platform
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import httpx

ADOPTIUM_API = "https://api.adoptium.net/v3"

JAVA_MIN_VERSIONS = {
    "1.17": 16,
    "1.18": 17,
    "1.19": 17,
    "1.20": 17,
    "1.21": 21,
    "1.22": 21,
    "1.23": 21,
    "1.24": 21,
}

JAVA_INSTALL_DIR = Path.home() / ".chunkdmesh" / "java"


def _get_os_name() -> str:
    system = platform.system().lower()
    os_names = {
        "linux": "linux",
        "darwin": "mac",
        "windows": "windows",
    }
    if system in os_names:
        return os_names[system]
    raise RuntimeError(f"Unsupported OS: {system}")


def _get_arch() -> str:
    machine = platform.machine().lower()
    if machine in ("x86_64", "amd64"):
        return "x64"
    elif machine in ("aarch64", "arm64"):
        return "aarch64"
    raise RuntimeError(f"Unsupported architecture: {machine}")


def _parse_java_version(version_output: str) -> int | None:
    match = re.search(r'"(\d+)(?:\.\d+)*', version_output)
    if match:
        major = int(match.group(1))
        if major > 8:
            return major
        return major
    return None


def _find_java_in_dir(base: Path) -> Path | None:
    java_bin = base / "bin" / "java"
    if sys.platform == "win32":
        java_bin = base / "bin" / "java.exe"
    if java_bin.exists():
        return java_bin
    return None


def _search_java_in_path() -> Path | None:
    java_path = shutil.which("java")
    if java_path:
        return Path(java_path)
    return None


def _search_java_home() -> Path | None:
    java_home = os.environ.get("JAVA_HOME")
    if java_home:
        found = _find_java_in_dir(Path(java_home))
        if found:
            return found
    return None


def _search_common_locations() -> list[Path]:
    locations = []
    system = platform.system()

    if system == "Linux":
        locations.extend([
            Path("/usr/lib/jvm"),
            Path("/usr/local/lib/jvm"),
            Path.home() / ".sdkman" / "candidates" / "java",
        ])
    elif system == "Darwin":
        locations.extend([
            Path("/Library/Java/JavaVirtualMachines"),
            Path.home() / ".sdkman" / "candidates" / "java",
        ])
    elif system == "Windows":
        program_files = os.environ.get("ProgramFiles", "C:\\Program Files")  # noqa: SIM112
        program_files_x86 = os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")  # noqa: SIM112
        locations.extend([
            Path(program_files) / "Java",
            Path(program_files_x86) / "Java",
            Path.home() / ".sdkman" / "candidates" / "java",
        ])

    found = []
    for base in locations:
        if not base.exists():
            continue
        for child in base.iterdir():
            if child.is_dir():
                java_bin = _find_java_in_dir(child)
                if java_bin:
                    found.append(java_bin)
    return found


def find_java() -> Path | None:
    candidates = []

    path_java = _search_java_in_path()
    if path_java:
        candidates.append(path_java)

    home_java = _search_java_home()
    if home_java:
        candidates.append(home_java)

    candidates.extend(_search_common_locations())

    for java_bin in candidates:
        try:
            result = subprocess.run(
                [str(java_bin), "-version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            version_output = result.stderr or result.stdout
            version = _parse_java_version(version_output)
            if version:
                return java_bin.parent.parent
        except (subprocess.TimeoutExpired, OSError):
            continue

    return None


def get_java_version(java_path: Path) -> int | None:
    java_bin = java_path / "bin" / "java"
    if sys.platform == "win32":
        java_bin = java_path / "bin" / "java.exe"

    try:
        result = subprocess.run(
            [str(java_bin), "-version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        version_output = result.stderr or result.stdout
        return _parse_java_version(version_output)
    except (subprocess.TimeoutExpired, OSError):
        return None


def required_java_version(mc_version: str) -> int:
    mc_major_minor = ".".join(mc_version.split(".")[:2])
    return JAVA_MIN_VERSIONS.get(mc_major_minor, 17)


def is_java_compatible(java_path: Path, mc_version: str) -> bool:
    version = get_java_version(java_path)
    if version is None:
        return False
    required = required_java_version(mc_version)
    return version >= required


def _fetch_download_url(mc_version: str) -> str:
    os_name = _get_os_name()
    arch = _get_arch()
    java_version = required_java_version(mc_version)

    url = (
        f"{ADOPTIUM_API}/assets/latest/{java_version}/hotspot"
        f"?architecture={arch}&os={os_name}&image_type=jdk"
    )
    resp = httpx.get(url, follow_redirects=True, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    if not data:
        raise RuntimeError("No assets found in Adoptium response")
    binary = data[0].get("binary", {})
    pkg = binary.get("package", {})
    download_url = pkg.get("link")
    if not download_url:
        raise RuntimeError("No download URL found in Adoptium response")
    return download_url


def download_java(mc_version: str, dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    url = _fetch_download_url(mc_version)
    filename = url.split("/")[-1]
    archive_path = dest / filename

    print(f"Downloading OpenJDK from {url}...")
    with httpx.stream("GET", url, follow_redirects=True, timeout=300) as resp:
        resp.raise_for_status()
        with open(archive_path, "wb") as f:
            for chunk in resp.iter_bytes(chunk_size=1024 * 64):
                f.write(chunk)
    print(f"Downloaded to {archive_path}")

    print("Extracting...")
    if archive_path.suffix == ".zip":
        with zipfile.ZipFile(archive_path, "r") as zf:
            zf.extractall(dest)
    elif archive_path.suffix == ".gz" or filename.endswith(".tar.gz"):
        import tarfile
        import tempfile
        with tempfile.TemporaryDirectory(dir=dest) as tmp:
            with tarfile.open(archive_path, "r:gz") as tf:
                tf.extractall(tmp)
            extracted = Path(tmp)
            children = list(extracted.iterdir())
            for item in children:
                target = dest / item.name
                if target.exists():
                    for p in target.rglob("*"):
                        if p.is_file():
                            p.chmod(p.stat().st_mode | 0o200)
                    shutil.rmtree(target)
                shutil.move(str(extracted / item.name), str(target))

    archive_path.unlink()

    extracted_dirs = [d for d in dest.iterdir() if d.is_dir()]
    if extracted_dirs:
        return extracted_dirs[0]
    return dest


def ensure_java(mc_version: str) -> Path:
    existing = find_java()
    if existing and is_java_compatible(existing, mc_version):
        print(f"Using existing Java: {existing}")
        return existing

    if existing:
        print(f"Found Java {get_java_version(existing)} but need {required_java_version(mc_version)}+")

    version = required_java_version(mc_version)
    java_dir = JAVA_INSTALL_DIR / f"jdk-{version}"

    if java_dir.exists():
        for d in java_dir.iterdir():
            if d.is_dir() and is_java_compatible(d, mc_version):
                print(f"Using cached Java: {d}")
                return d

    java_home = download_java(mc_version, java_dir)

    if not is_java_compatible(java_home, mc_version):
        raise RuntimeError(f"Downloaded Java is not compatible with MC {mc_version}")

    return java_home
