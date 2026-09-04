#!/usr/bin/env python3
"""
PZIP — Printable ZIP
====================
Compress files into a block of printable ASCII you can copy/paste
through any terminal or chat window — no file I/O required.

  Compression : zlib level 9 (DEFLATE)
  Encoding    : Base85  (25% more efficient than Base64)
  Integrity   : CRC-32 per file
  Multi-file  : yes, like a real zip archive

USAGE
-----
  python pzip.py pack   file1.txt file2.py    # compress → stdout
  python pzip.py pack   --text "Hello!"       # compress a string
  echo "hi" | python pzip.py pack -           # compress from stdin pipe
  python pzip.py unpack                       # paste block, then Ctrl+D → files
  python pzip.py unpack -o ./out_dir          # extract to a directory
  python pzip.py info                         # list contents without extracting

BINARY PAYLOAD (before base85 encoding)
----------------------------------------
  Offset  Size  Field
  ------  ----  -----
  0       4     Magic bytes: b'PZIP'
  4       1     Version (uint8)
  5       4     Number of files (uint32 BE)
  -- repeated per file --
  +0      4     Original size (uint32 BE)
  +4      4     CRC-32 of original data (uint32 BE)
  +8      2     Filename length in bytes (uint16 BE)
  +10     N     Filename (UTF-8)
  +10+N   4     Compressed size (uint32 BE)
  +14+N   M     zlib-compressed data (level 9)
"""

import zlib
import base64
import struct
import sys
import argparse
import textwrap
from pathlib import Path
from typing import List, Tuple

# ── Constants ─────────────────────────────────────────────────────────────────

MAGIC        = b'PZIP'
VERSION      = 1
LINE_WIDTH   = 76                          # chars per line (PEM uses 64, we use 76)
BEGIN_MARKER = '--- BEGIN PZIP ARCHIVE ---'
END_MARKER   = '--- END PZIP ARCHIVE ---'


# ── Core: pack ────────────────────────────────────────────────────────────────

def pack_files(files: List[Tuple[str, bytes]]) -> str:
    """
    Compress a list of (filename, raw_bytes) pairs into a PZIP string.

    Returns a printable ASCII block ready to copy/paste anywhere.
    """
    parts = [MAGIC, struct.pack('>BI', VERSION, len(files))]

    for name, data in files:
        name_b     = name.encode('utf-8')
        crc        = zlib.crc32(data) & 0xFFFFFFFF
        compressed = zlib.compress(data, level=9)

        parts.append(struct.pack('>IIH', len(data), crc, len(name_b)))
        parts.append(name_b)
        parts.append(struct.pack('>I', len(compressed)))
        parts.append(compressed)

    payload = b''.join(parts)
    encoded = base64.b85encode(payload).decode('ascii')

    # Wrap at LINE_WIDTH for readable terminal output
    lines = [encoded[i:i + LINE_WIDTH] for i in range(0, len(encoded), LINE_WIDTH)]

    return f'{BEGIN_MARKER}\n' + '\n'.join(lines) + f'\n{END_MARKER}'


# ── Core: unpack ──────────────────────────────────────────────────────────────

def unpack_string(pzip_str: str) -> List[Tuple[str, bytes]]:
    """
    Decompress a PZIP string back to a list of (filename, raw_bytes) pairs.

    Tolerant of surrounding text — only the block between markers is parsed.

    Raises ValueError on format errors or data corruption.
    """
    lines = pzip_str.splitlines()

    # Locate markers (ignore surrounding noise)
    start = end = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped == BEGIN_MARKER:
            start = i
        elif stripped == END_MARKER and start is not None:
            end = i
            break

    if start is None or end is None:
        raise ValueError(
            'PZIP markers not found.\n'
            f'Expected: "{BEGIN_MARKER}" ... "{END_MARKER}"'
        )

    # Decode base85 payload
    encoded = ''.join(
        line.strip()                        # ← kills \r, leading/trailing spaces
        for line in lines[start + 1 : end]
        if line.strip()                     # ← skip blank lines entirely
    )

    try:
        payload = base64.b85decode(encoded)
    except Exception as e:
        raise ValueError(f'Base85 decode failed: {e}') from e

    # Validate magic + version
    if len(payload) < 9:
        raise ValueError('Payload too short — truncated data?')
    if payload[:4] != MAGIC:
        raise ValueError(f'Bad magic bytes: {payload[:4]!r} (expected {MAGIC!r})')

    version, num_files = struct.unpack('>BI', payload[4:9])
    if version != VERSION:
        raise ValueError(f'Unsupported PZIP version: {version} (this tool supports v{VERSION})')

    # Parse each file entry
    pos   = 9
    files = []

    for idx in range(num_files):
        if pos + 10 > len(payload):
            raise ValueError(f'Truncated header at file #{idx + 1}')

        orig_size, crc, name_len = struct.unpack('>IIH', payload[pos:pos + 10])
        pos += 10

        name  = payload[pos:pos + name_len].decode('utf-8')
        pos  += name_len

        comp_size = struct.unpack('>I', payload[pos:pos + 4])[0]
        pos += 4

        try:
            data = zlib.decompress(payload[pos:pos + comp_size])
        except zlib.error as e:
            raise ValueError(f'[{name}] zlib decompress failed: {e}') from e
        pos += comp_size

        # Integrity checks
        if len(data) != orig_size:
            raise ValueError(
                f'[{name}] Size mismatch: expected {orig_size:,} B, got {len(data):,} B'
            )
        actual_crc = zlib.crc32(data) & 0xFFFFFFFF
        if actual_crc != crc:
            raise ValueError(
                f'[{name}] CRC-32 mismatch (expected {crc:#010x}, got {actual_crc:#010x})'
                ' — data was corrupted during copy/paste'
            )

        files.append((name, data))

    return files


# ── Convenience wrappers ──────────────────────────────────────────────────────

def compress_text(text: str, name: str = 'text.txt') -> str:
    """Compress a plain string → PZIP block. Convenience wrapper."""
    return pack_files([(name, text.encode('utf-8'))])


def decompress_text(pzip_str: str) -> str:
    """Decompress the first file in a PZIP block → string. Convenience wrapper."""
    files = unpack_string(pzip_str)
    if not files:
        raise ValueError('Archive is empty')
    return files[0][1].decode('utf-8')


def archive_info(pzip_str: str) -> str:
    """Return a human-readable table of archive contents."""
    files = unpack_string(pzip_str)
    col   = 42
    sep   = '  ' + '-' * (col + 16)
    rows  = [
        f'PZIP Archive — {len(files)} file(s)',
        '',
        f'  {"Filename":<{col}} {"Orig Size":>12}',
        sep,
    ]
    total = 0
    for name, data in files:
        rows.append(f'  {name:<{col}} {len(data):>10,} B')
        total += len(data)
    rows += [sep, f'  {"TOTAL":<{col}} {total:>10,} B', '']
    return '\n'.join(rows)

# ── CLI helpers ───────────────────────────────────────────────────────────────

def collect_files(path: Path, base: Path = None) -> List[Tuple[str, bytes]]:
    """
    Recursively collect all files under a directory.
    Filenames are stored as relative paths (e.g. 'src/main.py')
    so the directory structure is preserved on unpack.
    """

    if base is None:
        base = path.parent  # store paths relative to the folder's parent

    file_list = []
    for entry in sorted(path.rglob('*')):  # sorted for deterministic order
        if entry.is_file():
            rel_name = entry.relative_to(base).as_posix()  # forward slashes always
            file_list.append((rel_name, entry.read_bytes()))

    return file_list

def cmd_pack(args):
    file_list: List[Tuple[str, bytes]] = []

    for path in (args.files or []):
        if path == '-':
            file_list.append(('stdin', sys.stdin.buffer.read()))
        else:
            p = Path(path)
            if not p.exists():
                sys.exit(f'Error: path not found: {path}')
            if p.is_dir():
                collected = collect_files(p)
                if not collected:
                    sys.exit(f'Error: directory is empty: {path}')
                file_list.extend(collected)
            else:
                file_list.append((p.name, p.read_bytes()))

    if args.text:
        file_list.append(('text.txt', args.text.encode('utf-8')))

    if not file_list:
        sys.exit('Error: no input. Specify files/folders, use - for stdin, or --text "..."')

    result     = pack_files(file_list)
    total_orig = sum(len(d) for _, d in file_list)
    total_enc  = len(result)

    print(result)

    print(
        f'\n[PZIP] {len(file_list)} file(s) packed\n'
        f'       original : {_size_str(total_orig)} ({total_orig:,} bytes)\n'
        f'       encoded  : {_size_str(total_enc)} ({total_enc:,} chars)\n'
        f'       ratio    : {total_enc / max(total_orig, 1):.1%} of original',
        file=sys.stderr,
    )


def _size_str(n: int) -> str:
    for unit in ('B', 'KB', 'MB', 'GB'):
        if n < 1024:
            return f'{n:.1f} {unit}' if unit != 'B' else f'{n} B'
        n /= 1024
    return f'{n:.1f} TB'


def cmd_unpack(args):
    print('[PZIP] Paste your PZIP block below, then press Ctrl+D (Unix) or Ctrl+Z Enter (Windows):',
          file=sys.stderr)
    pzip_str = sys.stdin.read()

    try:
        files = unpack_string(pzip_str)
    except ValueError as e:
        sys.exit(f'Error: {e}')

    out_dir = Path(args.output or '.')
    out_dir.mkdir(parents=True, exist_ok=True)

    for name, data in files:
        dest = out_dir / name
        dest.parent.mkdir(parents=True, exist_ok=True)  # ← create subdirs as needed
        dest.write_bytes(data)
        print(f'  extracted: {dest}  ({_size_str(len(data))})')

    print(f'\n[PZIP] {len(files)} file(s) extracted to {out_dir.resolve()}', file=sys.stderr)


def cmd_info(args):
    print('[PZIP] Paste your PZIP block below, then Ctrl+D / Ctrl+Z Enter:',
          file=sys.stderr)
    try:
        print(archive_info(sys.stdin.read()))
    except ValueError as e:
        sys.exit(f'Error: {e}')


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog='pzip',
        description='PZIP — Printable ZIP: copy-paste friendly compression',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent('''\
            Examples:
              python pzip.py pack script.py config.json
              python pzip.py pack --text "Hello, World!"
              echo "some data" | python pzip.py pack -
              python pzip.py unpack
              python pzip.py unpack -o ./restored
              python pzip.py info
        '''),
    )
    sub = parser.add_subparsers(dest='command', required=True)

    # pack
    pk = sub.add_parser('pack', help='Compress files → PZIP string on stdout')
    pk.add_argument('files', nargs='*', metavar='FILE',
                    help='Files to compress (use - for stdin)')
    pk.add_argument('--text', '-t', metavar='TEXT',
                    help='Compress a text string directly')
    pk.set_defaults(func=cmd_pack)

    # unpack
    up = sub.add_parser('unpack', help='Decompress PZIP from stdin → files')
    up.add_argument('-o', '--output', metavar='DIR',
                    help='Output directory (default: current dir)')
    up.set_defaults(func=cmd_unpack)

    # info
    inf = sub.add_parser('info', help='List archive contents without extracting')
    inf.set_defaults(func=cmd_info)

    args = parser.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
