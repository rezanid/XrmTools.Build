# XrmTools.Build architecture and compatibility assessment

## Repository baseline

The initial repository contains only `LICENSE`. There are no existing `.cdsproj` or
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
package release. This is target-file evidence for 2.14.1 only; it is not a promise
that all package releases preserve the same target graph. In the actual fixture,
`BeforeTargets` alone did not cause the staging/reference targets to execute, so
XrmTools.Build explicitly depends on the existing `CopyCdsSolutionContent` and
`ProcessCdsProjectReferencesOutputs` targets before stamping. The real build/binlog
confirmed that sequence and Microsoft's subsequent ZIP packaging.

The package contains task assets under `tasks/net472` and `tasks/net6.0`. The
fixture proved a build and ZIP package on this macOS host with version 2.14.1.
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
- Initial validation passed on the installed .NET SDK 10.0.403 / MSBuild 18.9.15
  on macOS arm64 with the exact Microsoft package version pinned in the fixture.
  The fixture's `.cdsproj` also adds Microsoft's reference-assemblies package so
  the legacy .NET Framework target can build on this host.
- Microsoft Visual Studio/MSBuild on Windows, Azure DevOps, GitHub Actions,
  Dataverse deployment/import, and other Microsoft package releases are not
  available for validation in this worktree. No support claim is made for them
  until tested.
- Stamping is limited to the Microsoft staging directory. The source solution XML
  remains unchanged by default.
- No assertion is made about plugin-package artifact discovery, plugin reference
  transformation, final ZIP plugin XML, or Dataverse upgrade support until those
  phases have independent fixtures and tests.

## Prioritized implementation gates

| Priority | Work | Acceptance evidence |
| --- | --- | --- |
| 0 | Record the additive-package decision and baseline/toolchain findings | This assessment and ADR; no speculative source behavior |
| 1 | Package `build/XrmTools.Build.props` and `.targets`; restore/import through real `PackageReference` in a minimal Microsoft `.cdsproj` | Locally packed `.nupkg`, generated NuGet imports, successful build or a clearly recorded platform blocker |
| 2 | Resolve explicit > enabled NBGV > staged `Solution.xml`; validate a four-part numeric version and stamp only staged content | Fixture builds for all sources, invalid-version failure, ZIP version check, unchanged source file |
| 3+ | Add marked plugin references, producer pack flow, artifact discovery and plugin metadata staging | Deferred until earlier acceptance gates pass |

Phase 0 baseline ZIPs with plugin packages/PCF references cannot be captured because
the repository has no such projects. The minimal fixture added for Phase 1 is the
first reproducible baseline; it is not a substitute for Visual Studio or Dataverse
integration validation.
