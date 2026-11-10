# XrmTools.Build architecture and compatibility assessment

## Repository baseline

The initial repository contained only `LICENSE`. There were no existing `.cdsproj` or
plugin projects, AlbanianXrm references, templates, CI workflows, tests, or package
output conventions to preserve. The implementation therefore starts with isolated
fixtures and must not imply backwards compatibility with repository behavior that
does not exist.

## Verified target-order map

The package was downloaded from NuGet and inspected locally on 9 November 2026:
`Microsoft.PowerApps.MSBuild.Solution` **2.14.1**. Its `build/Microsoft.PowerApps.MSBuild.Solution.targets`
defines this relevant order:

1. `CopyCdsSolutionContent` runs `BeforeTargets="ProcessCdsProjectReferencesOutputs"`.
   It copies source content from `$(SolutionRootPath)` into
   `$(SolutionPackagerMetadataWorkingDirectory)`.
2. `ProcessCdsProjectReferencesOutputs` runs `BeforeTargets="PowerAppsPackage"` and
   processes outputs returned by referenced projects' `GetProjectOutputPath` target.
3. `PowerAppsPackage` runs `AfterTargets="AfterBuild"` and invokes Microsoft's
   `SolutionPackagerTask` on `$(SolutionPackagerMetadataWorkingDirectory)`.
4. `CleanUpIntermediateFiles` runs after `PowerAppsPackage` and removes the metadata
   and localization working directories.

The same Microsoft targets define `SolutionVersioningPipeline` with
`AfterTargets="CopyCdsSolutionContent"` and `BeforeTargets="PowerAppsPackage"`, proving
that staging-copy version operations are an intended integration point in this
package release. This ordering has also been exercised with solution package 2.13.1; it is not a promise
that all package releases preserve the same target graph. In the actual fixture,
`BeforeTargets` alone did not cause the staging/reference targets to execute, so
XrmTools.Build explicitly depends on the existing `CopyCdsSolutionContent` and
`ProcessCdsProjectReferencesOutputs` targets before stamping. The real build/binlog
confirmed that sequence and Microsoft's subsequent ZIP packaging.

The package contains task assets under `tasks/net472` and `tasks/net6.0`. The
fixtures proved builds and ZIP packaging on this macOS host with both tested versions.
Availability of a .NET 6 task asset and one fixture build do not establish broad
or future Dataverse packaging support on macOS or Linux.

## Upstream findings

- AlbanianXrm's current `Sdk.targets` runs package-copy logic before
  `CopyCdsSolutionContent`, discovers outputs via `_GetOutputItemsFromPack`, and
  passes `FileVersion` to plugin project builds and packs. It also removes
  matching `ProjectReference` items and edits source solution XML. These are
  observations of its implementation, not behavior copied into this package.
- NuGet's current `NuGet.Build.Tasks.Pack.targets` defines
  `_GetOutputItemsFromPack` conditionally on
  `PackageReferenceCompatibleProjectStyle=true`, returning `_OutputPackItems`.
  The task receives package ID/version, symbols, nuspec, and output-name inputs.
  The target remains internal and version-sensitive; it is not used as a public
  contract in the initial version resolver.
- NBGV documentation states that `GetBuildVersion` must execute before consuming
  its generated properties and that `BuildVersion` is numeric while `PackageVersion`
  can be prerelease SemVer. The fixture confirms that `GetBuildVersion` is imported
  by an opt-in package reference and returns the numeric version to the resolver.
- Microsoft Power Platform CLI documentation specifies a nonnegative integer for
  build and revision solution-version components. It does not establish maximum
  values for all four components or Dataverse import compatibility. The initial
  resolver validates four numeric components and MSBuild/System.Version integer
  bounds; actual server-side limits and imports remain unverified.

## Compatibility assumptions and boundaries

- `XrmTools.Build` is an ordinary NuGet package that contributes `build/` assets.
  It does not select or replace the Microsoft solution package.
- Validation passed on the installed .NET SDK 10.0.403 / MSBuild 18.9.15
  on macOS arm64 with Microsoft solution packages 2.14.1 and 2.13.1 and the real
  Microsoft PCF targets from package 2.14.1. Phase 4's package-first regression
  also passed in hosted Windows and macOS dotnet CI; the linked evidence and
  exact scope are recorded in [artifact discovery](artifact-discovery.md).
  The fixture's `.cdsproj` also adds Microsoft's reference-assemblies package so
  the legacy .NET Framework target can build on this host.
- Microsoft Visual Studio/MSBuild on Windows, Azure DevOps,
  Linux, IDE design-time/static-graph builds, Dataverse deployment/import, and
  other Microsoft package releases are not
  available for validation in this worktree. No support claim is made for them
  until tested.
- Stamping is limited to the Microsoft staging directory; a source/staging path
  collision fails before stamping. The source solution XML remains unchanged.
  Exactly one staged Version element is required. Four ASCII decimal components
  are validated before any numeric conversion using normalized string bounds;
  overflowing inputs produce XTB1003 rather than a property-function exception.
  Unchanged staged versions skip XmlPoke entirely.
- Phase 5 now validates final ZIP plugin XML, embedded package bytes and preserved
  metadata using independent fixtures. Dataverse deployment/upgrade behavior is
  still unverified.

## Phase 3: explicit project-reference integration

### Verified Microsoft behavior and alternatives

In both tested solution packages, `ProcessCdsProjectReferencesOutputs` uses:

```xml
<MSBuild Projects="@(ProjectReference)" Targets="GetProjectOutputPath">
  <Output TaskParameter="TargetOutputs" ItemName="ProjectReferenceCopyLocalPaths" />
</MSBuild>
```

It then passes those outputs to Microsoft's reference-processing task. The task
does not select references using `ReferenceOutputAssembly`, `BuildReference`, or
reference `Targets` metadata. The MSBuild task's supported per-project metadata
includes `Properties`, `AdditionalProperties`, and `UndefineProperties`, but cannot
override this fixed task-level target name for an individual reference.

Permanent/evaluation-time removals would corrupt normal restore and dependency
tracking. Changing producer targets to impersonate `GetProjectOutputPath` would
require modifying otherwise independent C# projects. Replacing Microsoft's target
would own its implementation and is rejected. Instead, the adapter snapshots only
explicitly marked `.csproj` references immediately before this Microsoft target,
filters them for that call, and restores them in an AfterTargets hook on success.
Removal matches FullPath **and marker**, so an unmarked reference to the same
project remains Microsoft's responsibility.

### Contract and target order

- `XrmToolsGetPluginPackageProjects` classifies references using only literal
  `XrmToolsPluginPackage=true` metadata. It executes before normal reference
  preparation/restore traversal and returns `XrmToolsPluginPackageProject` items
  through `Returns`. It does not evaluate raw producer XML, build, or pack.
- All metadata is copied, including explicit unique names/publisher prefixes,
  optional `ManagedIdentityId`, `XrmToolsPluginPackagePath`, and build dimensions.
  XTB2000 through XTB2004 reject malformed markers, missing projects, non-C#
  producers, duplicate normalized paths, and duplicate explicit unique names
  (case-insensitive). Package-derived names/identities are deferred.
- Normal Microsoft.Common/NuGet restore and dependency build scheduling remain
  responsible for producers. Phase 3 originally rejected Pack in its test fixture.
  Phase 4 adds explicit Pack/discovery processing described below, while retaining
  independent producer versions and build-count assertions.
- Before Microsoft's reference-output processing, `_XrmToolsFilterMicrosoftProjectOutputs`
  saves/removes only marked references. Unmarked C# and PCF references still reach
  the Microsoft target. The original incomplete-inclusion warning XTB2005 was
  retired when Phase 5 added staging.
- `_XrmToolsRestoreMicrosoftProjectReferences` restores the saved items and metadata
  after successful Microsoft processing. The existing resolver then stamps the
  staged solution before `PowerAppsPackage`; Microsoft still creates the ZIP and
  cleans staging. No Microsoft target definition is overwritten.

### Compatibility diagnostics and remaining risks

XTB1000 checks Microsoft's staging property/import contract and rejects a direct
source/staging path collision. XTB1002 checks staged manifest presence/shape.
XTB1001 warns when Microsoft's separate `SolutionVersionStrategy` is configured.
There is no Microsoft package-version allowlist or new NuGet dependency.
MSBuild does not provide a built-in supported target-existence query; missing
target names still produce its normal missing-target error, with the required
contract described by the extension's diagnostic message and this document.
These checks do not prove compatibility with an arbitrary future target graph.

The scoped filter is a version-sensitive adapter, not an unconditional SDK
compatibility guarantee. Another extension's BeforeTargets/AfterTargets hook can
observe the temporary reference list. Restoration appends marked items rather
than preserving their original interleaving; unmarked order is unchanged.
If Microsoft's target fails, its AfterTargets hooks do not run: the failed
in-memory project instance can retain the filtered list. A fresh MSBuild
invocation reevaluates the complete source references; callers that reuse failed
instances or continue after nested failures need separate verification. No
general Visual Studio, static-graph, failure-recovery, or third-party-hook
interoperability claim is made.

`ReferenceOutputAssembly=false` is recommended on package-only references, but
not injected: Microsoft.Common framework compatibility and configuration mapping
are intentionally not changed. An unmarked plain C# project without
`GetProjectOutputPath` still fails with Microsoft's MSB4057, as it did without
the extension. This is verified, not silently hidden.

### Reproducible evidence

`./eng/test-package.sh` packs the actual NuGet assets and runs baseline regression
plus `eng/test-targets.py`. Tests use disposable fixture paths containing spaces.
They retain complete recursive NuGet restore graphs, diagnostic logs, and binlogs
under ignored `artifacts/`. Coverage includes 0/1/2 producers, both tested solution
versions, arbitrary metadata, one producer without XrmTools.Build, distinct
Debug/Release reference dimensions, unchanged producer versions, no duplicate
build, and `BuildProjectReferences=false`. Direct output-target invocations
also restore references. Negative tests cover invalid/missing/duplicate references
and an unmarked reference sharing a marked producer's path.

The mixed-reference fixture imports real Microsoft PCF targets and executes their
npm build contract against a minimal prebuilt control payload. It verifies
reference processing and packaging, not pcf-scripts/TypeScript compilation. Final
ZIP inspection requires solution version 4.5.6.7 and the prefixed PCF manifest and
bundle; source XML hashes are unchanged. Phase 5 extends these ZIP assertions with producer `.nupkg` inclusion and
synchronized plugin XML. It is not Dataverse import validation.

## Phase 4: exact artifact discovery

See [artifact-discovery.md](artifact-discovery.md) for the investigated NuGet
adapter behavior, execution order, producer-return and explicit-path contracts,
compiled-task justification, diagnostic codes, pack-execution evidence, and complete
test matrix. Discovery processes classified items and private copies only; the
Phase 3 ProjectReference adapter receives no additional mutations.

Normal reference builds precede Pack. Multi-target producers require an outer
build so all package TFMs exist, followed by Pack with NoBuild=true. Producer
configuration/platform/AdditionalProperties and independent NuGet versions remain
intact. A small netstandard2.0 task checks the exact ZIP's nuspec against expected
NuGet identity/version, rather than trusting predicted filenames. The internal
adapter forces the isolated NuGet packaging target to execute while leaving
compilation incremental, and validates against current evaluated identity.
This fixes repeated builds without trusting timestamps or stale generated
nuspecs. A temporary producer-only import chains existing custom import hooks;
it changes no source files or ProjectReference items. Unsupported custom
nuspec/versionless predictions still require explicit contracts.

The failure-recovery test covers both Microsoft solution versions. A deliberately
failed reference-output target leaves marked references filtered in a reused
failed project instance; a fresh invocation reevaluates complete references,
builds successfully and discovers both packages. This remains a documented
limitation, not an excuse to add more ProjectReference mutations.

## Phase 5: staging and final ZIP validation

See [plugin package staging](plugin-package-staging.md) for metadata precedence,
path safety, final output contracts, diagnostics and the new compatibility
assumptions. Stage and final-ZIP tasks reuse the existing netstandard2.0 assembly.
They consume Phase 4's validated artifact items, not another discovery mechanism.
No new NuGet/Microsoft internal targets are used or overwritten.

The verified order is source/stage isolation check and plugin-only intermediate
reset → Microsoft source copy/reference processing → solution version resolution
→ Phase 4 discovery → plugin metadata/copy → Microsoft PowerAppsPackage →
Microsoft cleanup and final ZIP validation (the latter two need not be ordered).
Validation uses evidence captured before cleanup. All included source-only
plugin packages are synchronized, including zero-producer builds.

The new filesystem reset is necessary because Microsoft's copy only overlays
files and failed builds skip its normal cleanup. A regression deliberately leaves
bad staged metadata, deletes that source package, then verifies a fresh successful
build excludes the stale component. The reset is restricted to intermediate
`pluginpackages`, with ancestry/link checks before source copying. This is not a
third ProjectReference or producer-pack state workaround.

## Phases 0–5 architectural review

The review retains the two existing compatibility adapters. No concrete evidence
supports their safe elimination:

| Question | Evidence and conclusion |
| --- | --- |
| Is producer compilation incremental? | The retained Phase 4 repeat-build matrix runs actual `dotnet build` four times with both Microsoft versions, with/without GeneratePackageOnBuild. Unchanged DLL hashes **and mtimes** remain identical; a source edit changes the DLL and embedded package payload. Stage/final validation call no producer targets. |
| Are producers redundantly built? | Mixed 0/1/2 producer tests assert one Build record per referenced producer, including distinct Debug/Release dimensions. Multi-target outer Build is retained only to fill missing package TFMs; MSBuild caches already-built inner targets. No new Build call is added. |
| Are packages redundantly generated? | Yes, intentionally: the isolated NoBuild adapter regenerates standard NuGet packaging; GeneratePackageOnBuild may add a prior Pack. Existing tests prove future-dated/same-ID stale payloads and same-size/same-time source payload changes cannot bypass it. Removing invalidation would weaken correctness. |
| Can the temporary reference filter go away? | Both restored Microsoft targets hardcode `GetProjectOutputPath` on every ProjectReference, ignoring ReferenceOutputAssembly. Tests prove unmarked unsupported C# still fails normally; removing the filter would fail marked producers or require changing them/replacing Microsoft's target. Neither is a simplification of the supported contract. |
| Are consecutive builds/configuration changes correct? | Unchanged builds, changed source/payload/PackageId/PackageVersion, Debug→Release→Debug, source-only packages, custom output directories and Both outputs inspect final package bytes and versions. Combined Managed=2 source is needed for Microsoft's default Debug=Unmanaged/Release=Managed switch; the extension does not convert an unmanaged-only source to managed. |
| Are source files unchanged? | Target, artifact and staging suites compare source XML hashes/bytes before/after builds. Namespaces, UTF-16 declarations, comments, unknown fields, existing filenames/flags, prefixed names and nested managed identity survive final-ZIP inspection. Ancestry/symlink tests reject indirect source staging. |
| Do normal C#/PCF references still work? | Real Microsoft PCF targets with a prebuilt control payload and ordinary C# output contracts remain in the Microsoft path; final ZIP checks preserve PCF manifest/bundle and solution root component. No new reference mutations are introduced. |
| Do errors fail safely? | Missing/ambiguous/stale artifacts, malformed XML/archives, duplicate names, compiler/pack/staging failures and final-ZIP tampering fail explicitly. Failed builds can leave an older ZIP, but no validation success is emitted. A fresh invocation recovers; failed in-memory reference-filter instances retain the already documented limitation. |
| Are there side effects beyond extra packaging time? | Yes: staged package copies/XML edits, narrow intermediate plugin reset, linear path/link checks and ZIP/hash I/O, plus transient private evidence items. User output paths, source XML and producer version properties are not changed. Stage directories are now restricted to intermediate/disjoint/unlinked locations; extensions observing/staging plugin files before the copy boundary must respect reset ordering. |

### Compatibility and performance conclusions

The extension remains additive, but not side-effect-free. The scoped reference
filter can be observed by other hooks, appends restored marked references, and
does not restore a failed in-memory instance. The pack adapter temporarily changes
producer-only import globals and deliberately defeats NuGet Pack incrementality.
Phase 5 adds no such adapter, but assumes Microsoft's stage and ZIP layout and
uses the documented Both suffix because the task exposes no output items.
An archive mapping that changes plugin entry paths fails validation rather than
silently producing an unsupported layout.

Phase 5 logs preparation, staging and final-ZIP validation times separately from Pack. Costs
scale with file inventory and package bytes, not just package count; Both hashes
both outputs. CI fixture timings are not performance guarantees for large real
packages. The local small-fixture sample medians were 3 ms preparation, 3.5 ms
staging and 1 ms final validation; [staging details](plugin-package-staging.md)
record counts/ranges and their limited scope. Source-only archives do not incur
Pack. Compilation is not deliberately
invalidated. No source XML writes or user NuGet-output directory mutations are
added. Concurrent writers sharing a producer output/stage, Visual Studio
MSBuild/design-time/static-graph behavior, other Microsoft releases and Dataverse
imports remain unverified.

No broad refactoring is proposed. A future documented Microsoft package-reference
output extension point could eliminate the filter; a public NuGet
freshly-produced-output contract could avoid forced packaging. Neither exists in
the inspected targets, so changing them now would trade measured reliability for
speculation. The only implemented simplifications are retiring the obsolete
incomplete-staging warning and sharing the existing nuspec reader; the package
regression runner also reads the package version from the manifest instead of
duplicating the cache filename constant.

## Prioritized implementation gates

| Priority | Work | Acceptance evidence |
| --- | --- | --- |
| 0 | Record the additive-package decision and baseline/toolchain findings | This assessment and ADR; no speculative source behavior |
| 1 | Package `build/XrmTools.Build.props` and `.targets`; restore/import through real `PackageReference` in a minimal Microsoft `.cdsproj` | Locally packed `.nupkg`, generated NuGet imports, successful build or a clearly recorded platform blocker |
| 2 | Resolve explicit > enabled NBGV > staged `Solution.xml`; validate a four-part numeric version and stamp only staged content | Fixture builds for all sources, invalid-version failure, ZIP version check, unchanged source file |
| 3 | Classify explicit plugin references without replacing Microsoft targets or hiding normal C#/PCF references | Real mixed-reference builds/ZIPs, restore graph, metadata and build-count assertions; scoped-filter risks recorded above |
| 4 | Producer Pack, exact output discovery and validated fallbacks | Package-first artifact matrix, compiled-task validation and failed-instance recovery tests |
| 5 | Plugin metadata creation, solution staging and final-ZIP validation | Source-only/producer/mixed fixtures, metadata/encoding, negative cases, failure recovery and final-ZIP tampering |
| 6 | Diagnostics, predictable execution and package quality | Contextual error assertions, Clean/Restore/Build/Rebuild/Pack/NoBuild and isolated parallel regressions, built-package asset checks and extracted examples |

### Phase 6 baseline assessment and changes

The Phase 6 work started at merged remote main `b272863`. No `AGENTS.md` or
`XrmTools-Build-Implementation-Plan.md` (including `plan/`) existed in that tree or
the session Library. The current targets, tests and accepted ADR, not an earlier
conversation or superseded plan proposals, supplied the implementation baseline.
The complete baseline package-first run passed 48 methods.

Already satisfied: validated Phase 4 artifacts; independent producer versions;
staging-only metadata edits; preservation of identities/names; final validation of
Unmanaged/Managed/Both; deliberate NoBuild package regeneration; incremental
compilation and failed-build recovery. Neither adapter needed an execution change.
No directory scanning/timestamp selection was added for producer artifacts.

Remaining gaps addressed: generic errors omitted the active XML/artifact/root
paths and some corrective guidance; execution contracts lacked direct cold/warm
Restore/query, Clean/Rebuild/NoBuild and simultaneous isolated-run regressions;
the built nupkg checks omitted README/license metadata and runnable examples;
release notes and consolidated troubleshooting were missing. The probes showed
no solution Pack target and NETSDK1085 when NoBuild was passed to normal reference
Build. These are documented Microsoft/SDK boundaries, not reasons to replace
targets or add another compatibility adapter.

Phase 6 changes diagnostics and verification/documentation, not consumer scheduling
or cleanup behavior. A package-project regression also demonstrated that its own
BuildPackAdapters hook ran during `dotnet pack --no-build` and failed with
NETSDK1085; that hook now respects NoBuild and packages prebuilt helpers instead.
This does not change consumer producer Pack regeneration.
See [execution](execution.md), [troubleshooting](troubleshooting.md)
and [release notes](release-notes.md). Microsoft's Clean recursively owns its
configured solution directories; separate user NuGet stores survive. Mixed
user/build directories and shared-output concurrent writers remain unsupported.
No new internal-target dependency, runtime package dependency, reference mutation,
producer import change or broadened cleanup is introduced.

Phase 0 baseline ZIPs with plugin packages/PCF references cannot be captured because
the repository has no such projects. The minimal fixture added for Phase 1 is the
first reproducible baseline; it is not a substitute for Visual Studio or Dataverse
integration validation.
