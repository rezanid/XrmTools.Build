# Development-only package installation and producer dependencies

## Finding and scoped change

XrmTools.Build is a build tool, not a plugin runtime dependency. Its package
project now sets `DevelopmentDependency=true`; the packed root nuspec contains
`<developmentDependency>true</developmentDependency>`. Previously that element
was absent, including from the locally reproduced recognition artifact.
`SuppressDependenciesWhenPacking=true` in our package project only prevents
**our own** dependencies from being declared; it does not prevent another
package from depending on XrmTools.Build.

The supported package-authoring flag lets installation clients author the right
consumer metadata. It does **not** make NuGet Pack filter every plain reference
to a development package. No imported targets, producer reference metadata,
recognition defaults, reference adapters, runtime dependencies, consumer source
files or archive post-processing are changed by this fix.

## NuGet owns the installation boundary

The official [nuspec reference](https://learn.microsoft.com/en-us/nuget/reference/nuspec#developmentdependency)
and [PackageReference documentation](https://learn.microsoft.com/en-us/nuget/consume-packages/package-references-in-project-files#controlling-dependency-assets)
describe development-only packages and compile-asset exclusion. The more precise
[NuGet PackageReference design](https://github.com/NuGet/Home/wiki/DevelopmentDependency-support-for-PackageReference)
distinguishes installation from manually authored references:

- VS NuGet UI/PMC and `dotnet add package` use the package's flag to write
  `PrivateAssets=all` and include all assets except compile.
- A manually added PackageReference is treated normally. Existing references
  are not retroactively made private merely by restoring or packing.
- Consumers can explicitly override asset metadata.

Inspected NuGet.Client source at commit
`fa47ca47d40afefad3cecf03ea116c2134f0f826`:

| Component | Relevant behavior |
| --- | --- |
| [BuildIntegratedRestoreUtility.UpdatePackageReferenceMetadata](https://github.com/NuGet/NuGet.Client/blob/fa47ca47d40afefad3cecf03ea116c2134f0f826/src/NuGet.Core/NuGet.PackageManagement/BuildIntegration/BuildIntegratedRestoreUtility.cs#L150-L200) | Reads the installed nuspec flag and changes default dependency flags to suppress all parent assets and exclude compile; preserves non-default consumer flags. |
| [CpsPackageReferenceProject.ApplySuppressParentAndIncludeTypeAsync](https://github.com/NuGet/NuGet.Client/blob/fa47ca47d40afefad3cecf03ea116c2134f0f826/src/NuGet.Clients/NuGet.PackageManagement.VisualStudio/Projects/CpsPackageReferenceProject.cs#L340-L357) | Writes installation-context flags as PrivateAssets and IncludeAssets in the project. This is the VS CPS installation path, not an XrmTools build hook. |
| [AddPackageReferenceCommandRunner](https://github.com/NuGet/NuGet.Client/blob/fa47ca47d40afefad3cecf03ea116c2134f0f826/src/NuGet.Core/NuGet.CommandLine.XPlat/Commands/PackageReferenceCommands/AddPackageReferenceCommandRunner.cs#L380-L425) | CLI installation reads the flag and applies the same default-metadata rule. |
| [PackTaskLogic.InitializePackageDependencies](https://github.com/NuGet/NuGet.Client/blob/fa47ca47d40afefad3cecf03ea116c2134f0f826/src/NuGet.Core/NuGet.Build.Tasks.Pack/PackTaskLogic.cs#L990-L1032) | Gets direct dependencies from the restored project spec, rather than filtering them by each dependency's developmentDependency flag. |
| [PackCommandRunner.AddDependencyGroups](https://github.com/NuGet/NuGet.Client/blob/fa47ca47d40afefad3cecf03ea116c2134f0f826/src/NuGet.Core/NuGet.Commands/CommandRunners/PackCommandRunner.cs#L316-L335) | Omits dependencies with SuppressParent=All, the internal representation of PrivateAssets=all. |

These are source observations, not proof of the particular installed VS build.
The installed CLI behavior below independently confirms the installation/Pack
boundary (PackageReference support for this flag requires NuGet 4.8+).
Compile exclusion does not hide the tool's task assemblies: they are
packaged under `tools/`, not consumer compile assets under `lib/`.

## Observed before/after

The Windows smoke fixture was inspected **read-only** through the Parallels
mount. Its plugin project had:

```xml
<PackageReference Include="XrmTools.Build" Version="0.5.0-recognition" />
```

Both `PluginPackage/bin/Debug/PluginPackage.1.0.0.nupkg` and the exact same
package bytes nested in `DataverseSolution/bin/Debug/DataverseSolution.zip`
contained:

```xml
<dependency id="XrmTools.Build" version="0.5.0-recognition" exclude="Build,Analyzers" />
```

The final ZIP also contained the PCF bundle. This confirms the reported leak,
not desktop verification of the new authoring flag.

Disposable local fixtures use the real PAC producer (net48, Microsoft plugin
targets 1.52.1), a compatible net48 solution with Microsoft solution targets
2.14.1, ordinary project references, and the isolated recognition artifact.
Each run packs UUID-suffixed versions to avoid reusing old tool bytes.
Both before/after artifacts contain the same recognition assets; the development
flag and isolated package versions differ. The producer additionally references genuine runtime
dependency `Newtonsoft.Json` 13.0.3.

| Artifact and reference origin | Consumer reference metadata | Producer nuspec |
| --- | --- | --- |
| Before, plain reference | No PrivateAssets/IncludeAssets | XrmTools.Build present; Newtonsoft.Json retained |
| Before, explicit control | PrivateAssets=all | XrmTools.Build absent; Newtonsoft.Json retained |
| After, manually authored plain reference | Still no PrivateAssets/IncludeAssets | XrmTools.Build **still present**; Newtonsoft.Json retained |
| After, fresh CLI installation | PrivateAssets=all; IncludeAssets excludes compile, includes build | XrmTools.Build absent; Newtonsoft.Json retained |
| After, explicit consumer metadata followed by CLI install | PrivateAssets=all; IncludeAssets=build;analyzers preserved | XrmTools.Build absent; Newtonsoft.Json retained |

The CLI-generated reference is:

```xml
<PackageReference Include="XrmTools.Build" Version="0.5.0-dev-RUNID">
  <IncludeAssets>runtime; build; native; contentfiles; analyzers; buildtransitive</IncludeAssets>
  <PrivateAssets>all</PrivateAssets>
</PackageReference>
```

The successful producer dependency group retains:

```xml
<dependency id="Newtonsoft.Json" version="13.0.3" exclude="Build,Analyzers" />
```

The plain-reference cases additionally retain the XrmTools.Build dependency
with their experimental version and `exclude="Build,Analyzers"`, and emit
NU5104. Private-reference cases omit the tool entry and do not emit NU5104.
Removing the entry, not suppressing the warning or making the version stable,
is the acceptance criterion.

## Regression commands and scope

From the repository root:

```sh
# Full package-first check, including the new tests and actual NuGet assets:
./eng/test-package.sh

# Focused rerun after the helper assemblies have been built:
NUGET_PACKAGES="$PWD/artifacts/nuget-cache" \
  python3 eng/test-recognition.py DevelopmentDependency
```

The five focused methods pack both variants using `dotnet pack --no-build`
with distinct PackageVersion values, `XrmToolsPrototypeRecognition=true` and
DevelopmentDependency=false/true. They run real `dotnet add ... package`,
Restore, recognition/configuration queries, two solution Builds, producer
Rebuild and producer Pack/NoBuild, then another solution Build. Every successful
solution build independently opens the final ZIP, compares embedded producer
bytes, DLL and PCF payload, and inspects the producer nuspec dependency group.
Project/source manifest bytes remain unchanged after installation. Restore and
recognition queries do not build producers. Logs and before/after nuspecs are
under `artifacts/recognition <run-id>/`.

The focused command passed all **5 methods**. The full package-first command
passed **69 methods**: 16 target/reference, 20 artifact, 14 staging, 6 execution,
3 consumer-entry-point and 10 recognition/dependency methods, plus the shell
package-content and minimal-fixture checks.

Validation host: macOS arm64, .NET SDK 10.0.403 / MSBuild 18.9.15,
NuGet CLI 7.9.0-rc.2412. The broader suite covers Microsoft solution targets
2.13.1/2.14.1 and existing build/clean/pack/isolation behavior; the new dependency
matrix uses 2.14.1. No execution targets changed. Solution-wide Rebuild of the
source-driven PCF example is not claimed: its existing npm fixture lacks a
`clean` script. The focused producer Rebuild does not change PCF tooling.

## Smallest remaining Visual Studio check

Use a disposable copy of the successful smoke fixture and a newly versioned
local artifact with DevelopmentDependency=true (and recognition assets if
testing ordinary references). Do not overwrite or reuse the cached
0.5.0-recognition package.

1. Install the new package through VS NuGet UI into the plugin producer and
   solution, starting with no XrmTools.Build reference. Do not manually add
   PrivateAssets. Record the VS/NuGet versions and generated reference metadata;
   verify PrivateAssets=all and that IncludeAssets still includes build.
2. Use ordinary Add Project Reference, retain a genuine producer dependency,
   build, and inspect both producer and embedded nuspecs. Require no
   XrmTools.Build dependency, the genuine dependency retained, and byte-identical
   producer package inclusion. Confirm XrmTools imports and plugin recognition.
3. If upgrading an existing installation, separately inspect the resulting
   metadata. Restore/build alone do not repair the old plain reference.
   Fresh uninstall/reinstall via the client is the supported installation path
   to check; do not promise that every VS update path retrofits metadata.

Desktop UI installation is still unverified. This change does not adopt
recognition in the default package, resolve default net462/net48 compatibility,
alter PCF restore, provide a VSIX, or certify IDE scheduling, same-process failed
build recovery, static-graph builds, other SDK versions or Dataverse deployment.
