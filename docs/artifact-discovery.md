# Phase 4: exact plugin NuGet artifact discovery

## Scope and verified findings

Phase 4 adds producer Pack and exact artifact validation, not plugin metadata
creation or solution staging. Microsoft still owns the final solution ZIP.
`XTB2005` warns that discovered producer packages are not yet included in it.
The Phase 3 classification/Returns contract and all per-reference metadata remain
intact. No additional ProjectReference mutation or producer import injection is
introduced.

The installed .NET SDK 10.0.403 `NuGet.Build.Tasks.Pack.targets` was inspected and
exercised with real packs and diagnostic logs/binlogs. `_GetOutputItemsFromPack`:

- Is conditional on `PackageReferenceCompatibleProjectStyle=true`.
- Returns `_OutputPackItems`: predicted absolute `.nupkg` and generated `.nuspec`
  paths, plus symbol outputs when enabled. It is also used internally for Pack's
  incremental inputs/outputs; it is not a report of files actually written.
- Passes PackageId, PackageVersion, output paths and symbols settings to
  `GetPackOutputItemsTask`. **In this SDK its target invocation omits
  OutputFileNamesWithoutVersion, NuspecFile and NuspecProperties**, even though
  Pack itself handles those settings.
- Can therefore return nonexistent paths, or worse, old files left by an earlier
  pack with different naming. Checking only existence and matching the old
  generated nuspec does not detect the latter.

The upstream [GetPackOutputItemsTask source](https://github.com/NuGet/NuGet.Client/blob/dev/src/NuGet.Core/NuGet.Build.Tasks.Pack/GetPackOutputItemsTask.cs)
includes support for those extra inputs. That does not prove that a particular
installed targets file supplies them. The adapter is deliberately best-effort,
not an SDK version allowlist, NuGet target replacement, or package-name formula
copied into XrmTools.Build. AlbanianXrm's use of the same internal target informed
the investigation, not a stability guarantee.

## Execution and dimensions

`XrmToolsDiscoverPluginPackages` runs before `PowerAppsPackage` and can also be
called explicitly. It depends on classification and normal reference resolution.
It uses `XrmToolsPluginPackageProject`, joining a private copy with Microsoft's
resolved SetConfiguration/SetPlatform/GlobalPropertiesToRemove metadata. The
original classified items and ProjectReference items are not changed.

Each producer is processed independently with its AdditionalProperties and normal
MSBuild per-project Properties/UndefineProperties behavior. A supported
`GetTargetFrameworks` probe detects multi-target projects; their outer Build fills
in frameworks not built by ordinary nearest-framework reference resolution.
MSBuild caches already-built inner targets. Pack then runs with NoBuild=true.
With BuildProjectReferences=false, all package build outputs must already exist;
the extension does not rebuild them. Restore remains a normal explicit prerequisite:
use `dotnet build`/`-restore` or restore before directly calling discovery, including
any dimension-dependent producer dependencies.

The extension never sets Version, FileVersion or PackageVersion. It removes its
solution-version properties from the pack/query calls rather than mapping them
to producer versions. It does not set PackageOutputPath. GeneratePackageOnBuild
may cause Pack to have already run during Build; a later Pack call can be
incremental, but no additional single-target Build is requested. Multi-target and
GeneratePackageOnBuild fixtures verify build counts.

## Selection and validation contracts

Selection precedence after successful Pack:

1. `XrmToolsPluginPackagePath` on the marked reference: one exact path, relative to
   the solution project's directory or absolute.
2. `XrmToolsGetPluginPackageArtifact` in the producer, if present and returning
   items. Relative returned paths are resolved against the producer directory.
   The standard MSBuild task's SkipNonexistentTargets probe allows producers with
   no XrmTools.Build reference and no such target. An empty return opts into the
   adapter; a nonempty invalid/ambiguous return is an error, not a silent fallback.
3. NuGet `_GetOutputItemsFromPack`, if present. Select exactly one primary
   `.nupkg` from its reported outputs; never search a directory or reconstruct a
   name from PackageId/PackageVersion.

`.snupkg`, `.nuspec`, and `.symbols.nupkg` are not primary candidates. Duplicate
primary return items are ambiguous, even if they name the same file. The selected
file must exist, be readable as a ZIP, and have exactly one root nuspec with one
nonempty package/metadata/id and version. DTDs/external XML resolution are disabled
and nuspec XML size is bounded. Nuspec package type SymbolsPackage is rejected.
The validator does not certify plugin contents, signatures, or a deliberately
renamed legacy symbols archive that lacks identifying metadata.

Expected identity comes from reference metadata
`XrmToolsPluginPackageId`/`XrmToolsPluginPackageVersion`, otherwise the selected
producer return item's `PackageId`/`PackageVersion`. For the internal adapter,
read the one reported **primary** generated nuspec (not `.symbols.nuspec`).
An explicit path without expected metadata can use that generated nuspec too.
Missing expected identity fails; an explicit path does not disable validation.
IDs compare case-insensitively. NuGet.Versioning compares normalized NuGet
versions with VersionRelease semantics: prerelease is significant, build metadata
is not, and e.g. 1.2 and 1.2.0 represent the same package version.

The adapter additionally requires the exact selected file's write time to be
within this discovery/build invocation. Otherwise XTB3007 fails closed: without
a producer-side public contract it cannot distinguish an intentional incremental
reuse from stale same-identity output after a custom nuspec/naming change.
This is **not** a newest-file algorithm. No other files are considered. Repeated
incremental packs and filesystems with coarse timestamps/clock skew may require
one of the explicit contracts below. No user artifact is deleted/touched to
force freshness. Explicit contracts authorize reuse but still run Pack and
verify existence, package shape, and expected identity/version. They do not prove
byte-for-byte correspondence to current producer source if Pack itself lies.

## Producer-return example

This example belongs in a producer that intentionally uses versionless output.
The producer owns the exact path formula; XrmTools.Build does not guess it.
No XrmTools.Build PackageReference is required in that producer.

```xml
<PropertyGroup>
  <OutputFileNamesWithoutVersion>true</OutputFileNamesWithoutVersion>
</PropertyGroup>
<Target Name="XrmToolsGetPluginPackageArtifact"
        DependsOnTargets="Pack" Returns="@(MyPluginArtifact)">
  <ItemGroup>
    <MyPluginArtifact Include="$(PackageOutputPath)/$(PackageId).nupkg">
      <PackageId>$(PackageId)</PackageId>
      <PackageVersion>$(PackageVersion)</PackageVersion>
    </MyPluginArtifact>
  </ItemGroup>
</Target>
```

For custom nuspec substitutions or custom pack implementations, return the actual
path and actual expected identity/version from that implementation, which can
intentionally differ from evaluated PackageId/PackageVersion. Return one primary
package, not an output directory or glob of existing packages. A custom build
script can record its exact output path in a property consumed by this target.

## Explicit fallback example

For unusual/custom nuspec naming, CI can supply the exact path and expected
identity explicitly on the solution reference:

```xml
<ProjectReference Include="../Plugin/Plugin.csproj"
                  ReferenceOutputAssembly="false"
                  XrmToolsPluginPackage="true">
  <XrmToolsPluginPackageUniqueName>xt_MyPlugin</XrmToolsPluginPackageUniqueName>
  <AdditionalProperties>Configuration=Release</AdditionalProperties>
  <XrmToolsPluginPackagePath>../Plugin/custom packages/Literal.CustomProducer.nupkg</XrmToolsPluginPackagePath>
  <XrmToolsPluginPackageId>Literal.CustomProducer</XrmToolsPluginPackageId>
  <XrmToolsPluginPackageVersion>3.4.5-rc.1</XrmToolsPluginPackageVersion>
</ProjectReference>
```

All three fields can reference the consuming project's own CI properties.
Providing path plus expected ID/version bypasses both discovery probes. This is
not a prebuilt/no-Pack option: a working producer Pack target is still required.
It does not change the producer's NuGet version or output directory.

## Output contract and diagnostics

The public target returns `XrmToolsPluginPackageArtifact` through Returns and
MSBuild.TargetOutputs. Each item identity is the absolute validated artifact path,
with `ProducerProject`, actual normalized `PackageId`/`PackageVersion`,
`DiscoverySource` (ExplicitPath/ProducerTarget/NuGetAdapter), and all original
reference metadata, including unique names, prefixes and managed identities.
It does not write pluginpackage.xml or stage/copy the file into a solution.

| Code | Meaning |
| --- | --- |
| XTB3000 | Producer Pack failed or is unavailable; original producer errors are retained |
| XTB3001 | Zero or multiple primary outputs; invalid/ambiguous return contract |
| XTB3002 | Explicit selection is not a primary .nupkg |
| XTB3003 | Exact selected file is missing after Pack |
| XTB3004 | Expected identity/version unavailable; supply explicit metadata or fix the producer contract |
| XTB3005 | Invalid/unreadable ZIP or nuspec, or symbols metadata |
| XTB3006 | Actual nuspec identity/version differs from expected |
| XTB3007 | Internal adapter selected unchanged pre-existing output; explicit reuse contract required |

## Validation matrix and remaining integration risks

`./eng/test-package.sh` packs the real build assets/tasks and runs both Python
standard-library suites. Tests inspect nupkg contents, metadata and build records,
and final Microsoft-generated solution ZIPs (which deliberately contain no new
producer packages yet). Fixtures preserve source XML hashes.

| Scenario | Available-host evidence |
| --- | --- |
| Microsoft solution SDK 2.13.1 and 2.14.1 | Real mixed C#/PCF solution packaging; 0/1/2 producers and recovery |
| Imported computed PackageId; explicit producer PackageVersion; NBGV | Exact ZIP nuspec identity/version, independent of solution 9.8.7.6 |
| Relative/absolute custom PackageOutputPath; spaces | Exact reported path; no package emitted to a replacement output directory |
| symbols.nupkg and snupkg | One primary artifact validated; symbol outputs exist but are excluded |
| OutputFileNamesWithoutVersion; literal/substituted custom nuspec | Installed adapter fails clearly; producer-return and exact-path fallbacks succeed |
| Multi-target net462/netstandard2.0; GeneratePackageOnBuild | Correct primary artifact and one Build record per framework |
| Missing Pack/internal adapter, IsPackable=false, missing/ambiguous/mismatched/corrupt outputs | Actionable XTB3000-XTB3006 failures; explicit identity fallback for custom Pack |
| Stale computed package and nuspec; newer unrelated packages | No stale/default or newest-file fallback; XTB3007 for unchanged internal selection |
| Malformed XML/DTD, symbol nuspec type, version normalization | Compiled-task tests through the packaged MSBuild assembly |
| Phase 3 failed Microsoft output target | Same failed instance retains two unmarked references; fresh invocation restores all four and discovers two packages |

Verified locally on macOS arm64, .NET SDK 10.0.403/MSBuild 18.9.15. Windows and macOS
dotnet CI is defined in `.github/workflows/build.yml`; a workflow definition alone
is not evidence that a particular hosted run passed.
[Run 42715091002](https://github.com/rezanid/XrmTools.Build/actions/runs/42715091002)
verified implementation commit `f8b44c1998250fc0f568e236c2ed59a55eeaab76`: both
Windows and macOS jobs passed the package-first checks and all 30 test methods,
using the configured .NET 10.0.x toolchain and both Microsoft solution versions.
This proves hosted dotnet builds for that run, not full desktop MSBuild support.
Full desktop Visual Studio
MSBuild, Linux, Azure DevOps, static-graph/IDE design-time builds and Dataverse
imports remain separate compatibility gates. The Python suites also accept
`XRMTOOLS_MSBUILD_PATH` to exercise a desktop MSBuild executable after packing the
local package; that mode is not locally validated.

The Phase 3 scoped adapter is intentionally unchanged except for its warning text.
Other reference-boundary hooks may see a filtered list; successful restoration
appends marked items. The failure test proves that AfterTargets restoration does
not execute on failure, even if a caller continues; reusing that failed project
instance is unsafe. A fresh MSBuild invocation reevaluates all original references
and recovers. No try/finally emulation or extra reference mutation is introduced.

## Why a compiled helper

Built-in MSBuild tasks do not reliably inspect a ZIP's embedded nuspec or compare
NuGet versions across core/desktop runtimes. `tools/netstandard2.0` therefore
contains a small validator plus NuGet.Versioning, and a metadata-only task that
joins resolved build dimensions onto private producer copies. MSBuild framework
and utility assemblies are build-time references only and are supplied at runtime
by the host. The ordinary NuGet package declares **no consumer dependencies**;
no packages/items are added from imported targets, no buildTransitive assets are
shipped, and no shell/Python process is needed by consumers. The redistributed
NuGet.Versioning binary's Apache-2.0 license/attribution is included under licenses.
Python/Node/Bash are
repository test tooling only.
