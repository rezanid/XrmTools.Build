# ADR 0002: Defer a new consumer contract pending Visual Studio evidence

- **Status:** Prototype complete; defer adoption
- **Date:** 2026-11-10

## Context

The merged implementation is an additive NuGet build package that preserves
Microsoft's `.cdsproj` packaging pipeline. The desired consumer experience is
producer-owned plugin-package capability, ordinary project references without
per-reference marker XML, exact current package discovery, and no new SDK unless
it provides meaningful setup or maintenance savings.

The prototype starts from remote main, preserves the merged producer-contract
planning document, and compares a normal PackageReference with a thin,
versioned SDK wrapper that imports the same build targets.

## Evidence

- The baseline package-first test run passed 55 methods on macOS arm64 with .NET
  SDK 10.0.403/MSBuild 18.9.15.52412, Python 3.9.6, Node 22.4.0 and npm 10.8.1.
  The tests use Microsoft solution packages 2.13.1 and 2.14.1.
- The prototype `./eng/test-package.sh` run passed 59 methods: 16
  reference/version, 20 artifact, 14 staging, 6 execution, and 3 consumer
  entry-point tests. A representative before/after reference-hook probe ran
  twice and verified exact invocation order/count plus filtered/restored
  reference visibility.
- The inspected Microsoft `ProcessCdsProjectReferencesOutputs` target calls
  `GetProjectOutputPath` on each project reference, regardless of
  `ReferenceOutputAssembly`. The temporary reference filter prevents the plugin
  producer's assembly output from entering Microsoft solution reference
  processing. The marker-free probe failed with `MSB4057` for missing
  `GetProjectOutputPath`; the default `ReferenceOutputAssembly=true` variant
  failed earlier with `NETSDK1050` for the tested .NET Standard producer.
  Replacing this target or using dummy outputs is not acceptable.
- Producers can own `XrmToolsGetPluginPackageArtifact` and return an exact path
  and identity, but the current standard NuGet path still runs Pack in an
  isolated import with a private invalidation input to reject same-time stale
  content without rebuilding assemblies. An output path alone is not freshness
  proof.
- The SDK wrapper imports the same core props/targets and leaves Microsoft
  package selection explicit. It does not remove marker XML, filtering,
  isolated packaging, staging reset, producer setup, or PCF project setup. It
  introduces SDK package resolution from a configured feed before project
  restore, separate from the ordinary PackageReference lock graph.
- The existing mixed-reference PCF fixture still uses a prebuilt payload. A
  separate source-driven consumer example uses Microsoft PCF targets 2.14.1;
  changing its JavaScript source changes the final ZIP payload. Its small Node
  script is not the official `pcf-scripts`/TypeScript compilation pipeline.
- No desktop Visual Studio/MSBuild environment was available. The dated
  `docs/vs-smoke-test-2026-11-10.md` input was absent from main and the planning
  branch. VS NuGet UI behavior, VS restore differences, IDE scheduling, and
  same-session failure recovery are not verified.

## Decision

Retain PackageReference as the default entry point and defer both automatic
producer recognition and SDK adoption. The package-reference path has a single
normal NuGet restore graph and has broad CLI evidence; the SDK wrapper provides
no demonstrated benefit beyond replacing a package reference with an SDK
attribute. Consumers who already standardize on NuGet-distributed MSBuild SDKs
may evaluate the wrapper, but it is not a production recommendation.

Do not remove the scoped ProjectReference filter or isolated NuGet Pack adapter.
The producer target is an exact artifact-selection contract, not a generic
freshness guarantee or a substitute for Microsoft's reference-output contract.
Do not treat a capability query as sufficient to remove filtering; it must
demonstrate correct Microsoft output processing and hook visibility first.

The `.cdsproj` continues to use Microsoft's package and solution ZIP pipeline.
Producer NuGet/assembly versions remain independent from solution metadata.
NBGV behavior stays unchanged; normal package/config-only integration and
explicit overrides/opt-outs require a separate tested contract.

## Consequences

- Existing explicit marker behavior and its observable reference-list changes
  remain in place and documented.
- The SDK wrapper is packaged as a prototype but contains only import-forwarding
  files; no second build pipeline or Microsoft SDK version is embedded.
- Package-only and SDK examples keep current marker XML so they are runnable
  against the unchanged core. They do not claim the desired marker-free contract.
- Before adoption, Reza must complete the manual Visual Studio procedure in
  `docs/consumer-contract-prototype.md` and provide evidence for PackageReference
  creation, restore, PCF source scheduling, hooks, and same-session recovery.
- A future removal of either adapter requires a focused regression proving exact
  package bytes/currentness across source/content, identity/version and build
  configuration changes, with no timestamp-only or newest-file selection.
