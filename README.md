# XrmTools.Build

`XrmTools.Build` is an additive NuGet build package for Microsoft Dataverse
`.cdsproj` projects. It does not replace Microsoft's solution SDK or packager, and
the consuming project retains control of the
`Microsoft.PowerApps.MSBuild.Solution` version.

## Implemented through Phase 3

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

Explicit plugin-package project references are now classified separately from
unmarked C# and PCF references, with metadata retained and invalid/duplicate
references diagnosed. **This prerelease does not pack, discover, or include their
`.nupkg` files, or stamp `pluginpackage.xml`.** Builds with marked producers emit
`XTB2005` to make that limitation visible. Phase 4 has not been implemented.

## Usage

Keep the Microsoft package version under your control and add XrmTools.Build beside
it:

```xml
<ItemGroup>
  <PackageReference Include="Microsoft.PowerApps.MSBuild.Solution" Version="2.14.1" />
  <PackageReference Include="XrmTools.Build" Version="0.2.0-phase3.1" PrivateAssets="all" />
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
`AdditionalProperties`, and the future `XrmToolsPluginPackagePath` override.
These values are retained, not consumed for package staging in Phase 3. Duplicate
marked paths, duplicate explicit unique names, missing projects, unsupported
producer types, and invalid markers fail clearly. Computed package identities are
not inferred from raw project XML. Producers need not reference XrmTools.Build.

Microsoft calls `GetProjectOutputPath` on every `ProjectReference`, regardless of
`ReferenceOutputAssembly`. The adapter temporarily filters only marked references
for that one Microsoft target, then restores them with their metadata on success.
Normal restore/dependency builds retain the references; no Microsoft target is
replaced and no second producer build is added. Restoration appends the marked
items, so their original interleaving is not guaranteed. Other hooks at this
boundary can observe the temporary list, and a failed Microsoft target prevents
the restoration hook from running in that failed project instance. See the
architecture note before combining this prerelease with other reference-mutating
extensions.

## Build and fixture

Run the package-first regression suite with .NET, Python 3, Node/npm, and standard
shell ZIP utilities:

```sh
./eng/test-package.sh
```

The script packs the local NuGet package and exercises real restored assets,
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
| GitHub Actions / Azure DevOps | Not yet tested |
| Dataverse import or upgrade | Not tested; a successfully packaged ZIP does not prove that replacing an existing server-side plugin package is supported |

This is an early implementation, not a compatibility certification. See
[`docs/architecture.md`](docs/architecture.md) and
[`docs/adr/0001-additive-nuget-build-extension.md`](docs/adr/0001-additive-nuget-build-extension.md)
for verified target ordering, evidence, and limitations.
