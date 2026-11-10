# XrmTools.Build

`XrmTools.Build` is an additive NuGet build package for Microsoft Dataverse
`.cdsproj` projects. It does not replace Microsoft's solution SDK or packager, and
the consuming project retains control of the
`Microsoft.PowerApps.MSBuild.Solution` version.

## Implemented through Phase 6

The package currently proves conventional NuGet `build/` asset imports and a
per-solution Dataverse version resolver. On a `.cdsproj`, resolution precedence is:

1. `XrmToolsSolutionVersion`, when explicitly set.
2. NBGV `BuildVersion`, only when `XrmToolsUseNbgv=true` and
   `Nerdbank.GitVersioning` is referenced by that solution project.
3. The version already present in `Other/Solution.xml`.

The version must consist of four nonnegative decimal components that fit
`System.Version`'s signed 32-bit components. When NBGV is opted in but its package
is missing or produces no build version, the build fails instead of falling back.
Overflow and malformed versions produce XrmTools.Build diagnostics, without
calling `System.Version.Parse`. Version stamping modifies only Microsoft's staged
`SolutionPackagerMetadataWorkingDirectory/Other/Solution.xml`; the source manifest
is not rewritten. `XmlPoke` runs only when the staged version differs from the
resolved version.
The resolved value is exposed to later targets in the solution project as
`XrmToolsResolvedSolutionVersion`.

Explicit plugin-package project references are classified separately from
unmarked C# and PCF references, with metadata retained and invalid/duplicate
references diagnosed. Phase 4 packs producers and validates their exact primary
NuGet artifacts. Phase 5 stages those artifacts, generates or preserves
`pluginpackage.xml`, and synchronizes **all** included plugin XML versions,
including source-only packages. Microsoft creates the solution ZIP; the extension
then validates its manifest, plugin metadata, and exact embedded package bytes.
Only intermediate files are changed.

## Usage

Keep the Microsoft package version under your control and add XrmTools.Build beside
it:

```xml
<ItemGroup>
  <PackageReference Include="Microsoft.PowerApps.MSBuild.Solution" Version="2.14.1" />
  <PackageReference Include="XrmTools.Build" Version="0.5.0-phase6" PrivateAssets="all" />
</ItemGroup>
```

Set a CI override without changing project files:

```sh
dotnet build MySolution.cdsproj -p:XrmToolsSolutionVersion=2.5.100.0
```

For NBGV, add a `Nerdbank.GitVersioning` `PackageReference` to the `.cdsproj` that
owns the Dataverse solution and explicitly opt in:

```xml
<PropertyGroup>
  <XrmToolsUseNbgv>true</XrmToolsUseNbgv>
</PropertyGroup>
<ItemGroup>
  <PackageReference Include="Nerdbank.GitVersioning" Version="3.10.94" PrivateAssets="all" />
</ItemGroup>
```

Without an override or NBGV opt-in, no additional configuration is needed:
`Other/Solution.xml` remains the version source. Each plugin producer independently
owns its NuGet version; XrmTools.Build never sets its `Version`, `PackageVersion`,
or `FileVersion` to the Dataverse solution version.

### Explicit plugin-package references

```xml
<ItemGroup>
  <ProjectReference Include="../Plugin/Plugin.csproj"
                    ReferenceOutputAssembly="false"
                    XrmToolsPluginPackage="true">
    <XrmToolsPluginPackageUniqueName>xt_MyPlugin</XrmToolsPluginPackageUniqueName>
    <ManagedIdentityId>1a71c21a-cd2e-40f0-8a91-a31608d19900</ManagedIdentityId>
    <AdditionalProperties>Configuration=Release</AdditionalProperties>
  </ProjectReference>
  <ProjectReference Include="../Control/Control.pcfproj" />
</ItemGroup>
```

Only the literal marker `true` (case-insensitive) classifies a producer.
Omitted/`false` markers retain Microsoft's behavior. `ReferenceOutputAssembly=false`
is recommended for a package-only dependency; the extension does not set it or
change framework/configuration compatibility rules. Ordinary C# references still
need whatever output contract Microsoft's targets normally require.

`XrmToolsGetPluginPackageProjects` returns `XrmToolsPluginPackageProject` items
through MSBuild's `Returns`/`TargetOutputs` contract. All reference metadata is
preserved, including unique names with publisher prefixes, `ManagedIdentityId`,
`AdditionalProperties`, and the `XrmToolsPluginPackagePath` override.
These values are consumed by solution staging. Duplicate
marked paths, duplicate explicit unique names, missing projects, unsupported
producer types, and invalid markers fail clearly. Computed package identities are
not inferred from raw project XML. Producers need not reference XrmTools.Build.

Microsoft calls `GetProjectOutputPath` on every `ProjectReference`, regardless of
`ReferenceOutputAssembly`. The adapter temporarily filters only marked references
for that one Microsoft target, then restores them with their metadata on success.
Normal restore/dependency builds retain the references; no Microsoft target is
replaced. Restoration appends the marked
items, so their original interleaving is not guaranteed. Other hooks at this
boundary can observe the temporary list, and a failed Microsoft target prevents
the restoration hook from running in that failed project instance. See the
architecture note before combining this prerelease with other reference-mutating
extensions.

### Exact artifact discovery

`XrmToolsDiscoverPluginPackages` returns `XrmToolsPluginPackageArtifact` items:
absolute artifact paths with `ProducerProject`, validated `PackageId`,
`PackageVersion`, `DiscoverySource`, and original reference metadata. It also
runs before Microsoft's solution packager. It processes classified items, not
another edited ProjectReference list.

Discovery runs normal reference prerequisites, then producer `Pack` with
`NoBuild=true`; a multi-target producer's outer build first ensures all frameworks
are available. Configuration, platform and `AdditionalProperties` are preserved.
`BuildProjectReferences=false` requires prebuilt outputs for all package TFMs.
The producer controls its output directory and NuGet version.

Selection precedence is an exact reference `XrmToolsPluginPackagePath`, then an
optional producer `XrmToolsGetPluginPackageArtifact` target, then NuGet's internal
`_GetOutputItemsFromPack` adapter. No output-directory search is performed.
The selected ZIP's nuspec must match the expected identity/version, and symbols
packages are excluded. Explicit paths are solution-relative; producer-returned
paths are producer-relative (absolute paths work in both).

**The internal adapter is best-effort, not a public NuGet contract.** An isolated
producer import forces NuGet packaging to execute, with `NoBuild=true`, and returns
evaluated identity/naming settings alongside its predicted paths. Normal unchanged
builds therefore succeed without an explicit contract; compilation remains
incremental, but producer packaging is deliberately regenerated. No timestamp is
used as artifact proof. Versionless/custom-nuspec naming still requires a producer
return contract or exact path, because the installed internal target can predict
incorrect paths. Explicit paths are authoritative and do not probe lower-priority
producer-return targets; missing expected metadata must come from unambiguous
evaluated producer identity or be supplied explicitly.

See [artifact discovery](docs/artifact-discovery.md) for executable fallback
examples, expected-identity metadata, diagnostics, and the tested matrix.

### Staging and final ZIP validation

`XrmToolsStagePluginPackages` consumes only the validated
`XrmToolsPluginPackageArtifact` items. Explicit publisher-prefixed unique names
are preserved; otherwise the solution publisher prefix is prepended to the
validated NuGet ID (unless already present). An existing staged XML's package
filename, display name, IDs, flags, namespaces, encoding, and unknown fields are
preserved. An explicit reference `ManagedIdentityId` overrides the nested GUID;
omitting it preserves an existing identity. New metadata uses customizable,
active defaults and a filename matching the unique name.

Pre-existing source-only packages are included and stamped too, without
repacking or modifying their source archives. Missing/extra packages, malformed
XML, unsafe paths, identity errors, and duplicates fail the build. The final
`XrmToolsValidatePackage` hook checks Microsoft's actual Unmanaged, Managed, or
Both outputs, including custom ZIP paths. It rejects missing, additional,
duplicate, or changed plugin entries; an old ZIP left by a failed build is not
reported as a successful output.

Staging must be strictly inside `IntermediateOutputPath` and disjoint from
`SolutionRootPath`, without symlinks/reparse points in either tree. The Microsoft
metadata stage is exclusively intermediate build content, not a producer output
directory. A narrow pre-copy reset of staged `pluginpackages` prevents leftovers
from failed builds being silently included. User NuGet output directories remain
untouched. See [staging](docs/plugin-package-staging.md) for the exact contract,
diagnostics, overhead, and [complete pipeline review](docs/architecture.md#phases-05-architectural-review).

## Build and fixture

For runnable project files, see the packaged [solution/producer example](examples/README.md).
This prerelease is unpublished; the example documents local-feed use. It proves
packaging plumbing, not Dataverse registration/import support.

### Execution and troubleshooting

Use `dotnet build MySolution.cdsproj` to create the solution ZIP. The tested
Microsoft solution SDKs have **no NuGet Pack target** on `.cdsproj`.
Restore and `XrmToolsPrintConfiguration` / `XrmToolsGetPluginPackageProjects` do
not build or pack producers; discovery and staging targets intentionally do.
`NoBuild=true` alone is not a solution skip switch. With
`BuildProjectReferences=false`, all reference outputs must already exist for the
same build dimensions; producer packaging is still regenerated and validated.

Clean uses Microsoft's existing pipeline, including recursive deletion of its
configured output/intermediate/working directories. Keep user NuGet stores
separate from those directories; XrmTools.Build adds no package-store cleanup.
Concurrent shared-output writers (including Clean alongside Build) are
unsupported: isolate every project's intermediate, compile, NuGet, ZIP and log
paths. See the [complete execution table and isolation example](docs/execution.md),
[troubleshooting by diagnostic](docs/troubleshooting.md) and
[release notes](docs/release-notes.md).

Run the package-first regression suite with .NET, Python 3, Node/npm, and Bash:

```sh
./eng/test-package.sh
```

The script packs the local NuGet package, checks its README/license metadata,
build assets and helper DLLs, builds the extracted example, and exercises real restored assets,
version precedence/no-op stamping, invalid input, and mixed references with zero,
one, and two producers. It checks recursive NuGet restore graphs, metadata/build
dimensions, single producer builds, and Microsoft's final solution ZIP, including
the PCF payload and unchanged source XML. The PCF fixture uses Microsoft's PCF
targets with a dependency-free prebuilt payload, not a TypeScript compiler.
It leaves the local package under
`artifacts/local-feed/`, the isolated NuGet cache under `artifacts/nuget-cache/`,
and fixture copies, logs, binlogs, and restore graphs under `artifacts/`.
Generated output is ignored. `python3 eng/test-targets.py` reruns target/integration
tests after that local package has been built and restored.
`python3 eng/test-artifacts.py` exercises Phase 4, including custom nuspecs,
versionless output, symbols, NBGV, multi-target builds, invalid/ambiguous/missing
artifacts, and Phase 3 failure recovery. `python3 eng/test-staging.py` exercises
metadata preservation, source-only packages, configuration/version transitions,
failure recovery, path safety, managed/Both outputs, and final-ZIP tampering.
`python3 eng/test-execution.py` covers cold/warm Restore and read-only queries,
Clean/recovery/Rebuild with user package stores, solution Pack/NoBuild semantics
and simultaneous same-source builds with isolated per-run/per-project paths.
The suite includes repeated actual
`dotnet build` calls with changed code/payloads, and passes locally on the tooling
below. Hosted results are recorded with the pull request.

The extension depends on Microsoft's `CopyCdsSolutionContent`,
`ProcessCdsProjectReferencesOutputs`, `PowerAppsPackage`, and
`SolutionPackagerMetadataWorkingDirectory` staging contract. It diagnoses missing
staging/imports, missing manifest data, and conflicting `SolutionVersionStrategy`
configuration. It deliberately does not enforce a Microsoft package version
range; changed/missing target definitions still require compatibility investigation.

## Supported tooling status

| Environment | Status |
| --- | --- |
| .NET SDK 10.0.403 / MSBuild 18.9.15 on macOS arm64 | Real packaging passed with Microsoft solution packages 2.13.1 and 2.14.1, and PCF package 2.14.1; not a broad platform certification |
| Visual Studio MSBuild on Windows | Not yet tested |
| Linux; IDE design-time/static-graph builds; other Microsoft versions | Not yet tested |
| GitHub Actions / .NET 10.0.x on Windows and macOS | Phase 5's 48 methods passed in [run 42778369512](https://github.com/rezanid/XrmTools.Build/actions/runs/42778369512), with both Microsoft solution versions. Phase 6 results are recorded in its pull request; a workflow definition alone is not passing evidence |
| Azure DevOps | Not yet tested |
| Dataverse import or upgrade | Not tested; a successfully packaged ZIP does not prove that replacing an existing server-side plugin package is supported |

This is an early implementation, not a compatibility certification. See
[`docs/architecture.md`](docs/architecture.md) and
[`docs/adr/0001-additive-nuget-build-extension.md`](docs/adr/0001-additive-nuget-build-extension.md)
for verified target ordering, evidence, and limitations.
