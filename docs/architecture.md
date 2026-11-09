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
  Microsoft PCF targets from package 2.14.1.
  The fixture's `.cdsproj` also adds Microsoft's reference-assemblies package so
  the legacy .NET Framework target can build on this host.
- Microsoft Visual Studio/MSBuild on Windows, Azure DevOps, GitHub Actions,
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
- No assertion is made about plugin-package artifact discovery, final ZIP plugin
  XML, or Dataverse upgrade support until those
  phases have independent fixtures and tests.

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
  responsible for producers. The test producers record their own independent
  NuGet versions, build exactly once, and reject any Pack invocation.
- Before Microsoft's reference-output processing, `_XrmToolsFilterMicrosoftProjectOutputs`
  saves/removes only marked references and emits XTB2005: they are **not included**
  as packages yet. Unmarked C# and PCF references still reach the Microsoft target.
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
build/Pack, and `BuildProjectReferences=false`. Direct output-target invocations
also restore references. Negative tests cover invalid/missing/duplicate references
and an unmarked reference sharing a marked producer's path.

The mixed-reference fixture imports real Microsoft PCF targets and executes their
npm build contract against a minimal prebuilt control payload. It verifies
reference processing and packaging, not pcf-scripts/TypeScript compilation. Final
ZIP inspection requires solution version 4.5.6.7 and the prefixed PCF manifest and
bundle; source XML hashes are unchanged. Producer `.nupkg` inclusion is explicitly
absent and warned about. It is not plugin XML/import validation.

## Prioritized implementation gates

| Priority | Work | Acceptance evidence |
| --- | --- | --- |
| 0 | Record the additive-package decision and baseline/toolchain findings | This assessment and ADR; no speculative source behavior |
| 1 | Package `build/XrmTools.Build.props` and `.targets`; restore/import through real `PackageReference` in a minimal Microsoft `.cdsproj` | Locally packed `.nupkg`, generated NuGet imports, successful build or a clearly recorded platform blocker |
| 2 | Resolve explicit > enabled NBGV > staged `Solution.xml`; validate a four-part numeric version and stamp only staged content | Fixture builds for all sources, invalid-version failure, ZIP version check, unchanged source file |
| 3 | Classify explicit plugin references without replacing Microsoft targets or hiding normal C#/PCF references | Real mixed-reference builds/ZIPs, restore graph, metadata and build-count assertions; scoped-filter risks recorded above |
| 4+ | Producer pack flow, artifact discovery and plugin metadata staging | Not started; deferred for the next acceptance gate |

Phase 0 baseline ZIPs with plugin packages/PCF references cannot be captured because
the repository has no such projects. The minimal fixture added for Phase 1 is the
first reproducible baseline; it is not a substitute for Visual Studio or Dataverse
integration validation.
