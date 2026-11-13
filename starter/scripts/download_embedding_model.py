"""Download the pinned public embedding model; never upload corpus text."""
import argparse
import hashlib
import json
from pathlib import Path
import time

import requests

ROOT = Path(__file__).resolve().parents[2]
MODEL = "intfloat/multilingual-e5-small"
REVISION = "614241f622f53c4eeff9890bdc4f31cfecc418b3"
FILES = {"config.json", "model.safetensors", "modules.json", "sentence_bert_config.json",
         "sentencepiece.bpe.model", "special_tokens_map.json", "tokenizer.json",
         "tokenizer_config.json", "1_Pooling/config.json", "README.md"}


def hashes(path):
    sha256, git = hashlib.sha256(), hashlib.sha1()
    git.update(f"blob {path.stat().st_size}\0".encode())
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            sha256.update(block)
            git.update(block)
    return sha256.hexdigest(), git.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--direct", action="store_true", help="Connect directly instead of environment proxy settings")
    args = parser.parse_args()
    session = requests.Session()
    session.trust_env = not args.direct
    # Anonymous public download; no Hugging Face token or API key is read.
    response = session.get(f"https://huggingface.co/api/models/{MODEL}/revision/{REVISION}?blobs=true", timeout=60)
    response.raise_for_status()
    metadata = response.json()
    if metadata["sha"] != REVISION:
        raise ValueError("Unexpected model revision")
    entries = {entry["rfilename"]: entry for entry in metadata["siblings"]}
    missing = FILES - entries.keys()
    if missing:
        raise ValueError(f"Missing required model files: {sorted(missing)}")
    folder = ROOT / "models/multilingual-e5-small"
    folder.mkdir(parents=True, exist_ok=True)
    manifest = {"model_name": MODEL, "revision": REVISION, "files": []}
    started = time.perf_counter()
    for name in sorted(FILES):
        entry = entries[name]
        target = folder / name
        target.parent.mkdir(parents=True, exist_ok=True)
        expected = entry.get("lfs", {}).get("sha256")
        expected_git = entry.get("blobId")

        def verified():
            if not target.is_file() or target.stat().st_size != entry["size"]:
                return False
            sha, git = hashes(target)
            return sha == expected if expected else git == expected_git

        if not verified():
            temporary = target.with_suffix(target.suffix + ".partial")
            print(f"Downloading {name} ({entry['size']:,} bytes)", flush=True)
            with session.get(f"https://huggingface.co/{MODEL}/resolve/{REVISION}/{name}",
                             stream=True, timeout=(30, 180)) as result:
                result.raise_for_status()
                with temporary.open("wb") as handle:
                    for block in result.iter_content(1024 * 1024):
                        handle.write(block)
            temporary.replace(target)
            if not verified():
                raise ValueError(f"Model file integrity check failed: {name}")
        sha, _ = hashes(target)
        manifest["files"].append({"path": name, "bytes": target.stat().st_size, "sha256": sha})
        print(f"Verified {name}", flush=True)
    manifest["download_and_verify_seconds"] = round(time.perf_counter() - started, 6)
    (folder / "download_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Ready: {MODEL}@{REVISION} -> {folder}", flush=True)


if __name__ == "__main__":
    main()
