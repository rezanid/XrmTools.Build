# Runnable packaging example

`Solution/Example.cdsproj` uses Microsoft's solution pipeline and the build
extension. `Plugin/ExamplePlugin.csproj` owns NuGet version `2.3.4-beta.1`;
the Dataverse solution version is independently `1.2.3.4` or a build override.
This intentionally tiny class library proves packaging plumbing, **not** a
deployable Dataverse plugin or importable/upgrade-certified solution.

From this directory, with .NET 8+ core MSBuild and restored package availability:

```sh
dotnet build Solution/Example.cdsproj -p:XrmToolsSolutionVersion=4.5.6.7
dotnet clean Solution/Example.cdsproj
dotnet build Solution/Example.cdsproj -t:Rebuild
```

This prerelease is unpublished. For a repository-local package first run
`./eng/test-package.sh` from the repository root, copy/extract the example to
a disposable directory, and append
`-p:RestoreAdditionalProjectSources=/absolute/path/to/artifacts/local-feed`
to the commands. The regression builds this example from the **actual nupkg**,
not via source target imports.

The ZIP is `Solution/bin/Debug/Example.zip`; producer NuGet output is separately
`Plugin/packages/Example.Plugin.2.3.4-beta.1.nupkg`. Solution Clean must not delete
that separate package store. Build with `-p:IncludeExamplePlugin=false` for
version-only packaging without producers. Use
`-p:NoBuild=true -p:BuildProjectReferences=false` only after a normal build of all
references; package regeneration still occurs. Do not call solution `Pack`.

The example's Microsoft version is consumer-owned; change it only with validation.
It uses the .NET Framework reference-assemblies package for CLI portability.
For NBGV, add/restore NBGV on the solution and opt in as shown in the
[main README](../README.md). For custom artifact naming, use the exact
[producer-return or explicit path contract](../docs/artifact-discovery.md).
See [execution](../docs/execution.md) for path isolation and all command semantics.
