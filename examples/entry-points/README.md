# Consumer entry-point prototypes

These are complete CLI consumer projects using the same `XrmTools.Build` targets
and Microsoft-generated solution ZIP. The package-reference project is the
existing, supported entry point. The versioned SDK project is a prototype wrapper
packaged beside the same core assets; it does not replace Microsoft targets.

The examples intentionally retain `XrmToolsPluginPackage=true`: that marker is
required by the current implementation. Neither entry point proves the requested
producer-owned, marker-free contract. `ExamplePlugin.csproj` references
`XrmTools.Build`, but ordinary package installation alone does not classify it.
See [the investigation](../../docs/consumer-contract-prototype.md) for what the
tests establish and why the adapters remain.

`Microsoft.PowerApps.MSBuild.Solution` remains a normal explicit
`PackageReference` in both examples, pinned to `2.14.1`. Override
`MicrosoftSolutionBuildVersion` with an exact package version when adopting
another verified release. Do not use a floating version as a compatibility
guarantee. In a consuming application, pin all package versions and check in
NuGet lock files after switching from this local prerelease to immutable package
versions; restore/update them intentionally, then build with locked mode.
The SDK version is in the root `Sdk` attribute and must also be exact; NuGet SDK
resolution uses package sources from `NuGet.Config`, separately from the project
restore graph.

## Run from this repository

The prerelease package is not published. Pack it into the repository-local feed,
then restore/build either project:

```sh
dotnet pack XrmTools.Build.csproj --output artifacts/local-feed
dotnet build examples/entry-points/PackageReference/Solution.cdsproj \
  -p:XrmToolsSolutionVersion=4.5.6.7
dotnet build examples/entry-points/Sdk/Solution.cdsproj \
  -p:XrmToolsSolutionVersion=4.5.6.7
```

`examples/NuGet.Config` includes that local feed and nuget.org. Replace the
relative local source with a trusted package feed when using a published package.
The SDK form needs the SDK package to be resolvable before project restore; it is
not enough to pass a new source only as a restore property.

The local prerelease package is deliberately rebuilt by `dotnet pack` in the
test workflow and is not pinned in a checked-in lock file: repeated local packs
have identical package entry contents but different ZIP timestamps/content
hashes. Published immutable package bytes can be locked normally.

Both projects reference the same plugin producer and PCF project. The producer
owns its NuGet version and output path; the PCF project owns its source build.
The checked-in PCF build script reads `src/index.js` on each Microsoft PCF target
invocation, so a source edit changes the ZIP payload without a prebuilt bundle.
