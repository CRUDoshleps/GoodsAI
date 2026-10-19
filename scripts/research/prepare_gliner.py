"""Explicit preparation for experimental_gliner; never called from inference."""
import argparse
import json
import os
from pathlib import Path

from goodsai.experimental_gliner import CHECKPOINT, ENCODER, file_hash, validate_artifact


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    root = Path(args.output).resolve()
    root.mkdir(parents=True, exist_ok=False)
    os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
    os.environ['HF_HUB_DISABLE_XET'] = '1'
    from huggingface_hub import snapshot_download
    specs = [
        ('urchade/gliner_multi-v2.1', CHECKPOINT, 'gliner',
         ['gliner_config.json', 'model.safetensors', 'README.md']),
        ('microsoft/mdeberta-v3-base', ENCODER, 'encoder',
         ['config.json', 'tokenizer_config.json', 'spm.model', 'README.md']),
    ]
    for repo, revision, name, patterns in specs:
        snapshot_download(repo, revision=revision, local_dir=root/name,
                          allow_patterns=patterns, max_workers=2)
    config_path = root/'gliner/gliner_config.json'
    original = config_path.read_text()
    (root/'gliner/original_gliner_config.json').write_text(original)
    config = json.loads(original)
    config['model_name'] = str(root/'encoder')
    config_path.write_text(json.dumps(config, indent=2)+'\n')
    names = ['gliner/gliner_config.json', 'gliner/model.safetensors',
             'encoder/config.json', 'encoder/tokenizer_config.json', 'encoder/spm.model']
    manifest = {'checkpoint_revision':CHECKPOINT, 'encoder_revision':ENCODER,
                'licenses':{'gliner':'Apache-2.0', 'encoder':'MIT'},
                'sha256':{name:file_hash(root/name) for name in names}}
    (root/'artifact.json').write_text(json.dumps(manifest, indent=2)+'\n')
    validate_artifact(root)
    print('Prepared pinned local artifact. Preserve its absolute path; moving it requires re-preparation.')


if __name__ == '__main__':
    main()
