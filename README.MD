# PZIP — Printable ZIP
> Compress files and text into a block of printable ASCII you can copy and paste
> through any terminal, chat window, or text editor — no file I/O required.
---
## Why PZIP?
Sometimes you need to transfer data between machines or windows without access to
`scp`, shared drives, or file attachments — just a terminal or a text box. PZIP
solves this by turning any file or string into a self-contained, copy-pasteable
ASCII block that decompresses back to the original, byte-for-byte.
**No dependencies. Pure Python stdlib.**
---
## How It Works
| Layer       | Tool          | Detail                                      |
|-------------|---------------|---------------------------------------------|
| Compression | LZMA, Bzip2, or DEFLATE | Selects the smallest level-9 stdlib result |
| Encoding    | Base85        | 25% more efficient than Base64              |
| Framing     | PEM-style     | Clear begin/end markers, easy to parse      |
| Integrity   | CRC-32        | Per-file checksum catches paste corruption  |
A PZIP block looks like this:
--- BEGIN PZIP ARCHIVE ---
Wj%{Ld0%Xd0ssI0{{R30RRC20|NsC0|NsC0|NsC0|NsC0|NsC0|NsC0|NsC0|NsC0|NsC
Wj%{Ld0%Xd0ssI0{{R30RRC20|NsC0|NsC0|NsC0|NsC0|NsC0|NsC0|NsC0|NsC0|NsC
...
--- END PZIP ARCHIVE ---


---

## Requirements

- Python 3.6+
- No third-party packages — uses `lzma`, `bz2`, `zlib`, `base64`, `struct`, and `argparse` from stdlib

---

## Installation

No installation needed. Just download the single file:

```bash
curl -O https://your-repo-url/pzip.py
# or simply copy pzip.py into your working directory
Optionally make it executable:

bash
chmod +x pzip.py
Usage
Pack (compress → printable block)
bash
# Compress one or more files — block is printed to stdout
python pzip.py pack script.py config.json

# Compress a string directly
python pzip.py pack --text "Hello, World!"

# Compress from stdin (pipe)
echo "some data" | python pzip.py pack -

# Save the block to a file (optional — defeats the purpose, but valid)
python pzip.py pack report.csv > report.pzip.txt
Unpack (paste block → files)
bash
# Paste your PZIP block, then press Ctrl+D (Unix) or Ctrl+Z + Enter (Windows)
python pzip.py unpack

# Extract to a specific directory
python pzip.py unpack -o ./restored
Info (inspect without extracting)
bash
python pzip.py info
# Paste block → shows filenames and sizes
Example Session
Machine A — packing:

$ python pzip.py pack notes.txt
--- BEGIN PZIP ARCHIVE ---
Wj%{Ld0%Xd0ssI0{{R30RRC20|NsC0|NsC...
--- END PZIP ARCHIVE ---

[PZIP] 1 file(s) packed
       original : 2.1 KB (2,130 bytes)
       encoded  : 1.3 KB (1,298 chars)
       ratio    : 61.0% of original
Machine B — unpacking:

$ python pzip.py unpack -o ./out
[PZIP] Paste your PZIP block below, then press Ctrl+D:
--- BEGIN PZIP ARCHIVE ---
Wj%{Ld0%Xd0ssI0{{R30RRC20|NsC0|NsC...
--- END PZIP ARCHIVE ---
^D
  extracted: out/notes.txt  (2.1 KB)

[PZIP] 1 file(s) extracted to /home/user/out

# Pack a whole folder
python pzip.py pack my_project/

# Mix files and folders
python pzip.py pack main.py tests/ config.json

# Unpack restores the full tree
python pzip.py unpack -o ./restored
# → restored/my_project/src/main.py
# → restored/my_project/README.md
# → etc.


Compression Ratios
Input type	Approx. encoded size vs. original
Source code / JSON	~45–55%
Plain English text	~50–60%
Already-compressed (JPEG, ZIP)	~130% (slight expansion)
PZIP shines on text, code, CSV, and structured data. It is not intended for
binary formats that are already compressed.

Binary Payload Format
For those who want to implement their own encoder/decoder, the binary structure
before Base85 encoding is:

Offset  Size  Field
------  ----  -----
0       4     Magic bytes: b'PZIP'
4       1     Version (uint8, currently 2)
5       1     Compression codec (0=zlib, 1=bz2, 2=lzma)
6       M     Compressed archive data

The archive data begins with the number of files (uint32 BE), then repeats:

Offset  Size  Field
------  ----  -----
+0      4     Original size (uint32 BE)
+4      4     CRC-32 of original data (uint32 BE)
+8      2     Filename length in bytes (uint16 BE)
+10     N     Filename (UTF-8)
+10+N   M     Original data

PZIP chooses the smallest compressed archive from LZMA (preset 9 extreme),
Bzip2 (level 9), and DEFLATE (level 9). Compressing the complete archive also
captures repetition across files. The resulting payload is Base85-encoded, so
every payload character remains printable ASCII. Version 1 archives remain
readable.
Python API
PZIP can also be used as a library:

python
from pzip import pack_files, unpack_string, compress_text, decompress_text

# Compress files
block = pack_files([
    ("hello.txt", b"Hello, World!"),
    ("data.json", b'{"key": "value"}'),
])

# Decompress
files = unpack_string(block)
for name, data in files:
    print(name, data)

# Convenience wrappers for plain text
block = compress_text("Hello!")
text  = decompress_text(block)
Error Handling
PZIP validates integrity on unpack and gives clear errors:

Situation	Error message
Markers not found in pasted text	PZIP markers not found
Truncated / incomplete paste	Payload too short — truncated data?
Single character corrupted	CRC-32 mismatch — data was corrupted during copy/paste
Wrong version	Unsupported PZIP version: X
Limitations
Not a replacement for ZIP/tar — designed for copy-paste transfer, not archival storage.
Max practical size — works well up to a few MB. Very large files produce blocks too long to paste comfortably in most terminals.
Binary files — supported, but already-compressed formats (JPEG, MP4, ZIP) will expand slightly.
Filename sanitization — PZIP preserves filenames as-is; be cautious with path traversal if extracting untrusted archives.
Contributing
Bug reports and pull requests are welcome. Please open an issue first to discuss
significant changes. Keep PRs focused — one fix or feature per PR.
