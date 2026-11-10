# Execution contracts

These contracts are exercised through the built NuGet package with Microsoft
solution packages 2.13.1 and 2.14.1. XrmTools.Build does not replace their targets.
Commands below assume a restored `.cdsproj` and .NET CLI; add `-restore` to
`dotnet msbuild` when needed. `dotnet build` restores by default.

| Operation | Behavior |
| --- | --- |
| `dotnet restore Solution.cdsproj` | Restores the full reference graph; classification validates marked references. No producer Build/Pack or solution staging/packaging. |
| `dotnet msbuild Solution.cdsproj -t:XrmToolsPrintConfiguration` | Read-only diagnostic of evaluated project/version/build dimensions and source/intermediate/stage/ZIP paths. Does not evaluate or execute producer targets. |
| `dotnet msbuild Solution.cdsproj -t:XrmToolsGetPluginPackageProjects -getItem:XrmToolsPluginPackageProject` | Classifies and returns references/metadata without building or packing. Requires restored imports; not an artifact query. |
| `dotnet build Solution.cdsproj` | Normal incremental reference compilation, deliberate producer NoBuild Pack regeneration, validated artifact staging, Microsoft ZIP creation and final validation. Does not set producer versions. |
| `dotnet clean Solution.cdsproj` | Runs normal reference Clean and Microsoft's solution Clean. Does not Build/Pack producers. Removes solution output/intermediate/working directories and configured solution ZIP/log files. A separate producer `PackageOutputPath` and unrelated packages there survive. |
| `dotnet build Solution.cdsproj -t:Rebuild` | Clean then Build, with restore. Recompiles cleaned producer outputs, regenerates packages, stages and validates the final ZIP. |
| `dotnet pack Solution.cdsproj` (also `--no-build`) | **Not supported by the tested Microsoft solution SDKs**: MSB4057, target Pack does not exist. Use Build to create a solution ZIP, not a NuGet package. |
| `dotnet build Solution.cdsproj -p:NoBuild=true` | Not a solution-level skip switch: ordinary reference Build still runs and SDK producers reject it with NETSDK1085. |
| `dotnet build Solution.cdsproj -p:NoBuild=true -p:BuildProjectReferences=false` | Uses prebuilt reference outputs. Still regenerates producer packages and the solution ZIP; validates all artifacts. All producer package TFMs and ordinary C#/PCF outputs must already exist for the same dimensions. Missing outputs fail, even if an old `.nupkg` exists. |

`XrmToolsDiscoverPluginPackages` is deliberately **not read-only**: it resolves/builds
references and packs producers. `XrmToolsResolveSolutionVersion` copies/stamps the
stage and processes Microsoft's reference outputs; it is not a pure version query.
`XrmToolsStagePluginPackages` invokes both. `PowerAppsPackage` runs staging
prerequisites and final validation, but is not a substitute for restoring/building
all ordinary C#/PCF outputs. `XrmToolsValidatePackage` alone fails without staging
evidence in that invocation. Do not infer success from an existing ZIP after failure.

Producer `Pack` is a different operation: SDK `.csproj` producers own their NuGet
Pack contract. XrmTools.Build calls it with `NoBuild=true` after normal reference
compilation. The isolated adapter intentionally regenerates packaging even on
unchanged builds. `GeneratePackageOnBuild=true` can cause another Pack; this is
an accepted correctness cost, not repeated compilation.

For **this repository's build-package project**, `dotnet pack XrmTools.Build.csproj`
builds the helpers and packs the extension itself. After building it for the same
configuration, `dotnet pack XrmTools.Build.csproj --no-build` packages those helper
outputs without compiling them. This is not a command for creating solution ZIPs.

## Clean ownership and recovery

Keep producer NuGet output directories separate from solution/producer compilation
output and intermediate directories. XrmTools.Build does not add a package
directory deletion or wildcard package cleanup. Microsoft solution Clean
recursively removes its configured `OutputPath`, `IntermediateOutputPath` and
`SolutionPackagerWorkingDirectory`; ordinary producer Clean can remove its tracked
build outputs. **Do not put a user/shared package store in or above those paths,
or configure them to point at source/shared directories.** Those overlapping
layouts are unsupported and are not made safe by XrmTools.Build. Custom producer
Clean targets remain the producer owner's responsibility.

The regression suite checks relative and absolute custom producer package paths
with spaces, unrelated packages and nested user files through Clean, Build and
Rebuild. Microsoft's solution Clean also removes restore assets from its
intermediate directory: restore again before a direct MSBuild Build after Clean.
The next Build re-creates the validated stage. The narrow pre-copy reset of staged
`pluginpackages` remains required after failed overlay builds; it is unchanged.
A fresh invocation is required after a failed reference-output adapter instance.

## Repeated and parallel execution

Repeated unchanged builds preserve compiled assembly bytes **and modification
times**; changed source is recompiled, and changed package content is regenerated
even with unchanged size/timestamps. Do not disable the adapter to save Pack calls.

Concurrent writers to the same intermediate/staging, compiled output, NuGet
package output, solution ZIP or packager log path are **unsupported**. Separate
solution output paths alone are not sufficient if producer outputs still collide.
No locks, retry-on-corruption, directory scanning or newest-file selection are used.
The parallel regression builds the **same source projects** simultaneously with
distinct per-run/per-project restore/intermediate, stage, compile, NuGet output,
ZIP and log paths and checks both actual final ZIPs.

The simplest operational isolation is separate worktrees/checkouts with all
generated paths kept inside each worktree. If sharing sources, set paths early
(for example in `Directory.Build.props` imported by **each** project), not a single
global `IntermediateOutputPath` shared by all references:

```xml
<Project>
  <PropertyGroup Condition="'$(RunRoot)' != ''">
    <!-- RunRoot is absolute and unique per concurrent invocation. -->
    <BaseIntermediateOutputPath>$(RunRoot)/$(MSBuildProjectName)/obj/</BaseIntermediateOutputPath>
    <BaseOutputPath>$(RunRoot)/$(MSBuildProjectName)/bin/</BaseOutputPath>
    <PackageOutputPath>$(RunRoot)/$(MSBuildProjectName)/packages/</PackageOutputPath>
  </PropertyGroup>
</Project>
```

Use distinct names or add a stable project-specific segment if project names
collide. A nearer `Directory.Build.props` stops MSBuild's upward search: import
the common props explicitly there. Do not hardcode a shared stage, ZIP, log or
custom producer output that defeats isolation. Do not run Clean against another
active build's paths. Parallel evidence does not certify static-graph/IDE builds.
