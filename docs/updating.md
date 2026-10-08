# Updating

## Check

At startup, Emerager0DB asks `https://falks.cyou/api/version` for the newest version in the background. The check has a short timeout and fails silently, so the shell works offline. If a newer version exists, you see:

```text
A new Emerager0DB version is available: 0.2.0
Run `Emerager0DB update` to update.
```

## Update

```sh
Emerager0DB update
```

The update:

1. Reads the manifest over HTTPS.
2. Picks the release for your OS and CPU.
3. Downloads the checksum list and the new file.
4. Verifies the file's SHA-256. If it does not match, nothing is changed.
5. Replaces the executable. On Windows the old file is renamed first, because a running program cannot be overwritten.

Your databases, accounts and configuration are in the data directory, which an update never touches. Restart the shell to use the new version.

Self-update works only for standalone builds. If you installed with pip, run `pip install -U emerager0db` instead.

## Manifest format

`/api/version` returns:

```json
{
  "latest": "0.2.0",
  "release_url": "https://github.com/.../releases/tag/v0.2.0",
  "downloads": {
    "windows-x86_64": "https://.../Emerager0DB-windows-x86_64.exe",
    "linux-x86_64": "https://.../Emerager0DB-linux-x86_64",
    "linux-arm64": "https://.../Emerager0DB-linux-arm64",
    "macos-x86_64": "https://.../Emerager0DB-macos-x86_64",
    "macos-arm64": "https://.../Emerager0DB-macos-arm64"
  },
  "checksums": "https://.../SHA256SUMS"
}
```

## Publishing a new release

1. Bump `emerager0db/version.py` and `pyproject.toml`.
2. Tag and push: `git tag v0.2.0 && git push --tags`. The release workflow builds each platform on its native runner and publishes `SHA256SUMS`.
3. Update `web/api/releases.json` with the new `latest`, `release_url`, `downloads` and `checksums`, then redeploy the Railway service.

## Limits

Verification uses SHA-256 from the same HTTPS host as the download, so it guards against corruption and tampering in transit, not against a compromised release host. Release signing (for example minisign) is planned for a later version.
