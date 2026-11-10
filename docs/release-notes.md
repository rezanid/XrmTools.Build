# Release notes

## 0.5.0-phase6 (unpublished)

Diagnostics now include active stage/source/intermediate paths, the failing
artifact/XML/ZIP, relevant input values and corrective guidance. Existing
XTB1000-XTB4002 codes retain their meanings. Both-output failures identify the
actual failing managed ZIP, rather than only the base ZIP.

Added package-first execution regressions for cold/warm Restore and read-only
queries, Clean/recovery/Rebuild with separate user NuGet stores, solution Pack's
unsupported-target result, prebuilt NoBuild semantics, and simultaneous builds
of the same source with fully isolated per-project paths. Existing repeated-build,
compile incrementality, failure recovery and final ZIP validation remain intact.
No consumer execution target, reference filter or NuGet adapter was replaced or
expanded. The build-extension project's own `BuildPackAdapters` hook now respects
NoBuild: previously `dotnet pack XrmTools.Build.csproj --no-build` tried to Build
the adapter helpers and failed with NETSDK1085. Prebuilt helper files are still
required; NuGet reports missing files rather than silently rebuilding them.

The package now carries execution/troubleshooting documentation, these release
notes and a runnable minimal solution/producer example. Package checks cover the
actual README/license metadata, build assets, helper assemblies, attribution,
dependency exclusion and links; the extracted example is built through real
PackageReference restore. Producer NuGet versions remain independent.

No new runtime dependencies, directory scans for artifacts, timestamp selection,
source metadata writes, cleanup scope or compatibility workarounds are introduced.
The existing deliberate NoBuild producer package regeneration, intermediate-only
plugin reset and path restrictions remain. Shared-output concurrent writers are
unsupported, including Clean alongside Build. Microsoft's Clean owns its
configured directories: keep user package stores separate.

Phase 7 deployment/import/upgrade validation, desktop Visual Studio, Linux,
Azure DevOps, design-time/static-graph builds and broad SDK certification remain
separate gates. No package is published by this work.

## 0.4.0-phase5

Validated artifact staging, preservation/generation of plugin metadata, synchronized
solution/plugin XML versions, narrow intermediate failed-build recovery and final
Unmanaged/Managed/Both ZIP validation. See [staging](plugin-package-staging.md).
