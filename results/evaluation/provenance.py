"""Store settings and hashes alongside independent analysis results."""
from pathlib import Path
from dataclasses import asdict
import hashlib,json

def write_provenance(input_path,out,cfg):
    input_path=Path(input_path)
    info={'input_name':input_path.name,
          'input_sha256':hashlib.sha256(input_path.read_bytes()).hexdigest(),
          'settings':asdict(cfg)}
    Path(out,'analysis_settings.json').write_text(json.dumps(info,indent=2,
        default=lambda v:sorted(v) if isinstance(v,set) else str(v)))
