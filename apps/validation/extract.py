"""Defensive extraction of uploaded eCTD zip packages.

Rejects path traversal ("zip slip"), absolute paths, symlinks, encrypted
members and zip bombs (the byte budget is enforced on the actual bytes
written, not on the sizes the archive claims).
"""
import re
import stat
import zipfile
from pathlib import Path

JUNK_PREFIXES = ("__MACOSX/",)
JUNK_NAMES = {".DS_Store", "Thumbs.db", "desktop.ini"}
CHUNK = 1024 * 1024


class ArchiveError(Exception):
    pass


def safe_extract(zip_path, dest: Path, *, max_total_bytes: int, max_files: int) -> int:
    """Extract ``zip_path`` into ``dest``. Returns the number of files written."""
    try:
        archive = zipfile.ZipFile(zip_path)
    except (zipfile.BadZipFile, OSError) as exc:
        raise ArchiveError(f"The file is not a valid ZIP archive ({exc}).") from exc

    dest.mkdir(parents=True, exist_ok=True)
    root = dest.resolve()
    written_bytes = 0
    written_files = 0

    with archive:
        members = archive.infolist()
        file_members = [m for m in members if not m.is_dir()]
        if not file_members:
            raise ArchiveError("The ZIP archive is empty.")
        if len(file_members) > max_files:
            raise ArchiveError(f"The archive contains {len(file_members)} files; the limit is {max_files}.")
        if sum(m.file_size for m in members) > max_total_bytes:
            raise ArchiveError("The archive exceeds the maximum allowed uncompressed size.")

        for member in members:
            name = member.filename.replace("\\", "/")
            if name.startswith(JUNK_PREFIXES) or name.rsplit("/", 1)[-1] in JUNK_NAMES:
                continue
            if name.startswith("/") or re.match(r"^[A-Za-z]:", name) or ".." in name.split("/"):
                raise ArchiveError(f"Unsafe path in archive: {member.filename}")
            if ":" in name:
                raise ArchiveError(f"Invalid character in archive path: {member.filename}")
            if stat.S_ISLNK(member.external_attr >> 16):
                raise ArchiveError(f"Symbolic links are not allowed: {member.filename}")
            if member.flag_bits & 0x1:
                raise ArchiveError("Password-protected (encrypted) ZIP archives are not accepted.")

            target = (dest / name).resolve()
            if not target.is_relative_to(root):
                raise ArchiveError(f"Unsafe path in archive: {member.filename}")
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue

            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                with archive.open(member) as src, open(target, "wb") as out:
                    while chunk := src.read(CHUNK):
                        written_bytes += len(chunk)
                        if written_bytes > max_total_bytes:
                            raise ArchiveError("The archive exceeds the maximum allowed uncompressed size.")
                        out.write(chunk)
            except (zipfile.BadZipFile, zipfile.LargeZipFile, OSError, EOFError) as exc:
                raise ArchiveError(f"Could not extract {member.filename}: {exc}") from exc
            written_files += 1

    return written_files
