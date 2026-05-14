# Release Tags

This file records the immutable commit mapping for released template versions. It exists so migration baselines can be recreated if a local or remote tag is accidentally deleted.

| Version | Tag | Commit | Notes |
|---------|-----|--------|-------|
| 0.2.0 | `v0.2.0` | `2db730164d2d44cc343c1556c975c27d8a5efa32` | Last 0.2.0-line commit before 0.3.0 feature work. |
| 0.3.0 | `v0.3.0` | `fd30e86d68a91786b39af85dcf3bfce8a3000c1e` | 0.3.0 release commit. |
| 0.3.1 | `v0.3.1` | `57811184c870d31e22fc047e06314c626c2c7a79` | Migration framework tooling release. |
| 0.3.2 | `v0.3.2` | `499eb163bdc4cf5de39f7572a538af418828be4c` | Pre-0.4.0 lightweight tag; baseline listed in `core/migrations/0.4.0/migration.json::from_versions`. |
| 0.4.0 | `v0.4.0` | `2bb93a0ea9870eccdba1c195f7e65ed367a58ed7` | Template release 0.4.0. |
| 0.5.0 | `v0.5.0` | `3900230d548852696fd39b6745fe05f08179c7fb` | Template release 0.5.0 (empty migration). |
| 0.6.0 | `v0.6.0` | `264b0661a80c235dfd2a3b63078d2e45cbc3b8ce` | Template release 0.6.0. |
| 0.7.0 | `v0.7.0` | `fb5ce62789203200a8d987befb6a39301bc8f0b9` | Template release 0.7.0. |
| 0.8.0 | `v0.8.0` | `a59e21bb5056a0f72f638f43c84391806b90100b` | Template release 0.8.0. |
| 0.8.1 | `v0.8.1` | `303546cf8eff42e6f539a12f12403bf7abb7afa0` | Patch release 0.8.1. |
| 0.9.0 | `v0.9.0` | `670d5a53ff3563bdad33461aad03315c86c0b8b0` | Template release 0.9.0. |
| 0.10.0 | `v0.10.0` | `78aba0a307829ca1640ebe6f912173100a5af952` | Template release 0.10.0 (constitution split). |
| 0.11.0 | `v0.11.0` | `8b223bdc3cde12c554169d899c4454bab17b3216` | MCP discovery + D-11 Option A backfill `core/migrations/0.11.0/`. |
| 0.12.0 | `v0.12.0` | `00453a67f499f6105900eb1b819d32fecb2e66d7` | Stage 3 trust-layer (sync runner) + Stage 3.4 release-prep scaffold; template-internal only. |
| 1.1.0 | `v1.1.0` | `<PENDING>` | Replace `<PENDING>` with the release commit after `git tag -a v1.1.0` (see core/release-process.md). |

## Recovery

If a release tag is missing, recreate the annotated tag at the recorded commit:

```bash
git tag -a v0.2.0 2db730164d2d44cc343c1556c975c27d8a5efa32 -m "agent-bootstrap-template 0.2.0"
git tag -a v0.3.0 fd30e86d68a91786b39af85dcf3bfce8a3000c1e -m "agent-bootstrap-template 0.3.0"
git tag -a v0.3.1 57811184c870d31e22fc047e06314c626c2c7a79 -m "agent-bootstrap-template 0.3.1"
git tag -a v0.3.2 499eb163bdc4cf5de39f7572a538af418828be4c -m "agent-bootstrap-template 0.3.2"
git tag -a v0.4.0 2bb93a0ea9870eccdba1c195f7e65ed367a58ed7 -m "agent-bootstrap-template 0.4.0"
git tag -a v0.5.0 3900230d548852696fd39b6745fe05f08179c7fb -m "agent-bootstrap-template 0.5.0"
git tag -a v0.6.0 264b0661a80c235dfd2a3b63078d2e45cbc3b8ce -m "agent-bootstrap-template 0.6.0"
git tag -a v0.7.0 fb5ce62789203200a8d987befb6a39301bc8f0b9 -m "agent-bootstrap-template 0.7.0"
git tag -a v0.8.0 a59e21bb5056a0f72f638f43c84391806b90100b -m "agent-bootstrap-template 0.8.0"
git tag -a v0.8.1 303546cf8eff42e6f539a12f12403bf7abb7afa0 -m "agent-bootstrap-template 0.8.1"
git tag -a v0.9.0 670d5a53ff3563bdad33461aad03315c86c0b8b0 -m "agent-bootstrap-template 0.9.0"
git tag -a v0.10.0 78aba0a307829ca1640ebe6f912173100a5af952 -m "agent-bootstrap-template 0.10.0"
git tag -a v0.11.0 8b223bdc3cde12c554169d899c4454bab17b3216 -m "agent-bootstrap-template 0.11.0"
git push origin v0.2.0 v0.3.0 v0.3.1 v0.3.2 v0.4.0 v0.5.0 v0.6.0 v0.7.0 v0.8.0 v0.8.1 v0.9.0 v0.10.0 v0.11.0
```

Push is always user-triggered. The sync runner must never create or push release tags.

Do not retarget an existing release tag silently. If a published tag points at a different commit, stop and resolve it as a release integrity incident.

Use `scripts/bump-version.sh NEW_VERSION` to update version sources and add a new row with `<PENDING>`; replace the placeholder after tagging, then run `python3 scripts/lib/check_version_consistency.py --strict`.
