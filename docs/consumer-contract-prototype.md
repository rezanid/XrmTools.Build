# Consumer-contract prototype

**Status:** CLI prototype only; no production consumer-contract change is adopted.
The existing package build remains the baseline. This investigation changes no
runtime target behavior except adding an import-only SDK wrapper as an opt-in
packaged experiment and adding a source-driven PCF consumer example alongside
the existing prebuilt test fixture. No package is published or deployed.

## Decision

Keep the conventional `XrmTools.Build` `PackageReference` as the supported
entry point for now. Defer a producer-owned automatic-recognition contract until
it can preserve Microsoft's reference processing without an unsafe workaround.
Do not make the thin SDK the default: it imports the same targets, but does not
remove any execution adapter or consumer configuration, and introduces NuGet
SDK-resolution/source/version-pin concerns outside the project restore graph.
The side-by-side project files are in
[`examples/entry-points`](../examples/entry-points/README.md).

This is not a claim that the desired consumer contract has been achieved. Both
examples still use `XrmToolsPluginPackage=true`; current package-only builds still
need that marker. Adding `XrmTools.Build` to a producer makes its targets
available, but does not by itself establish producer intent or make the current
solution classifier recognize it.

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

The marker-free CLI probe is a concrete negative result. With the recommended
`ReferenceOutputAssembly=false` metadata but no XrmTools marker, the real
Microsoft 2.14.1 reference-processing target fails with `MSB4057` because the
producer project has no `GetProjectOutputPath` target; no ZIP is created. With
the default `ReferenceOutputAssembly=true`, this `.NETStandard` producer instead
fails earlier with `NETSDK1050` on the tested .NET 10 SDK. Neither failure is
hidden by changing target frameworks or consumer projects. These are CLI
observations, not Visual Studio behavior.

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

An opt-in producer-owned capability target is a plausible way to distinguish a
plugin-package producer from an ordinary class library without reading child
project XML or treating `XrmTools.Build`/`PackageId` as classification. A
producer can already own the `XrmToolsGetPluginPackageArtifact` target and return
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
   marker-free probe above demonstrates the missing-target failure for this
   producer, rather than a safe substitute for current staging.
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

The prototype packages `Sdk/Sdk.props` and `Sdk/Sdk.targets` in `XrmTools.Build`.
They import the exact same `build/XrmTools.Build.props` and
`build/XrmTools.Build.targets` files; they contain no second execution pipeline.
The SDK consumer omits the XrmTools `PackageReference`, and neither project
imports the core twice. Both retain an explicit exact Microsoft package version.

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

The two examples use the same producer and source-driven PCF project. The
producer keeps `PackageVersion=2.3.4-beta.1`; the solution version remains an
independent four-part value. Both examples retain the existing per-reference
marker solely because this is the current runnable contract. The target desired
by product direction is proposed, not implemented.

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

The package-first command `./eng/test-package.sh` passed **59 methods**:
16 reference/version, 20 artifact, 14 staging, 6 execution, and 3 consumer
entry-point tests. It covers Restore, Build, repeated Build, Clean/Rebuild,
Debug/Release and reference configuration mapping, producer Pack/NoBuild, final
ZIP package bytes/versions, unchanged source XML, and CLI failure/recovery. The
new reference-hook regression passed before/after ordering and exact once-per-
Build counts over two builds; its hooks observed two unmarked references before
Microsoft processing and all four references after restoration. The SDK and
PackageReference entry points each built with one core import; editing PCF
source changed the final ZIP payload. This is CLI evidence only.

CLI results do not prove Visual Studio target scheduling, NuGet UI behavior,
VS-MSBuild restore source parity, or same-session recovery. These remain pending.
Test the VS-specific questions separately from `.cdsproj` loading, which is
already available through Xrm Tools.

### Prototype delta from baseline

| Surface | Baseline | Prototype result |
| --- | --- | --- |
| Solution entry point | `XrmTools.Build` PackageReference imports the core. | Same PackageReference plus a thin SDK wrapper importing the same core; SDK is optional and not recommended as the default. |
| Producer selection and Microsoft output processing | Explicit marker plus temporary reference filter/restore. | Unchanged; marker-free real-target probe fails, so the proposed capability contract is not adopted. |
| Package freshness | Isolated Pack invocation with private NuGet invalidation. | Unchanged; exact producer path does not prove freshness or remove forced Pack. |
| PCF evidence | Mixed-reference test fixture packages a prebuilt payload. | Separate source-driven consumer example proves source edits change the final ZIP payload through Microsoft PCF targets; not official `pcf-scripts` compilation. |
| Validation and maintenance | Package-first tests exercise current adapters and final ZIP validation. | Adds two entry-point regressions and the source-driven PCF check; runtime execution pipeline is shared, with SDK resolution and wrapper maintenance as new optional costs. |

### Manual Visual Studio gate for Reza

Use a disposable Windows checkout with the intended Visual Studio version,
NuGet tooling and Xrm Tools extension. Capture VS/MSBuild and Microsoft solution
package versions in the result.

1. Open both example solutions. In NuGet UI, add the exact XrmTools and Microsoft
   packages to the PackageReference project; record whether the UI creates
   `<PackageReference>` or `packages.config`. For the SDK example, restore the
   exact SDK package from the configured feed before build.
2. Add the producer and PCF projects using **Add Project Reference**. Build the
   runnable marked example first. Then remove only `XrmToolsPluginPackage=true`
   in a disposable copy and build again. Record reference visibility before and
   after `ProcessCdsProjectReferencesOutputs`, errors, build/Pack counts, and
   whether an ordinary class library stays excluded.
3. Build Debug and Release twice, change producer source and package identity/
   version, and edit `Control/src/index.js`. Verify compile/package counts,
   independent NuGet versions, changed PCF bundle bytes, final ZIP contents and
   exact nested package bytes. Run Clean and Rebuild; compare `dotnet` and VS
   restore source/asset behavior without editing project XML automatically.
4. Enable representative custom BeforeTargets/AfterTargets hooks that log order,
   invocation count and visible references. Force one reference-output failure,
   then remove the failure property and rebuild in the same VS session/project
   context. Record whether state recovers without closing/reloading the project.
5. Capture VS output/error logs, an MSBuild binlog if available, package/project
   assets, ZIP listing plus hashes of embedded `.nupkg` and PCF files, and hashes
   of source manifests before/after. Do not infer this evidence from CLI runs.

Expected baseline behavior: the marked project succeeds; the marker-free copy
is **not** expected to prove the desired contract and must be recorded as a
limitation. The PCF bundle must reflect the edited source. No success claim is
made for NuGet UI, restore-host equivalence, custom hook compatibility or
same-session recovery until this procedure passes on desktop VS.
