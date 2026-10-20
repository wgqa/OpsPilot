from pathlib import Path
import hashlib
manifest = Path('docs/evidence/vnext/m3-01-hf-01/FROZEN_SHA256SUMS.txt')
checked = 0
mismatches = []
for line in manifest.read_text(encoding='utf-8').splitlines():
    if not line.strip():
        continue
    expected, rel = line.split(None, 1)
    target = Path(rel.strip())
    actual = hashlib.sha256(target.read_bytes()).hexdigest()
    checked += 1
    if actual != expected:
        mismatches.append({'path': str(target), 'expected': expected, 'actual': actual})
print({'checked': checked, 'mismatch_count': len(mismatches), 'mismatches': mismatches})
raise SystemExit(1 if mismatches else 0)
