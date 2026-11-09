# ADR 0001: Extend the Microsoft Dataverse build with a NuGet package

- **Status:** Accepted for the initial implementation
- **Date:** 2026-11-09

## Context

The repository is empty apart from its license. The required build extension must
add optional solution-version handling and, in later phases, plugin-package
integration without owning Microsoft's Dataverse solution build or constraining
the Microsoft package version chosen by each consuming project.

Microsoft.PowerApps.MSBuild.Solution 2.14.1 imports targets from its NuGet package.
Its `CopyCdsSolutionContent` target stages source files into an intermediate
metadata directory; `PowerAppsPackage` then invokes Microsoft's Solution Packager
against that directory. The package also provides a `SolutionVersioningPipeline`
hook after the staging copy and before packaging.

## Decision

Ship `XrmTools.Build` as a normal NuGet package with conventional
`build/XrmTools.Build.props` and `build/XrmTools.Build.targets` assets. Do not define
a replacement MSBuild SDK, fork the Microsoft package, or package a second solution
packager. Keep the Microsoft solution-package reference and version under the
consumer's control.

Initial behavior will be scoped to a `.cdsproj` and version resolution/stamping.
All stamping operates on Microsoft's staged metadata, not on source-controlled
solution files. NBGV is opt-in per solution project. Plugin project build versions
and artifact handling are separate follow-on work and must not inherit the
Dataverse solution version as NuGet `PackageVersion`, `Version`, or `FileVersion`.

### Phase 3 refinement: scoped reference-output adapter

Microsoft's `ProcessCdsProjectReferencesOutputs` calls `GetProjectOutputPath` on
every ProjectReference, ignoring the package marker and ReferenceOutputAssembly.
The extension therefore classifies explicit `XrmToolsPluginPackage=true`
references, preserving metadata and returning them through a public MSBuild
Returns contract. It temporarily filters only these references at Microsoft's
reference-output target boundary and restores them after successful processing.
Normal restore/reference builds retain the references; there is no replacement
Microsoft target, producer-target injection, or additional build/Pack call.

This decision is verified against solution packages 2.13.1 and 2.14.1, including
real PCF reference processing, but remains a version-sensitive adapter. Third-party
hooks can observe the transient list, restored marked items are appended, and a
failed Microsoft target skips restoration in that failed instance. Those risks
and untested IDE/static-graph scenarios are documented in the architecture note.
Phase 3 emits an explicit warning that recognized producer packages are not yet
packed/included; artifact discovery and staging remain later phases.

## Consequences

- Direct `PackageReference` import, build ordering, and package contents must be
  verified against actual restored fixture packages.
- The target names in Microsoft's package are version-sensitive integration
  points. Compatibility claims require a tested matrix, not inference from one
  package.
- The initial host can validate package import and packaging only to the extent
  supported by its installed toolchain. Windows IDE/CI and Dataverse import tests
  remain separate gates.
- Plugin-package discovery and final-ZIP synchronization are not claimed until
  those features are implemented and tested.
