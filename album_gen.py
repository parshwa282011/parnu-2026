#!/usr/bin/env python3
"""Generate an album.json manifest for event album files."""

from __future__ import annotations

import argparse
import json
import mimetypes
import platform
import shutil
import subprocess
from pathlib import Path
from urllib.parse import quote


IMAGE_EXTENSIONS = {
    ".avif",
    ".bmp",
    ".gif",
    ".jpeg",
    ".jpg",
    ".png",
    ".svg",
    ".webp",
}

VIDEO_EXTENSIONS = {
    ".m4v",
    ".mov",
    ".mp4",
    ".ogg",
    ".ogv",
    ".webm",
}


def conversion_command(input_path: Path, output_path: Path) -> list[str] | None:
    system = platform.system().lower()

    if system == "darwin":
        sips = shutil.which("sips")
        if sips:
            return [sips, "-s", "format", "jpeg", str(input_path), "--out", str(output_path)]
        raise SystemExit("Could not find macOS 'sips' for HEIC conversion.")

    if system == "linux":
        magick = shutil.which("magick")
        if magick:
            return [magick, str(input_path), str(output_path)]

        convert = shutil.which("convert")
        if convert:
            return [convert, str(input_path), str(output_path)]

        heif_convert = shutil.which("heif-convert")
        if heif_convert:
            return [heif_convert, str(input_path), str(output_path)]

        return None

    raise SystemExit(
        f"HEIC conversion is not configured for {platform.system()}. "
        "Use --skip-heic-conversion or convert HEIC files manually."
    )

def convert_heic_files(directory: Path, remove_originals: bool) -> int:
    converted = 0
    for path in sorted(directory.rglob("*")):
        if not path.is_file() or path.suffix.lower() != ".heic":
            continue

        output_path = path.with_suffix(".jpg")
        if output_path.exists():
            stem = path.stem
            index = 2
            while output_path.exists():
                output_path = path.with_name(f"{stem}-{index}.jpg")
                index += 1

        command = conversion_command(path, output_path)
        if command:
            subprocess.run(
                command,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
            )
        else:
            convert_heic_with_python(path, output_path)
        converted += 1

        if remove_originals:
            path.unlink()

    return converted


def convert_heic_with_python(input_path: Path, output_path: Path) -> None:
    try:
        from PIL import Image
        from pillow_heif import register_heif_opener
    except ImportError as error:
        raise SystemExit(
            "Could not find a HEIC converter. On Linux, either install ImageMagick/heif-convert "
            "or run: python3 -m pip install Pillow pillow-heif"
        ) from error

    register_heif_opener()
    with Image.open(input_path) as image:
        image.convert("RGB").save(output_path, "JPEG", quality=95)


def media_type_for(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in IMAGE_EXTENSIONS:
        return "image"
    if suffix in VIDEO_EXTENSIONS:
        return "video"
    return "file"


def url_for(relative_path: Path) -> str:
    return "/".join(quote(part) for part in relative_path.parts)


def build_manifest(directory: Path, output_name: str) -> dict:
    files = []
    for path in sorted(directory.rglob("*")):
        if not path.is_file():
            continue
        relative_path = path.relative_to(directory)
        if relative_path.name == output_name:
            continue
        mime_type, _ = mimetypes.guess_type(path.name)
        files.append(
            {
                "name": path.name,
                "url": url_for(relative_path),
                "mediaType": media_type_for(path),
                "mimeType": mime_type or "application/octet-stream",
                "size": path.stat().st_size,
            }
        )

    return {"files": files}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate album.json from every file inside a directory."
    )
    parser.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="Album directory to scan. Defaults to the current directory.",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="album.json",
        help="Output JSON filename or path. Defaults to album.json in the album directory.",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Write indented JSON. Compact JSON is used by default.",
    )
    parser.add_argument(
        "--keep-heic",
        action="store_true",
        help="Convert HEIC files to JPG but keep the original HEIC files.",
    )
    parser.add_argument(
        "--skip-heic-conversion",
        action="store_true",
        help="Do not convert HEIC files before generating the manifest.",
    )
    args = parser.parse_args()

    directory = Path(args.directory).expanduser().resolve()
    if not directory.is_dir():
        raise SystemExit(f"Not a directory: {directory}")

    converted = 0
    if not args.skip_heic_conversion:
        converted = convert_heic_files(directory, remove_originals=not args.keep_heic)

    output_path = Path(args.output).expanduser()
    if not output_path.is_absolute():
        output_path = directory / output_path

    manifest = build_manifest(directory, output_path.name)
    output_path.write_text(
        json.dumps(manifest, indent=2 if args.pretty else None) + "\n",
        encoding="utf-8",
    )
    print(
        f"Wrote {output_path} with {len(manifest['files'])} files. "
        f"Converted {converted} HEIC files."
    )


if __name__ == "__main__":
    main()