# XrmTools.Build

`XrmTools.Build` is an additive NuGet build package for Microsoft Dataverse
`.cdsproj` projects. It does not replace Microsoft's solution SDK or packager, and
the consuming project retains control of the
`Microsoft.PowerApps.MSBuild.Solution` version.

## Initial implementation

The package currently proves conventional NuGet `build/` asset imports and a
per-solution Dataverse version resolver. On a `.cdsproj`, resolution precedence is:

1. `XrmToolsSolutionVersion`, when explicitly set.
2. NBGV `BuildVersion`, only when `XrmToolsUseNbgv=true` and
   `Nerdbank.GitVersioning` is referenced by that solution project.
3. The version already present in `Other/Solution.xml`.

The version must consist of four nonnegative decimal components that fit
`System.Version`'s signed 32-bit components. When NBGV is opted in but its package
is missing or produces no build version, the build fails instead of falling back.
Version stamping modifies only Microsoft's staged
`SolutionPackagerMetadataWorkingDirectory/Other/Solution.xml`; the source manifest
is not rewritten by default.
The resolved value is exposed to later targets in the solution project as
`XrmToolsResolvedSolutionVersion`.

This initial release does not yet discover or stage plugin `.nupkg` files, classify
plugin project references, stamp `pluginpackage.xml`, or validate plugin contents
in the final ZIP. Those are follow-on phases and are not represented as supported
behavior yet.

## Usage

Keep the Microsoft package version under your control and add XrmTools.Build beside
it:

```xml
<ItemGroup>
  <PackageReference Include="Microsoft.PowerApps.MSBuild.Solution" Version="2.14.1" />
  <PackageReference Include="XrmTools.Build" Version="0.1.3" PrivateAssets="all" />
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

The plugin producer's NuGet package version remains independently controlled.
`XrmTools.Build` does not currently pass the Dataverse solution version to producer
projects.

## Build and fixture

The repository's initial integration fixture pins
`Microsoft.PowerApps.MSBuild.Solution` 2.14.1 and builds through Microsoft's
`PowerAppsPackage` target:

```sh
./eng/test-package.sh
```

The script packs the local NuGet package, restores and builds the `.cdsproj`,
checks the final Microsoft-generated ZIP's solution version, and confirms that
the source `Solution.xml` was unchanged. It leaves the local package under
`artifacts/local-feed/`, the isolated NuGet cache under `artifacts/nuget-cache/`,
and the MSBuild binary log under `artifacts/`.

## Supported tooling status

| Environment | Status |
| --- | --- |
| .NET SDK 10.0.403 / MSBuild 18.9.15 on macOS arm64 | Fixture passed with the exact pinned Microsoft package; not a broad platform certification |
| Visual Studio MSBuild on Windows | Not yet tested |
| GitHub Actions / Azure DevOps | Not yet tested |
| Dataverse import or upgrade | Not tested; a successfully packaged ZIP does not prove that replacing an existing server-side plugin package is supported |

This is an early implementation, not a compatibility certification. See
[`docs/architecture.md`](docs/architecture.md) and
[`docs/adr/0001-additive-nuget-build-extension.md`](docs/adr/0001-additive-nuget-build-extension.md)
for verified target ordering, evidence, and limitations.
