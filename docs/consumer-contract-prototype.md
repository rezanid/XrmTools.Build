# Consumer-contract prototype

**Status:** CLI prototype only; no production consumer-contract change is adopted.
The default package retains explicit-marker classification. Separate, distinctly
versioned local artifacts enable evaluated producer recognition and an import-only
SDK wrapper. Neither experiment is in the default package. No package is published
or deployed. The revision started with a clean branch at the reviewed `5a22cf9`;
local and remote heads matched, with no subsequent changes to overwrite.

## Decision

Keep the conventional `XrmTools.Build` `PackageReference` as the supported
entry point. Automatic recognition works in the experiment when the solution's
framework is compatible with the PAC producer, **without reference metadata**.
It does not by itself make a default net462 solution compatible with PAC's net48
producer, nor make ordinary class libraries valid Microsoft solution outputs.
Defer production adoption until these consumer and VS gates are resolved.
Do not make the thin SDK the default: it imports the same targets, but does not
remove any execution adapter or consumer configuration, and introduces NuGet
SDK-resolution/source/version-pin concerns outside the project restore graph.
The side-by-side project files are in
[`examples/entry-points`](../examples/entry-points/README.md).

**Separate answers:** the marker can be removed for a Microsoft plugin-package
producer in the framework-compatible recognition experiment. Neither the scoped
reference filter nor the isolated Pack adapter can be removed on this evidence.
The default package and the original entry-point comparison still use markers.

## Baseline and evidence

The starting tree was clean at `8556e38`, equal to `origin/main`. The planning
commit later merged as `b7b42c6` was fetched during this investigation and
preserved by rebasing the feature branch onto the updated remote main. The dated
`docs/vs-smoke-test-2026-11-10.md` file was absent from both main and the planning
branch. The planning document and `AGENTS.md` from the documentation branch are
now present in the feature branch; the missing VS report is not reconstructed or
treated as evidence.

The baseline `./eng/test-package.sh` passed all **55 methods** on macOS arm64:
15 target/reference/version tests, 20 artifact tests, 14 staging tests, and 6
execution tests. The package-first run used .NET SDK **10.0.403**, MSBuild
**18.9.15.52412**, Python **3.9.6**, Node **22.4.0**, npm **10.8.1**, and
Microsoft solution packages **2.13.1** and **2.14.1**. The mixed-reference
fixture used Microsoft PCF targets **2.14.1**, but its prebuilt control payload
was insufficient evidence for source-change scheduling; the prototype adds a
source-driven PCF build and regression.

The completed baseline CI run is
[Package regression 42791867282](https://github.com/rezanid/XrmTools.Build/actions/runs/42791867282)
on commit `0585e9d`; both Windows and macOS CLI jobs passed. This is evidence for
the then-current baseline only, not for desktop Visual Studio or the prototype
changes. No desktop Visual Studio/MSBuild executable or VS application was
available in this macOS worktree.

The prototype PCF example uses Microsoft PCF targets 2.14.1 to schedule its
source-driven build. Its small Node build script copies the manifest and
JavaScript source into the expected output; it is not the official
`pcf-scripts`/TypeScript compilation pipeline. The existing mixed-reference
fixture still uses its prebuilt PCF payload and was not changed.

The two pinned entry-point examples built through the same targets, and the
SDK project's preprocessed graph contained one definition each of
`XrmToolsGetPluginPackageProjects`, `XrmToolsDiscoverPluginPackages`, and
Microsoft's `ProcessCdsProjectReferencesOutputs`. The SDK project assets did not
contain `XrmTools.Build`; its package was resolved by the SDK resolver from the
configured NuGet source. Both builds embedded the exact producer `.nupkg` bytes
and source-generated PCF bundle; editing `Control/src/index.js` changed the
final ZIP bundle bytes. Source `Solution.xml` remained unchanged.

The original marker-free CLI probe remains baseline evidence, not the recognition
experiment. With the recommended
`ReferenceOutputAssembly=false` metadata but no XrmTools marker, the real
Microsoft 2.14.1 reference-processing target fails with `MSB4057` because the
producer project has no `GetProjectOutputPath` target; no ZIP is created. With
the default `ReferenceOutputAssembly=true`, this `.NETStandard` producer instead
fails earlier with `NETSDK1050` on the tested .NET 10 SDK. Neither failure is
hidden by changing target frameworks or consumer projects. These are CLI
observations, not Visual Studio behavior. That producer does **not** import
Microsoft plugin targets; its missing output target is not evidence that a
PAC-generated producer lacks that target.

## Evaluated recognition experiment (PR #5 revision)

PAC **2.14.1+g6f517e5** (`.NET 10.0.2`) generated
[`examples/automatic/Plugin/Plugin.csproj`](../examples/automatic/Plugin/Plugin.csproj)
using `pac plugin init --outputDirectory examples/automatic/Plugin --author XrmTools --skip-signing`.
The generated project/source/imports are retained; floating package references
were pinned and the experimental XrmTools PackageReference added. This unsigned
fixture is build evidence, not Dataverse registration/deployment certification.
The restored versions are Microsoft plugin targets **1.52.1**, CRM SDK core
assemblies **9.0.2.60**, and .NET Framework reference assemblies **1.0.3**.
The solution matrix is **2.13.1/2.14.1**, with PCF targets **2.14.1**.
`pac solution init --publisher-name XrmTools --publisher-prefix xt` was also
run in an ignored output directory to verify that this PAC version still
generates the net462/v4.6.2 solution defaults.

`XrmToolsGetProducerCapability` returns the evaluated producer path only when
`PowerAppsComponentType=Plugin` (set by Microsoft's plugin targets) and
`IsPackable!=false`. The solution queries that target on unmarked `.csproj`
references using the MSBuild task, then joins returned paths to copies of the
original references. No raw child XML, PackageId heuristic, Build, Pack, output
scan, or fake output is involved. Projects without the query target return no
capability through `SkipNonexistentTargets`; errors from existing targets are
not suppressed. Explicit `XrmToolsPluginPackage=false` opts out; explicit true
and identity/path/name overrides retain their current precedence.

No reference metadata is added. Only classified references enter the existing
scoped filter; ordinary/PCF references and their metadata are not changed.
Recognition requires restored imports: a first restore establishes the real
graph, and a subsequent capability query is read-only. This is not a new
restore-time framework repair mechanism.

| Case (both solution versions unless noted) | First boundary/result |
| --- | --- |
| Default net462 solution + PAC net48 producer + plain refs, including PCF/ordinary library | NuGet `Restore`/`RestoreTask` reports `NU1201` on the Plugin net48 graph edge. No Build/Pack or ZIP. The failure precedes reference build resolution, Microsoft output processing and packaging; recognition does not fix framework compatibility. |
| Disposable solution set to net48/v4.8 only, matching the generated producer | Fresh restore succeeds; read-only recognition returns only Plugin. Plain plugin + PCF references build the correct ZIP. No marker, explicit unique name, ReferenceOutputAssembly or replacement consumer opt-in property. |
| Same compatible solution plus ordinary net462 library with XrmTools.Build and `PackageId=Ordinary.NotAPlugin` | Restore/query succeed; only Plugin is classified. `ProcessCdsProjectReferencesOutputs` calls `GetProjectOutputPath` on the remaining ordinary library and fails `MSB4057`. A Microsoft-only mixed-reference comparison fails at the same target. No ZIP; the library is not silently removed to make the experiment pass. |
| Microsoft-only compatible plugin + PCF (2.14.1) | Real plugin `GetProjectOutputPath` returns Plugin.dll tagged `PowerAppsComponentType=Plugin`. Microsoft's processing task then fails because no assembly registration configuration exists under `PluginAssemblies`. This is a package producer, not a preconfigured individual-assembly component. |

The compatible-framework test edits **only its disposable solution's** framework
properties; it is a controlled follow-on to `NU1201`, not a broad global-property
override, RID change, automatic consumer rewrite, or claim that arbitrary
framework changes are safe. The checked-in automatic example deliberately retains
the default net462 solution to reproduce the first failure.

### Package bytes, compilation and custom hooks

For each Microsoft solution version, `eng/test-recognition.py` runs a fresh
compatible build, unchanged Build, and Build after editing plugin and PCF source.
Every ZIP embeds exactly the producer's `Plugin.1.0.0.nupkg`; after the edit its
compiled assembly and embedded package bytes change. The unchanged Build retains
both assembly bytes and modification time. Solution/plugin metadata is 4.5.6.7,
independent of producer version 1.0.0. No explicit unique name is needed:
staging derives `xt_Plugin` from publisher prefix `xt` and validated PackageId.

Hooks installed through ordinary `Directory.Build.targets` observe:

| Hook/adapter per successful Build | Observed count/effect |
| --- | --- |
| Scoped filter, Microsoft reference processing, restore | Once each. Before-processing hook sees only PCF; after-restoration hook sees PCF then Plugin. Original Plugin/PCF order is changed by append restoration, as in the marked baseline. A custom reference metadata value added after recognition survives the boundary. |
| Producer Before/After Pack | Two pairs: Microsoft's `GeneratePackageOnBuild=true` normal Pack, then isolated `NoBuild=true` Pack. The second reports `_XrmToolsPackInvalidated=true`; the normal one does not. |
| Private NuGet invalidation/discovery | One isolated invalidation per Build; `_GetOutputItemsFromPack` selection/evidence still runs. Recognition is not a package-output or freshness contract. |
| Read-only recognition after Restore | No producer bin directory, package or Pack hook log; graph retains plugin, ordinary and PCF projects. |

These are representative, explicitly ordered hooks, not proof that arbitrary
custom hook placement has identical reference visibility. In the mixed failure,
the restoration AfterTarget does not run; failed in-memory state/recovery remains
a gate. Repeating fresh CLI invocations does not establish same-session recovery.

### Implemented baseline behavior and trade-offs

| Area | Implemented behavior | Observable trade-off |
| --- | --- | --- |
| Reference classification | Only a solution `ProjectReference` with `XrmToolsPluginPackage=true` is classified. Restore/reference builds still see it. | Marker XML is required today; PackageReference or PackageId alone does not classify. |
| Microsoft output processing | Save and temporarily remove only marked project references before `ProcessCdsProjectReferencesOutputs`; restore after success. | Microsoft calls `GetProjectOutputPath` on every reference, ignoring `ReferenceOutputAssembly`. Other hooks can observe the filtered set; restored references append to the list; a failed target does not run the restoration hook in that failed project instance. |
| NuGet package freshness | Build producers normally, then run isolated `Pack` with `NoBuild=true`; a private producer import invalidates NuGet's incremental Pack input and chains existing custom after-target imports. | Compile remains incremental, but packaging runs again on every solution build; `GeneratePackageOnBuild` may cause an additional Pack. The isolated adapter relies on private NuGet target/input behavior. |
| Exact artifact discovery | Explicit exact path, producer `XrmToolsGetPluginPackageArtifact` target, or NuGet `_GetOutputItemsFromPack`; validate the exact archive nuspec and identity/version. | Producer return can skip `_GetOutputItemsFromPack` discovery, but the normal path still runs Pack through the isolated freshness adapter first. A path alone is not freshness evidence. |
| Intermediate cleanup | Reset only the intermediate `pluginpackages` before Microsoft's source overlay; stage validated packages and preserve metadata; validate the final Microsoft ZIP. | Adds a narrow owned-intermediate filesystem side effect and fails if staging is outside intermediate, overlapping source or traverses links. Microsoft remains the ZIP engine. |
| Project versions | Solution version is explicit override, opted-in NBGV, then source manifest; producer NuGet versions remain producer-owned. | NBGV currently requires explicit solution opt-in, unlike its normal package/configuration-only experience. The prototype does not broaden this behavior. |

The exact implementation and evidence are in
[`architecture.md`](architecture.md), [`artifact-discovery.md`](artifact-discovery.md),
[`plugin-package-staging.md`](plugin-package-staging.md), and
[`execution.md`](execution.md).

## Producer-owned capability and artifact contract

The recognition artifact implements the capability query described above,
without treating `XrmTools.Build`/`PackageId` alone as classification. Separately,
a producer can already own the `XrmToolsGetPluginPackageArtifact` target and return
one exact path plus `PackageId` and `PackageVersion`. This avoids guessing output
paths and can avoid the private `_GetOutputItemsFromPack` prediction when the
target returns complete metadata.

That is not enough to replace the current adapters:

1. Microsoft `ProcessCdsProjectReferencesOutputs` evaluates
   `@(ProjectReference)` and invokes `GetProjectOutputPath` on each reference.
   The restored 2.13.1 and 2.14.1 targets do not filter on
   `ReferenceOutputAssembly` or a producer capability. A producer-owned package
   artifact target is not called by Microsoft's target. Without filtering, the
   ordinary project output is still sent to Microsoft's output contract; the
   original non-PAC marker-free probe demonstrates a missing-target failure;
   the real PAC producer instead reaches Microsoft's assembly-registration
   requirement. Neither supplies the package staging contract.
2. Discovering capability before that target and omitting only the producer
   output still requires a temporary filter unless Microsoft exposes a supported
   per-reference output-target contract. Replacing Microsoft's target or using a
   dummy output is rejected. Setting `ReferenceOutputAssembly=false` does not
   change the inspected target call.
3. Returning a package path does not prove that the package is current. Existing
   equal-size/equal-time payload and stale-output regressions require Pack to
   regenerate without sacrificing compilation incrementality. The current
   standard-NuGet path forces that through an isolated producer import. A custom
   producer can own its own fresh-package target, but the prototype has no
   generic independently validated producer contract that proves its output is
   current for source/content, identity/version and configuration changes.
4. The current exact producer-return contract can remove the internal
   `_GetOutputItemsFromPack` **selection fallback** for that producer. It does not
   remove the isolated Pack invocation or its private invalidation mechanism.
   Removing either is not established by this prototype.

Consequently, do not claim the reference filter or forced Pack adapter has been
eliminated. Keep these compromises explicit until a concrete, tested producer
contract plus Microsoft's reference-output integration demonstrates otherwise.

## Entry-point comparison

The default package contains **no** `Sdk/` or recognition asset. The opt-in pack
options below create separate exact prerelease versions in the local feed:

```sh
dotnet pack XrmTools.Build.csproj -o artifacts/local-feed
dotnet pack XrmTools.Build.csproj --no-build -o artifacts/local-feed \
  -p:XrmToolsPrototypeSdk=true -p:PackageVersion=0.5.0-sdk-prototype
dotnet pack XrmTools.Build.csproj --no-build -o artifacts/local-feed \
  -p:XrmToolsPrototypeRecognition=true -p:PackageVersion=0.5.0-recognition
```

Prototype pack refuses the default package version. Tests inspect all three
archives, reject SDK/recognition assets in the default, verify the expected
experimental assets and shared core bytes, and clear only each named experimental
version from the repository-local cache after repacking. The SDK example pins
`Sdk="XrmTools.Build/0.5.0-sdk-prototype"`; the recognition example references
`0.5.0-recognition`. Thus NuGet cannot substitute the default artifact for either.

The SDK experiment packages `Sdk/Sdk.props` and `Sdk/Sdk.targets`.
They import the exact same `build/XrmTools.Build.props` and
`build/XrmTools.Build.targets` files; they contain no second execution pipeline.
The SDK consumer omits the XrmTools `PackageReference`, and neither project
imports the core twice. Both retain an explicit exact Microsoft package version.
This wrapper supplies **only import forwarding**: Microsoft package references,
Common.props/Common.targets imports and project defaults stay in the consumer.
It does not test a convenience SDK that supplies sensible project defaults.

| Cost | PackageReference | Thin versioned SDK |
| --- | --- | --- |
| Solution integration | One ordinary package reference alongside Microsoft tooling. Package version can use Central Package Management and participates in the restore graph/lock file. | One `Sdk="XrmTools.Build/<exact-version>"` root attribute imports the same core. SDK version must be changed in the project attribute. |
| Microsoft tooling | Exact `Microsoft.PowerApps.MSBuild.Solution` PackageReference and version remain visible in the project/central package file. | Same. The SDK does not select or replace the Microsoft package. |
| Restore/reproducibility | Package graph can be locked with `packages.lock.json` and locked restore. | Exact SDK version and configured trusted source are needed during SDK resolution before project restore; SDK resolver source/cache state is separate from project package lock. |
| Plugin producer and PCF | Producer PackageReference is separate. PCF remains a normal Microsoft PCF project. | Unchanged; SDK does not simplify producer participation, PCF scheduling or VS project behavior. |
| Build execution and maintenance | Imports core build targets once. | Imports the same core files once; adds two wrappers, SDK package resolution and separate source/version diagnostics, with no removal of adapters or target complexity. |

No measured build behavior or setup outcome justifies changing the default to the
SDK. The wrapper remains an experiment for consumers who already standardize on
NuGet-distributed MSBuild SDKs; it is not evidence that an SDK is beneficial for
the general consumer.

## Current minimum consumer files

The full runnable project files and setup are kept in the repository examples,
not duplicated here:

- [`PackageReference/Solution.cdsproj`](../examples/entry-points/PackageReference/Solution.cdsproj)
- [`Sdk/Solution.cdsproj`](../examples/entry-points/Sdk/Solution.cdsproj)
- [`entry-points README`](../examples/entry-points/README.md)

The two original entry-point examples use the same producer and source-driven PCF project. The
producer keeps `PackageVersion=2.3.4-beta.1`; the solution version remains an
independent four-part value. Both examples retain the existing per-reference
marker solely because this is the current runnable contract. The target desired
by product direction is implemented only in the distinct recognition experiment
with the limitations above.

### Minimal plain-reference consumer (compatible-framework diagnostic)

The complete default-failure example is
[`automatic/Solution.cdsproj`](../examples/automatic/Solution.cdsproj). For the
most promising tested configuration, a deliberately net48 solution is:

```xml
<Project ToolsVersion="15.0" DefaultTargets="Build"
         xmlns="http://schemas.microsoft.com/developer/msbuild/2003">
  <Import Project="$(MSBuildExtensionsPath)/$(MSBuildToolsVersion)/Microsoft.Common.props" />
  <PropertyGroup>
    <TargetFrameworkVersion>v4.8</TargetFrameworkVersion>
    <TargetFramework>net48</TargetFramework>
    <RestoreProjectStyle>PackageReference</RestoreProjectStyle>
    <SolutionRootPath>../Solution/src</SolutionRootPath>
  </PropertyGroup>
  <ItemGroup>
    <PackageReference Include="Microsoft.NETFramework.ReferenceAssemblies" Version="1.0.3" PrivateAssets="all" />
    <PackageReference Include="Microsoft.PowerApps.MSBuild.Solution" Version="2.14.1" />
    <PackageReference Include="XrmTools.Build" Version="0.5.0-recognition" PrivateAssets="all" />
    <ProjectReference Include="Plugin/Plugin.csproj" />
    <ProjectReference Include="../Control/ExampleControl.pcfproj" />
  </ItemGroup>
  <Import Project="$(MSBuildToolsPath)/Microsoft.Common.targets" />
</Project>
```

The PAC producer keeps its Microsoft-generated imports and properties; add only
`<PackageReference Include="XrmTools.Build" Version="0.5.0-recognition" PrivateAssets="all" />`
alongside the pinned Microsoft plugin references. No marker or replacement opt-in
property is added. Full producer XML is linked above. PCF retains its own Microsoft
package/build setup; it does not need XrmTools.Build. The ordinary-library project
is present separately so tests can add it with one plain reference and demonstrate
the preserved Microsoft failure rather than advertising an unbuildable mixed ZIP.

For reproducible consumer restore, pin Microsoft/XrmTools/NBGV package versions
and check in lock files where supported. The package-only entry point can use
Central Package Management and `RestoreLockedMode=true`; do not use floating
versions as a compatibility claim. With the SDK entry point, pin the SDK version
in the `Sdk` attribute and keep the SDK package source explicit and trusted.
Microsoft package-version overrides are consumer-owned; test each selected
version. No broad RID/framework changes or project-file rewrites are prescribed.

The example's unpublished local `XrmTools.Build` package is not represented by a
checked-in lock file: repeated `dotnet pack` runs have identical package entry
contents but different ZIP timestamps and therefore different package content
hashes. A published immutable package version can be locked normally. The SDK
resolver's package itself is not part of the solution project's PackageReference
lock graph; pin its exact version and source independently.

## Validation and remaining risks

At reviewed commit `5a22cf9`, `./eng/test-package.sh` passed **59 methods**:
16 reference/version, 20 artifact, 14 staging, 6 execution, and 3 consumer
entry-point tests. It covers Restore, Build, repeated Build, Clean/Rebuild,
Debug/Release and reference configuration mapping, producer Pack/NoBuild, final
ZIP package bytes/versions, unchanged source XML, and CLI failure/recovery. The
new reference-hook regression passed before/after ordering and exact once-per-
Build counts over two builds; its hooks observed two unmarked references before
Microsoft processing and all four references after restoration. The SDK and
PackageReference entry points each built with one core import; editing PCF
source changed the final ZIP payload. This is CLI evidence only.

Revision checks add five recognition methods (each applicable matrix runs
2.13.1/2.14.1) and fix the source-preservation regression: each entry-point build
now captures and compares the bytes of the **disposable fixture's** `Solution.xml`,
including the PCF edit/rebuild. It no longer hashes the untouched repository copy.
Exact revision commands/results, final commit and CI links are recorded in the
PR description. Local versions remain .NET SDK 10.0.403, MSBuild 18.9.15.52412,
Python 3.9.6, Node 22.4.0 and npm 10.8.1. CLI support evidence is limited to the
tested Microsoft versions/hosts; desktop VS, other SDK versions, static graph,
design-time and Dataverse import/upgrade are not certified.

The revision's canonical validation/commit record is
[PR #5](https://github.com/rezanid/XrmTools.Build/pull/5); its description records
the final pushed SHA and exact Windows/macOS run links so this document does not
embed a self-referential commit hash. The baseline reviewed commit's
[Windows/macOS CI](https://github.com/rezanid/XrmTools.Build/actions/runs/42908863780)
passed, but is not validation of the revision.

CLI results do not prove Visual Studio target scheduling, NuGet UI behavior,
VS-MSBuild restore source parity, or same-session recovery. These remain pending.
Test the VS-specific questions separately from `.cdsproj` loading, which is
already available through Xrm Tools.

### Prototype delta from baseline

| Surface | Baseline | Prototype result |
| --- | --- | --- |
| Solution entry point | `XrmTools.Build` PackageReference imports the core. | Same PackageReference. A separate SDK artifact forwards the same imports; it is not included in the default package and not recommended as the default. |
| Producer selection and Microsoft output processing | Explicit marker plus temporary reference filter/restore. | Distinct experimental package recognizes Microsoft plugin capability with plain refs; same scoped filter/restore remains. Default net462/net48 restore and ordinary-library output limitations remain visible. |
| Package freshness | Isolated Pack invocation with private NuGet invalidation. | Unchanged; exact producer path does not prove freshness or remove forced Pack. |
| PCF evidence | Mixed-reference test fixture packages a prebuilt payload. | Separate source-driven consumer example proves source edits change the final ZIP payload through Microsoft PCF targets; not official `pcf-scripts` compilation. |
| Validation and maintenance | Package-first tests exercise current adapters and final ZIP validation. | Adds two entry-point regressions and the source-driven PCF check; runtime execution pipeline is shared, with SDK resolution and wrapper maintenance as new optional costs. |

### Manual Visual Studio gate for Reza

`.cdsproj` loading through Xrm Tools is solved; do not retest it as the blocker.
In a disposable Windows checkout, pack `0.5.0-recognition`, configure that local
feed, and use the explicit net48 solution above with the PAC net48 producer.
Install XrmTools.Build **through NuGet UI** on both projects (record whether it
creates PackageReference or packages.config), add producer and PCF through
ordinary **Add Project Reference**, and build from clean outputs. Edit plugin
code and PCF source, rebuild, then induce a reference-output failure by adding
the ordinary library; remove that reference and retry in the **same VS session**
without reload. Do not add marker/ReferenceOutputAssembly metadata to rescue it.

Capture VS/NuGet/MSBuild/package versions, output log/binlog and restore assets.
Inspect capability classification, first failing target if any, filtered/restored
reference order and two Pack pairs (one isolated) per successful Build; the
unchanged build must not recompile the producer. Inspect final ZIP
`pluginpackages/xt_Plugin/package/xt_Plugin.nupkg` byte-for-byte against the producer
package, metadata version, changed PCF bundle, and unchanged source Solution.xml.
Record whether retry recovered; an old ZIP after failure is not success.
The checked-in JavaScript PCF script proves CLI source scheduling only. Repeat
the source-edit step with an actual PAC TypeScript/pcf-scripts control before
claiming real PCF/VS scheduling support. All these desktop gates remain pending.
