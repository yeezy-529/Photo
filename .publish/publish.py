"""One-time import and publication in the explicitly named GitHub repository."""

import base64
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import urllib.parse
import urllib.request


REPO = "yeezy-529/Photo"
BRANCH = "japanese-edition"
BASE = "6ab99157189f2b9ea79e2404967151d0ba5eb2db"
API = "https://api.github.com"
TOKEN = os.environ["GH_TOKEN"]


def request(method, url, payload=None, binary=False):
    headers = {
        "Authorization": "Bearer " + TOKEN,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "Photo-Japanese-Publisher",
    }
    if payload is not None:
        headers["Content-Type"] = "application/octet-stream" if binary else "application/json"
        if not binary:
            payload = json.dumps(payload, ensure_ascii=False).encode()
    req = urllib.request.Request(url, data=payload, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=300) as response:
        return json.load(response)


def git(*args, env=None):
    return subprocess.check_output(["git", *args], env=env).decode().strip()


def main():
    assert os.environ["GITHUB_REPOSITORY"] == REPO
    assert git("rev-parse", "HEAD") == os.environ["GITHUB_SHA"], "Publication branch advanced unexpectedly"
    root = Path.cwd()
    manifest = json.loads((root / ".publish/manifest.json").read_text())
    assert manifest["source_base"] == BASE
    assert manifest["asset_name"] == "PhotoCraft-日本語版.exe"
    assert manifest["tag"] == "v0.20.1-ja.1"
    temporary = Path(tempfile.mkdtemp(prefix="photo-publication-"))
    patch = temporary / "changes.patch"
    shutil.copyfile(root / ".publish/changes.patch", patch)
    bootstrap = (root / ".github/workflows/publish-japanese.yml").read_bytes()
    asset = temporary / manifest["asset_name"]
    digest = hashlib.sha256()
    total = 0
    with asset.open("wb") as output:
        for part in sorted(manifest["chunks"], key=lambda p: p["index"]):
            assert re.fullmatch("[0-9a-f]{40}", part["sha"])
            assert 0 < part["size"] <= 376832
            blob = request("GET", f"{API}/repos/{REPO}/git/blobs/{part['sha']}")
            content = base64.b64decode(blob["content"])
            assert len(content) == part["size"]
            assert hashlib.sha1(f"blob {len(content)}\0".encode() + content).hexdigest() == part["sha"]
            output.write(content)
            digest.update(content)
            total += len(content)
    assert total == manifest["size"] and digest.hexdigest() == manifest["sha256"]
    print("Public EXE assembled and SHA-256 verified", flush=True)

    git("fetch", "--depth=1", "https://github.com/storytold/photocraft.git", BASE)
    git("read-tree", "--reset", "-u", "FETCH_HEAD")
    git("apply", "--index", str(patch))
    # Keep the original developer's CI definitions for reference, without enabling their
    # scheduled builds and deployment jobs in this independent distribution repository.
    archive = root / ".github/upstream-workflows"
    archive.mkdir(parents=True, exist_ok=True)
    for path in sorted((root / ".github/workflows").glob("*")):
        if path.is_file():
            git("mv", str(path.relative_to(root)), str((archive / path.name).relative_to(root)))
    git("add", "-A")
    assert git("write-tree") == manifest["expected_tree"], "Imported source tree differs from the reviewed tree"
    # Keep this unchanged while the job pushes: contents-write is sufficient and the job
    # does not need permission to edit workflows. The caller removes this bootstrap later.
    workflow = root / ".github/workflows/publish-japanese.yml"
    workflow.parent.mkdir(parents=True, exist_ok=True)
    workflow.write_bytes(bootstrap)
    git("add", str(workflow.relative_to(root)))
    git("config", "user.name", "yeezy-529")
    git("config", "user.email", "85273889+yeezy-529@users.noreply.github.com")
    git("commit", "-m", "Import Japanese PhotoCraft edition and Windows packaging [skip ci]")
    source_commit = git("rev-parse", "HEAD")
    auth = base64.b64encode(("x-access-token:" + TOKEN).encode()).decode()
    environment = os.environ.copy()
    environment.update({"GIT_TERMINAL_PROMPT": "0", "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "http.https://github.com/.extraheader", "GIT_CONFIG_VALUE_0": "AUTHORIZATION: basic " + auth})
    git("push", "origin", f"HEAD:refs/heads/{BRANCH}", env=environment)
    print("Source imported:", source_commit, flush=True)

    body = (
        "Photoshopに近い日本語UIへ調整した、Windows x64向けの単体EXEです。初回は必要ファイルを自動展開します。\n\n"
        "確認済み: 日本語化テスト76件、起動パッケージ4件、公開用診断パス匿名化4件、画面の自動描画、PNG・JPEG・PSD保存。"
        "実ウィンドウ操作・ハードウェアGPU高速化は未確認です。一部の処理メッセージは英語が残ります。\n\n"
        "自動更新確認は初回設定でOFFです。手動更新機能は残っています。公開用EXEでは診断文字列内のビルドPCパスを匿名化しています。\n\n"
        f"元のソース: storytold/photocraft @ {BASE}\n\nSHA-256: `{manifest['sha256']}`\n"
    )
    release = request("POST", f"{API}/repos/{REPO}/releases", {
        "tag_name": manifest["tag"], "target_commitish": source_commit,
        "name": "PhotoCraft 日本語版 0.20.1", "body": body, "draft": True, "prerelease": True,
    })
    upload = release["upload_url"].split("{", 1)[0]
    assert urllib.parse.urlsplit(upload).hostname == "uploads.github.com"
    attached = request("POST", upload + "?name=" + urllib.parse.quote(manifest["asset_name"]), asset.read_bytes(), binary=True)
    assert attached["size"] == manifest["size"]
    if attached.get("digest"):
        assert attached["digest"] == "sha256:" + manifest["sha256"]
    published = request("PATCH", f"{API}/repos/{REPO}/releases/{release['id']}", {"draft": False})
    print(json.dumps({"release": published["html_url"], "asset": attached["browser_download_url"], "source_commit": source_commit, "sha256": manifest["sha256"]}), flush=True)


if __name__ == "__main__":
    main()
