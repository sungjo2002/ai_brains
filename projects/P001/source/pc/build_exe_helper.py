from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

DISPLAY_NAME = "스마트인력관리365"
INTERNAL_BUILD_NAME = "smart_workforce365_build"
LOG_FILE = "build_log.txt"

ROOT = Path(__file__).resolve().parent
LOG_PATH = ROOT / LOG_FILE


def log(message: str = "") -> None:
    print(message, flush=True)
    try:
        with LOG_PATH.open("a", encoding="utf-8", errors="replace") as f:
            f.write(message + "\n")
    except PermissionError:
        print("[WARN] build_log.txt is locked; continuing without file log for this line.")


def run_command(args: list[str], title: str) -> None:
    log("")
    log(f"[INFO] {title}")
    log("[CMD] " + " ".join(str(x) for x in args))
    with LOG_PATH.open("a", encoding="utf-8", errors="replace") as f:
        process = subprocess.Popen(
            args,
            cwd=str(ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert process.stdout is not None
        for line in process.stdout:
            print(line, end="", flush=True)
            f.write(line)
        code = process.wait()
    if code != 0:
        raise RuntimeError(f"{title} failed with exit code {code}")


def remove_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
        log(f"[CLEAN] removed folder: {path.name}")
    elif path.exists():
        path.unlink()
        log(f"[CLEAN] removed file: {path.name}")


def clean_old_outputs() -> None:
    log("[INFO] Cleaning old build folders...")
    for name in ["build", "dist", "release", ".pyinstaller_cache"]:
        remove_path(ROOT / name)
    for spec_name in [
        f"{INTERNAL_BUILD_NAME}.spec",
        "workforce_pc_main.spec",
        f"{DISPLAY_NAME}.spec",
    ]:
        remove_path(ROOT / spec_name)


def ensure_required_files() -> None:
    required = [
        ROOT / "main.py",
        ROOT / "requirements.txt",
        ROOT / "app.manifest",
        ROOT / "assets" / "app_icon.ico",
        ROOT / "assets",
        ROOT / "tesseract",
    ]
    missing = [str(p.relative_to(ROOT)) for p in required if not p.exists()]
    if missing:
        raise FileNotFoundError("Missing required files: " + ", ".join(missing))


def build() -> None:
    LOG_PATH.write_text("", encoding="utf-8")
    log("[INFO] 스마트인력관리365 build started")
    log(f"[INFO] Root: {ROOT}")
    log(f"[INFO] Python: {sys.executable}")
    log(f"[INFO] Display name: {DISPLAY_NAME}")

    os.environ["PYINSTALLER_CONFIG_DIR"] = str(ROOT / ".pyinstaller_cache")

    ensure_required_files()
    clean_old_outputs()

    run_command([sys.executable, "-m", "pip", "install", "--upgrade", "pip"], "Upgrade pip")
    run_command([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], "Install requirements")

    try:
        import PyInstaller  # noqa: F401
        log("[INFO] PyInstaller already installed")
    except Exception:
        run_command([sys.executable, "-m", "pip", "install", "pyinstaller"], "Install PyInstaller")

    add_data_sep = ";" if os.name == "nt" else ":"
    pyinstaller_args = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--windowed",
        "--noupx",
        "--name",
        INTERNAL_BUILD_NAME,
        "--icon",
        str(ROOT / "assets" / "app_icon.ico"),
        "--manifest",
        str(ROOT / "app.manifest"),
        "--add-data",
        f"assets{add_data_sep}assets",
        "--add-data",
        f"tesseract{add_data_sep}tesseract",
        "main.py",
    ]
    run_command(pyinstaller_args, "PyInstaller build")

    src_dir = ROOT / "dist" / INTERNAL_BUILD_NAME
    src_exe = src_dir / f"{INTERNAL_BUILD_NAME}.exe"
    final_dir = ROOT / "dist" / DISPLAY_NAME
    final_exe = final_dir / f"{DISPLAY_NAME}.exe"

    if not src_dir.exists():
        raise FileNotFoundError(f"Build folder not found: {src_dir}")
    if not src_exe.exists():
        raise FileNotFoundError(f"Build EXE not found: {src_exe}")

    if final_dir.exists():
        shutil.rmtree(final_dir)

    renamed_exe = src_dir / f"{DISPLAY_NAME}.exe"
    if renamed_exe.exists():
        renamed_exe.unlink()
    src_exe.rename(renamed_exe)
    src_dir.rename(final_dir)

    if not final_exe.exists():
        raise FileNotFoundError(f"Final EXE not found: {final_exe}")

    log("")
    log("[DONE] Build completed successfully.")
    log(f"[DONE] Final folder: {final_dir}")
    log(f"[DONE] Final EXE: {final_exe}")


def main() -> int:
    try:
        LOG_PATH.unlink(missing_ok=True)
    except PermissionError:
        pass
    try:
        build()
        return 0
    except Exception as exc:
        log("")
        log(f"[ERROR] {exc}")
        log("[ERROR] Build failed. Check build_log.txt.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
