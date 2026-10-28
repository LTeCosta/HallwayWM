#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
npm --prefix "$project_root" run build
python3 - "$project_root" <<'PY'
from pathlib import Path
import sys
from zipfile import ZIP_DEFLATED, ZipFile

root = Path(sys.argv[1])
archive = root / "temp/hallwaywm.zip"
archive.parent.mkdir(exist_ok=True)
with ZipFile(archive, "w", compression=ZIP_DEFLATED) as output:
    for source in sorted((root / "dist").rglob("*")):
        if source.is_file():
            output.write(source, source.relative_to(root / "dist"))
    output.write(root / "README.md", "README.md")
print("Created " + str(archive))
PY
