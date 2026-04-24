# Release Tags

This file records the immutable commit mapping for released template versions. It exists so migration baselines can be recreated if a local or remote tag is accidentally deleted.

| Version | Tag | Commit | Notes |
|---------|-----|--------|-------|
| 0.2.0 | `v0.2.0` | `2db730164d2d44cc343c1556c975c27d8a5efa32` | Last 0.2.0-line commit before 0.3.0 feature work. |
| 0.3.0 | `v0.3.0` | `fd30e86d68a91786b39af85dcf3bfce8a3000c1e` | 0.3.0 release commit. |

## Recovery

If a release tag is missing, recreate the annotated tag at the recorded commit:

```bash
git tag -a v0.2.0 2db730164d2d44cc343c1556c975c27d8a5efa32 -m "agent-bootstrap-template 0.2.0"
git tag -a v0.3.0 fd30e86d68a91786b39af85dcf3bfce8a3000c1e -m "agent-bootstrap-template 0.3.0"
git push origin v0.2.0 v0.3.0
```

Push is always user-triggered. The sync runner must never create or push release tags.

Do not retarget an existing release tag silently. If a published tag points at a different commit, stop and resolve it as a release integrity incident.
