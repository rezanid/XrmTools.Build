# XrmTools.Build — Phased implementation plan

**Status:** Phases 0–6 merged; consumer-contract prototype completed with a defer recommendation; release compatibility and deployment certification remain outstanding
**Prepared:** 9 November 2026
**Updated:** 11 November 2026, PR #5 recognition revision after reviewed commit `5a22cf9`
**Scope:** A small NuGet package providing MSBuild `.props` and `.targets` to extend Microsoft's existing Dataverse solution projects (`.cdsproj`) and optional plugin-producing `.csproj` projects.

## 0. Current decisions and next gate (authoritative)

This section and §10 supersede conflicting proposals in the original plan below.
Sections 2–7 retain the research and original phase requirements for traceability;
completed phase tasks are not instructions to reimplement them. Read `AGENTS.md`,
current code, regression tests, `docs/architecture.md` and its referenced ADRs first.
No claim of desktop Visual Studio or Dataverse support follows from milestone completion.

### Merged baseline

| Milestone | State and evidence |
| --- | --- |
| Phases 0–4 | Merged in PR #1; package imports, solution versioning, explicit producer classification and validated artifact discovery implemented. Original cross-environment exit gates remain subject to the support table. |
| Phase 5 | Merged in PR #2; intermediate package/metadata staging and final Microsoft ZIP validation; 48 regression methods passed on Windows/macOS CLI. |
| Phase 6 | Merged in PR #3; diagnostics, execution contracts, package documentation/examples and extension-package NoBuild fix; 55 methods passed on Windows/macOS CLI. |
| Consumer contract | PR #5 now includes a separate evaluated-recognition artifact using real PAC plugin tooling, plus an opt-in SDK artifact. Plain references work in the compatible-framework diagnostic; default restore and ordinary-library limitations remain. No runtime adapter was removed. See `docs/consumer-contract-prototype.md` and ADR 0002. |
| Next | Resolve the documented Visual Studio gates and decide whether a marker-free producer contract can preserve the tested Microsoft reference boundary. |
| Phases 7–8 | Not complete. Deployment, desktop IDE and broader compatibility evidence, migration and release remain gated. |

Phase 6 CI: https://github.com/rezanid/XrmTools.Build/actions/runs/42791867282
Tests use Microsoft solution packages 2.13.1/2.14.1 and .NET 10 CLI; consult the
repository support table for exact evidence and outstanding environments.

The baseline requires a per-reference `XrmToolsPluginPackage=true` marker and
explicit solution NBGV opt-in. It temporarily filters/restores project references,
uses an isolated NuGet adapter that intentionally regenerates packages, and resets
only intermediate plugin staging before source copy. These are current contracts,
not final architectural requirements. Reference visibility/order and failed
in-memory recovery remain concerns. Producer compilation remains incremental;
extra package generation is an accepted performance tradeoff, not proof of safety.

The package now authors `DevelopmentDependency=true` so fresh NuGet client
installation can write private build-tool reference metadata without a manual
XML edit. This does not retrofit manual/existing references during restore or
Pack, and does not change recognition adoption. CLI installation and the precise
remaining VS NuGet UI check are recorded in
[`docs/development-dependency.md`](../docs/development-dependency.md).

### Desired consumer contract

1. Retain the normal CLI-generated Microsoft `.cdsproj`, its Microsoft package
   references/imports and independent Microsoft tooling version selection.
2. Referencing `XrmTools.Build` in the solution and participating package-producing
   `.csproj` projects should enable core features with conventional defaults.
3. Add producer references through ordinary Visual Studio Add Project Reference.
   No mandatory marker metadata, special Xrm Tools action or VS extension dependency.
4. Installing NBGV and supplying its normal per-project/version configuration
   should be sufficient to use its calculated versions in the conventional case.
   Preserve an explicit project opt-out and documented override precedence.
5. Each project retains version ownership and participation controls. Document
   build-wide versus project-specific inputs, command-line global properties and
   opt-out behavior. Never silently map a solution version to producer versions.
6. A plain class library must not become a Dataverse plugin just because our
   package is present. Existing plugin/package configuration establishes producer
   intent; future assembly features are separate scope.

These are prototype acceptance goals, not features already shipped. Public API
names and opt-out properties must be settled from evidence, not invented here.

### Producer-contract prototype

Explore a producer-owned integration that provides Microsoft's required reference
output contract plus an explicit capability and package-producing/output target.
Use supported MSBuild target-return communication and a contract owned by us or
custom producers. The solution should detect participation without reading raw
child XML, guessing from PackageId, or mutating ProjectReference collections.

The prototype must demonstrate whether this can remove both temporary reference
filtering and the isolated private NuGet adapter. Returning an existing path alone
is insufficient: the producer must reliably create a current package, propagate
failures and return its exact path/identity. Do not substitute timestamp checks,
stale artifacts, dummy assembly outputs or another hidden import workaround.

Keep artifact identity/content validation, metadata preservation, source isolation
and final ZIP checks. Review staging ownership/reset ordering independently; a new
producer contract does not by itself solve cleanup interactions.

| Acceptance area | Required evidence |
| --- | --- |
| Consumer workflow | Real NuGet restore in CLI-generated projects; normal references; package installed on solution/producers; no per-reference marker. |
| Reference compatibility | References and metadata/order remain visible to representative custom hooks before/during/after reference processing and after failures. |
| Build graph | Restore includes producers without Build/Pack; configuration/platform mappings, multiple producers/TFMs, C#/PCF coexistence and solution builds behave predictably. |
| Execution | Restore, Clean, Build, repeated Build, Rebuild, direct producer Pack and relevant NoBuild paths; no incidental packaging on standalone ordinary producer Build. Solution ZIP creation remains Microsoft's Build behavior, not an invented solution Pack alias. |
| Freshness | Changed code/payload/version, including equal-size/equal-time payloads, reaches the embedded archive; no extra compilation; failure never yields validation success. |
| Versioning | NBGV installed/absent, independent configs, explicit overrides and project opt-outs; no accidental cross-project version propagation. |
| Extensibility | Existing hooks/imports still run with correct dimensions; compare to a Microsoft-only baseline and attribute observable differences. |
| Recovery/isolation | Same-process failure recovery, unchanged source/user outputs and isolated parallel builds. Do not certify recovery solely from fresh command invocations. |
| Hosts | CLI Windows/macOS plus desktop VS/MSBuild, including repeated builds and same-session failure recovery. Unavailable host checks are explicit adoption gates. |

A prototype may report a negative result. Document feasibility, consumer costs,
removed and remaining compromises, measured overhead and unresolved risks in an
ADR. Do not remove existing safeguards or declare the new contract production-ready
until the evidence supports adoption. Documentation alone does not resolve risky
behavior. Small performance costs are acceptable; unexpected execution/state
changes are not acceptable merely to preserve automatic setup.

### Consumer-contract prototype result

The prototype evidence is recorded in
[`docs/consumer-contract-prototype.md`](../docs/consumer-contract-prototype.md)
and [ADR 0002](../docs/adr/0002-consumer-contract-prototype.md). The recommendation
is to retain the package-only `PackageReference` entry point for now and defer
making either the producer-owned capability contract or thin SDK the default.
The SDK wrapper imports the same core successfully, but it does not remove the
marker, reference-filter adapter, forced NuGet packaging, or metadata-staging
reset; it adds an SDK resolver/source/version pin outside the normal package
restore graph. Shorter XML is not sufficient evidence to adopt it.
It only forwards imports, leaving Microsoft references and project defaults
in the consumer. It is now excluded from the default package and available only
with an explicit prototype pack option and a distinct version.

The actual Microsoft `ProcessCdsProjectReferencesOutputs` target still calls
`GetProjectOutputPath` on every `ProjectReference`, including references with
`ReferenceOutputAssembly=false`. The revision implements an evaluated capability
query against Microsoft's `PowerAppsComponentType=Plugin` signal, without child
XML parsing, Build or Pack. Only the real PAC producer is recognized; ordinary
libraries with PackageId and XrmTools.Build are not. Plain references need no
marker, unique name or ReferenceOutputAssembly metadata in the compatible-net48
diagnostic, while the existing scoped reference filter remains necessary.
The default net462 solution/PAC net48 producer fails Restore with NU1201; adding
an ordinary class library preserves Microsoft's MSB4057 output-target failure.
These limitations are not hidden by reference mutations or project rewrites.
The current producer-return target reports an exact artifact path and identity;
the standard-package freshness guarantee still depends on the isolated NuGet
adapter. No safe generic replacement was demonstrated. Recognition is evaluated
independently of adapter removal in a distinct `0.5.0-recognition` local artifact,
not adopted silently by the default package.

The dated VS smoke-test report named in the investigation request is absent from
the inspected main and planning branch. The current CLI prototype must not be
used to claim desktop VS scheduling, restore-host parity, NuGet UI behavior, or
same-session recovery. The VS test procedure and outstanding gates are listed in
the prototype report.

## 1. Objective and design principles

Deliver `XrmTools.Build`, a standalone and Xrm Tools-compatible NuGet build extension. A Dataverse solution project must continue using the **Microsoft** `Microsoft.PowerApps.MSBuild.Solution` package and Microsoft's normal solution packaging pipeline. Users should be able to upgrade the Microsoft package independently. Xrm Tools project templates may add `XrmTools.Build`, but using the Visual Studio extension must **not** be required to build or use it.

The extension addresses gaps currently handled by `AlbanianXrm.CDSProj.Sdk`, notably:

1. Discovering, building, and including project-produced plugin `.nupkg` packages in Dataverse solutions.
2. Synchronizing a resolved **Dataverse solution version** across the packaged `Other/Solution.xml` and every included `pluginpackage.xml`.
3. Optional per-project NBGV integration, with explicit version override and manifest fallback.
4. Preserving package identity, publisher-prefixed names, and optional managed identity information without overriding Microsoft's solution packaging implementation.
5. Clear diagnostics and repeatable builds in Visual Studio, MSBuild, `dotnet build`, and supported CI agents.

**Non-goals:** No fork/wrapper MSBuild SDK; no custom NuGet pack engine; no replacement Dataverse solution packager; no mandatory NBGV; no automatic rewrites of `PackageVersion` in plugin `.csproj` projects; no forced changes to a user's package/output directories; no recursive search for the “latest” `.nupkg`; no mandatory dependency on the Xrm Tools VS extension.

### Important distinction: three version values

| Version | Owner and intended behavior |
| --- | --- |
| Plugin NuGet `PackageVersion` | Owned by **each plugin `.csproj`**. May come from NBGV, an explicit version, or other project configuration. `XrmTools.Build` must not overwrite it implicitly. |
| Dataverse solution version | Resolved once for the **`.cdsproj`** from explicit `XrmToolsSolutionVersion`, enabled NBGV, or the existing `Solution.xml`. Must be four numeric components. |
| `pluginpackage.xml` `<version>` | Stamped using the **same resolved Dataverse solution version**, for each plugin package included in the final solution ZIP. |

The version inside a plugin `.nupkg` and the Dataverse solution/plugin-package metadata version are **not required to be identical**. Whether this distinction causes deployment constraints is a separate Dataverse integration-test concern (see §7).

## 2. Research findings and confidence

| Claim | Current evidence | Remaining verification |
| --- | --- | --- |
| A standard `.cdsproj` can consume build assets from NuGet `PackageReference` | Microsoft `.cdsproj` example references `Microsoft.PowerApps.MSBuild.Solution`; NuGet documents automatic `.nuget.g.props`/`.nuget.g.targets` imports. [R1–R3] | Validate with a local `XrmTools.Build.nupkg` and representative legacy/modern `.cdsproj` configurations. |
| We can extend existing Microsoft targets instead of replacing its SDK | MSBuild supports `BeforeTargets`/`AfterTargets`; TALXIS demonstrates using Dataverse extension targets. [R4, R5] | Confirm exact hook sequence in each supported Microsoft-package version. |
| Producer project targets can return artifacts to consuming solution targets | `MSBuild` task supports `TargetOutputs` and target `Returns`; AlbanianXrm already uses it. [R6–R8] | Verify target execution/order under IDE, CLI and graph builds. |
| NBGV can provide a numeric four-part version | NBGV's `GetBuildVersion` sets `BuildVersion`; `PackageVersion` is independently SemVer. [R9] | Confirm availability/import timing for non-SDK-style `.cdsproj` projects and partial CI checkouts. |
| NuGet exposes calculated pack outputs | `_GetOutputItemsFromPack` returns `_OutputPackItems`, with absolute `.nupkg`/`.nuspec` paths. [R10, R11] | It is an internal target, not a documented stable public contract. Some older toolchains miscompute custom `.nuspec` names. [R12–R14] |
| `pluginpackage.xml` can be created/updated with MSBuild XML tasks | AlbanianXrm's `Sdk.targets` uses `XmlPeek`, `XmlPoke`, `Copy`, and `WriteLinesToFile`. [R8] | Prefer staging rather than source edits; prove resulting files are included in the final ZIP. |
| Dataverse accepts repeated solution imports with versioned plugin package XML | Not established by build-source inspection. Microsoft documents restrictions on changing server-side plugin package name/version through API/update flows. [R15, R16] | **Must test actual imports** into a disposable environment; do not mark as proven. |

**Engineering constraint:** Installed Microsoft solution packaging targets may differ from open-source examples, and the NuGet task is internal. Every build hook and metadata shape must be established by examining the *restored* packages, preprocessed MSBuild project, and binary log, not by assuming the sample target structure matches all supported releases.

## 3. Proposed package and project contract

> Historical proposal: the merged implementation includes justified compiled helpers. The layout and APIs below are not a mandate to remove them. For the next consumer contract, §0 takes precedence.

### 3.1 Package layout

Start with one NuGet package and no compiled custom MSBuild task unless one becomes demonstrably necessary.

```text
XrmTools.Build.nupkg
└── build/
    ├── XrmTools.Build.props
    ├── XrmTools.Build.targets
    └── targets/
        ├── SolutionVersion.targets
        ├── PluginPackageReferences.targets
        ├── PluginPackageArtifacts.targets
        ├── PluginPackageMetadata.targets
        └── Validation.targets
```

Use NuGet's conventional `build/` assets and generated imports. Avoid `buildTransitive/` in V1: downstream projects should not accidentally inherit a solution's build behavior. Do not introduce or mutate restore-related `PackageReference`, `PackageVersion` items, or target-framework configuration from imported package targets; NuGet restricts this behavior [R2]. Keep `.props` lightweight and avoid mutable side effects at project evaluation time. Use conditional `.targets` execution determined by the actual project context and explicit inputs.

### 3.2 `.cdsproj` usage (illustrative; adjust to actual existing Microsoft project)

```xml
<ItemGroup>
  <PackageReference Include="Microsoft.PowerApps.MSBuild.Solution" Version="2.x.y" />
  <PackageReference Include="XrmTools.Build" Version="1.0.0" PrivateAssets="all" />
  <!-- Optional, and only when THIS project wants NBGV: -->
  <PackageReference Include="Nerdbank.GitVersioning" Version="3.x.y" PrivateAssets="all" />
</ItemGroup>
<PropertyGroup>
  <XrmToolsUseNbgv>true</XrmToolsUseNbgv>
  <!-- Optional: XrmToolsSolutionVersion is the highest-priority override. -->
</PropertyGroup>
<ItemGroup>
  <ProjectReference Include="..\PluginA\PluginA.csproj">
    <XrmToolsPluginPackage>true</XrmToolsPluginPackage>
    <!-- Optional: XrmToolsPluginPackageUniqueName, ManagedIdentityId, ... -->
  </ProjectReference>
</ItemGroup>
```

`2.x.y` and `3.x.y` are placeholders: choose tested exact versions or central package management; don't publish this sample with literal placeholders or float the Microsoft dependency for the user.

For a CI override:

```bash
dotnet build MySolution.cdsproj -p:XrmToolsSolutionVersion=2.5.100.0
```

**Project intent:** `ProjectReference` metadata `XrmToolsPluginPackage=true` marks a package-producing reference. Normal references (such as PCF projects) are left to Microsoft's ordinary behavior. Consider an explicit `<XrmToolsPluginPackage Include="...">` alternative if direct project-reference processing proves unsafe. Do not classify by the existence of a literal `<PackageId>` XML node: package IDs may be calculated or inherited.

### 3.3 Optional producer `.csproj` integration

Ordinary plugin projects should not *have to* reference `XrmTools.Build` when automatic output discovery succeeds. Advanced projects may add the same build package to expose an explicit **producer-side target** (proposed name `XrmToolsGetPluginPackageArtifact`), returning the produced `.nupkg` path and metadata using `Returns="@(...)"`. Also allow an explicit artifact path on the solution reference for custom/nonstandard pack flows.

The consumer must **not** transmit its `XrmToolsSolutionVersion`, `FileVersion`, `PackageVersion`, or generic `Version` as global properties into the plugin project unless the user explicitly requests such coupling. Pass only genuinely necessary build dimensions (e.g., configuration/platform) with appropriate project-reference mapping. Respect plugin-local NBGV or explicit package versions.

### 3.4 Property/API proposal (freeze after Phase 1)

| Property/item | Meaning |
| --- | --- |
| `XrmToolsSolutionVersion` | Optional, **highest priority** four-part numeric version for the `.cdsproj` solution and all included `pluginpackage.xml`. |
| `XrmToolsUseNbgv` | Optional `true/false`; when true and no explicit override, use this `.cdsproj`'s NBGV `GetBuildVersion` output. |
| `XrmToolsPluginPackage=true` | Reference metadata identifying a plugin package producer. |
| `XrmToolsPluginPackagePath` | Optional exact `.nupkg` file path override; exact semantics (absolute/relative to project) must be documented. |
| `XrmToolsPluginPackageUniqueName` | Optional Dataverse unique-name override; default from a validated package identity + publisher prefix. |
| `ManagedIdentityId` | Optional plugin-package metadata; preserve existing valid values or use explicit reference metadata with documented precedence. |
| `XrmToolsGetPluginPackageArtifact` | Optional producer target returning primary `.nupkg` and metadata after pack. |
| `XrmToolsValidatePackage` | Target that validates resulting artifact and final solution metadata. |

Keep internal/private MSBuild identifiers prefixed (`_XrmTools...`). Avoid using unqualified `FileVersion` as the canonical solution-version property because NBGV and plugin builds already use it differently. This table is a **proposal**, not an implementation-ready API until Phase 1 tests confirm the integration constraints.

## 4. Phased execution plan

### Phase 0 (merged milestone; original tasks) — Baseline, compatibility inventory, and design record

**Tasks**

1. Inspect the actual target repository: existing `.cdsproj` samples/templates, `AlbanianXrm.CDSProj.Sdk` usages, plugin `.csproj`, CI workflows, NBGV references, code that assumes paths, managed identity metadata, and tests.
2. Record current behavior and capture reference solution ZIPs with at least one plugin package, multiple plugin packages, and one PCF reference.
3. Pin a reproducible initial test matrix: installed Visual Studio/MSBuild, .NET SDK versions, PAC CLI, Microsoft solution package versions (at least one known-working baseline and one current supported version), NuGet/NBGV versions, OS/agent images.
4. Read actual restored Microsoft/NuGet imports and map the target DAG using `-pp`/`-preprocess`, diagnostic logs, and `-bl`. Document the boundaries between `CopyCdsSolutionContent`, `ProcessCdsProjectReferencesOutputs`, and solution packaging target(s).
5. Write a concise ADR explaining why an additive `PackageReference` extension replaces a wrapper SDK.

**Deliverables:** `docs/architecture.md`, baseline fixture(s), build log artifacts, version/target compatibility inventory, one ADR.

**Exit:** Evidence demonstrates the exact build ordering and a normal Microsoft-only project still builds unchanged. No speculative replacement of Microsoft's internal targets.

### Phase 1 (merged milestone; original tasks) — Minimal NuGet import proof (the first implementation gate)

**Tasks**

1. Create minimal `XrmTools.Build` packaging with `build/XrmTools.Build.props` and `build/XrmTools.Build.targets` (no DLL initially).
2. Add a harmless diagnostic target such as `XrmToolsPrintConfiguration` to confirm imports in a real `.cdsproj` and `.csproj` via direct `PackageReference`.
3. Verify imports after restore under VS/MSBuild and `dotnet build` where supported; no need for `Sdk="XrmTools.Build/..."`.
4. Confirm Microsoft SDK version remains selected independently by consuming project.
5. Confirm `PrivateAssets="all"` and build asset scope don't leak behavior to unrelated project references.

**Exit:** Same `.cdsproj` builds successfully with and without package; local NuGet pack/restore works; CI and Visual Studio import proof recorded. If a specific project type doesn't import `.targets`, document supported configuration instead of silently claiming universal compatibility.

### Phase 2 (merged milestone; original tasks) — Resolve the Dataverse solution version

**Tasks**

1. Implement version-selection precedence:
   - explicit `XrmToolsSolutionVersion`;
   - NBGV `BuildVersion` **only if `XrmToolsUseNbgv=true` for that `.cdsproj`**;
   - existing `Other/Solution.xml` `<Version>` otherwise.
2. Call NBGV `GetBuildVersion` at the correct MSBuild time (not before package targets are imported); never use `NuGetPackageVersion` as a Dataverse XML value. If NBGV is enabled but unavailable or misconfigured, fail with a specific actionable error rather than silently substituting another version.
3. Validate four numeric components; fail on SemVer suffixes, empty/malformed values, overflow/out-of-range values, and missing `Solution.xml`. Verify actual supported component ranges, rather than assuming them.
4. Make the resolved value available within **the consuming `.cdsproj` build**; do not propagate it to child plugin project versions.
5. Ensure no unnecessary writes to source-controlled files: investigate stamping the staged solution content with an explicit condition, or use a safe temporary staging copy if Microsoft's target order requires it.

**Exit:** Explicit, NBGV, and manifest sources each produce a predictable resolved four-part version. Repeated builds are idempotent and source files aren't unexpectedly modified.

### Phase 3 (merged milestone; original tasks) — Recognize plugin-package projects safely

**Tasks**

1. Prefer explicit metadata `XrmToolsPluginPackage=true` on each `ProjectReference` (or a dedicated item if proven safer). Avoid reading raw child `.csproj` text to infer `PackageId`.
2. Distinguish marked plugin `.csproj` references from normal C# references, PCF projects, and unrelated project types. Preserve all unmarked Microsoft behavior.
3. Determine an integration point before Microsoft treats plugin package projects as ordinary project-output/assembly references; avoid rewriting Microsoft's targets by name if possible.
4. Preserve per-reference metadata for unique name, package source, managed identity, and build dimensions. Validate duplicate unique names, missing referenced projects, and unsupported producer types.
5. Use MSBuild's `TargetOutputs`/`Returns` contract for producer communication; prevent accidental double-builds or unbounded recursive MSBuild invocations.

**Exit:** A solution with 0, 1, or many package references builds; existing PCF/non-plugin references remain functional; package references are not misclassified.

### Phase 4 (merged milestone; original tasks) — Exact `.nupkg` discovery and verified fallback

**Implementation order**

1. Build/pack the referenced producer through MSBuild (`Targets="Pack"`, with correct restore prerequisites/configuration) and keep its own package version settings untouched.
2. If the user supplied `XrmToolsPluginPackagePath`, resolve and verify that **exact file** after producer packaging (or document opt-out for prebuilt artifacts).
3. If the producer supplies `XrmToolsGetPluginPackageArtifact`, use its `Returns` contract and validate the returned item.
4. Otherwise, use NuGet's `_GetOutputItemsFromPack` target as a **best-effort adapter**. It uses the actual package-related MSBuild inputs, returns absolute output paths, and is already used by AlbanianXrm, but it is an internal target and must not be treated as immutable.
5. Filter `.nuspec`, `.snupkg`, and symbols `.nupkg`; require **one unambiguous primary package**. Check existence, freshness when appropriate, and the expected NuGet package identity/version. For a robust identity check, examine the actual `.nupkg`'s embedded nuspec; implement a small compiled task **only if necessary** and justified by cross-runtime portability tests.
6. For unsupported custom `.nuspec` or older NuGet mismatches, issue a precise error (computed vs actual path and suggested `XrmToolsPluginPackagePath`/producer-contract fix). **Do not** guess via timestamps or search an output folder for the newest file.
7. Handle custom `PackageOutputPath`, relative/absolute paths, centralized props, `PackageId`, `PackageVersion`, `OutputFileNamesWithoutVersion`, source/symbol packages, multiple TFMs, `GeneratePackageOnBuild`, and unusual `.nuspec` substitution.

**Exit:** Primary artifact is correctly identified, deterministically, across the supported matrix; failures offer explicit overrides; no user output paths are changed. Record which combinations are guaranteed vs best-effort.

### Phase 5 (merged milestone; original tasks) — Stage plugin packages and synchronized metadata

**Tasks**

1. Determine the authoritative **staged solution directory** from Microsoft's installed build targets. Stage each resolved plugin `.nupkg` under the Dataverse solution's expected `pluginpackages/<unique-name>/package/<unique-name>.nupkg` layout, adapting only to the actual schema/packager requirements.
2. Create missing `pluginpackage.xml` or update existing metadata using MSBuild `XmlPeek`, `XmlPoke`, `Copy`, and `WriteLinesToFile` (or a minimal task if built-in tools are insufficient). Avoid wholesale rewriting XML, which can drop unknown fields.
3. Apply the **same resolved** `XrmToolsSolutionVersion` to the staged `Other/Solution.xml` and **every included** `pluginpackage.xml`, not just those linked from active references. Decide and document handling of pre-existing packages already in the solution source tree.
4. Preserve package unique name, publisher prefix, `managedidentityid` structure, customization flags, existing IDs/metadata, and XML namespaces/encoding. Avoid unintentionally deleting managed identity elements when the producer/reference omits metadata.
5. Verify output includes exactly one expected `.nupkg` per package and XML's package file entry points to it. Check duplicate/conflicting components and empty paths.
6. Invoke Microsoft's usual solution package targets; do not build ZIPs independently or change unrelated solution content.

**Exit:** Inspect the **final output ZIP**, not just the `src/` directory: consistent versions, expected package contents, intact metadata. Original source-controlled XML unchanged unless a documented opt-in enables source changes.

### Phase 6 (merged milestone; original tasks) — Diagnostics, predictable execution and packaging quality

**Tasks**

1. Add clear errors/warnings with project paths and relevant property values: missing/invalid NBGV; malformed version; no `Pack`; ambiguous `.nupkg`; NuGet output mismatch; missing publisher prefix; duplicate package unique names; missing plugin source; invalid managed identity metadata; staging path collisions.
2. Make repeated builds stable: no needless XML rewrites; ensure builds notice changed `.nupkg`; avoid timestamp-sensitive logic; document behavior for incremental, clean and parallel builds.
3. Support `Clean` without deleting user output directories or unrelated packages. Respect `NoBuild`, `Restore`, `Pack` and CI target semantics as applicable; do not rerun pack unexpectedly when building a solution in the IDE.
4. Produce `.nupkg` with README, supported-tooling table, licensing, release notes, sample `.cdsproj`/`.csproj`, and troubleshooting guide.
5. Pin package-test fixtures; test final package layout and imports using the actual built `.nupkg`, not only an in-repo imported `.targets` file.

**Exit:** Deterministic builds; straightforward diagnostics; package consumable without Xrm Tools and independent of other community SDKs.

### Phase 7 — Functional, compatibility and deployment tests

Implement §7's matrix and use test categories:

- **Unit/target tests:** version precedence/validation, metadata choices, unique-name normalization, project classification, multiple-package matching, artifact selection, failure diagnostics.
- **Build integration:** real local NuGet package restore; Microsoft standard `.cdsproj`; one/multiple plugin-producing `.csproj`; PCF coexistence; source unchanged; final ZIP inspection.
- **CLI/IDE/CI:** Visual Studio MSBuild, `dotnet build`, Azure DevOps and GitHub Actions on supported runners; graph builds or solution builds if relevant.
- **Dataverse end-to-end:** import newly packaged solution, then import an updated version; test managed and unmanaged cases as relevant; verify existing plugin steps and packages behave as expected. Use a disposable environment and follow normal ALM practices.

**Exit:** Matrix is green for declared support, exceptions are documented; deployment test has explicit results rather than inference from ZIP contents.

### Phase 8 — Xrm Tools adoption, migration and release

**Tasks**

1. Update Visual Studio project templates so new `.cdsproj` projects use Microsoft's supported structure and optionally add `XrmTools.Build`. If a generated plugin project benefits from the producer contract, add the same package there; otherwise avoid a needless dependency.
2. Provide migration guidance from `AlbanianXrm.CDSProj.Sdk`: replace SDK selection with the Microsoft project configuration, add the `PackageReference`, mark plugin references, map old version/managed-identity settings. Do **not** silently rewrite existing projects.
3. Compare before/after solution ZIP outputs and build behavior using fixture projects. Test backward compatibility before proposing any automated migration action.
4. Publish prerelease NuGet builds for real-user feedback, with a compatibility table, limitations and troubleshooting instructions.
5. Release V1 only when version stamping, package selection and final ZIP inspection are reliable; put any unsupported environment or exotic pack path in a documented limitation rather than guessing.

**Exit:** A developer can create or migrate a solution, restore/build/package in a supported environment, and obtain synchronized metadata without installing Xrm Tools.

## 5. Reference execution flow (conceptual)

```text
.cdsproj (Microsoft.PowerApps.MSBuild.Solution + XrmTools.Build)
    |
    +--> Resolve XrmToolsSolutionVersion:
    |      explicit override > enabled .cdsproj NBGV > Solution.xml
    |
    +--> Identify marked plugin-package ProjectReferences
    |      (leave normal Microsoft references alone)
    |
    +--> For each plugin package producer (.csproj):
    |       Build/Pack with its own NuGet version choices
    |       exact artifact path override (if supplied)
    |          or producer target (if present)
    |          or NuGet _GetOutputItemsFromPack adapter
    |       verify exactly one primary .nupkg
    |
    +--> Stage all plugin artifacts + preserve metadata
    |
    +--> Stamp staged Solution.xml and pluginpackage.xml versions
    |
    +--> Run Microsoft's existing solution packaging targets
    |
    +--> Inspect/validate final Dataverse solution ZIP
```

**Critical ordering rule:** Version stamping must operate on the bytes that the Microsoft packager actually consumes. `BeforeTargets`/`AfterTargets` hook selection must be derived from the restored target files and verified using a binlog. Do not assume changes to source files automatically flow into staged contents.

## 6. Key risks and decisions

| Risk | Mitigation / decision |
| --- | --- |
| `_GetOutputItemsFromPack` is private and version-sensitive | Best-effort automatic adapter; post-pack validation; exact artifact override and optional producer output contract. Do not depend solely on a recent NuGet fix. |
| `.cdsproj` project styles differ across SDK/VS versions | Begin with supported Microsoft project shape, version matrix, and effective imported targets. |
| Build package import timing | Validate `.nuget.g.props/.targets`; use execution-time targets for NBGV/version metadata; no restore-affecting updates in imported targets. |
| Unexpected child project version override | Never forward `XrmToolsSolutionVersion` as `PackageVersion`, generic `Version`, or `FileVersion` to plugin projects. |
| Inconsistent final metadata | Validate **final ZIP**: solution version equals *all* plugin XML versions, irrespective of producer NuGet versions. |
| Source-controlled XML dirtied by build | Work on staging/intermediate copy by default; verify git working tree stays clean. |
| Target conflicts with Microsoft/other plugins | Prefix target names; hook non-destructively; record any Microsoft target version dependency. |
| Managed identity and package name regressions | Golden fixtures and regression tests for `managedidentityid`, publisher prefix, XML fields, and unique names. |
| Dataverse update restrictions | Test imports in a disposable environment; do not assume server behavior based on successful ZIP generation. |
| Unsupported platform/version combinations | Clear support table; error with actionable alternative; avoid silent fallback or guessing. |

**Historical open decisions (consult merged contracts and §0 before acting):** final public property/item names; whether pre-existing unmanaged pluginpackage XML without a project reference is stamped; handling of source-only packages; exact unique-name/ID precedence; whether to expose a producer-side contract in V1 or V1.1; and which toolchain versions are promised for V1.

## 7. Detailed test matrix and acceptance criteria

### 7.1 Version-source behavior

| Scenario | Expected outcome |
| --- | --- |
| Explicit `XrmToolsSolutionVersion=3.2.45.0`, with NBGV installed | Explicit value wins; all final solution/plugin XMLs are `3.2.45.0`. |
| NBGV enabled on `.cdsproj`, no explicit override | `GetBuildVersion` runs and its numeric four-part `BuildVersion` is stamped; NuGet/assembly versions on plugin producers unchanged. |
| NBGV disabled/absent | Existing `Solution.xml` version retained and used in plugin XML. |
| NBGV enabled but package missing or version unavailable | Clear failure; no stale/unrelated version silently stamped. |
| CLI explicit version malformed (`1.2.3-beta`) | Fail before packaging; report expected four-part numeric format. |
| Multiple solution projects in the same repo | Each project resolves independently; shared `version.json` is not treated as implicit opt-in. |
| Solution version differs from plugin NuGet package version | Allowed; XML reflects solution version, actual `.nupkg` retains its producer version. |
| Version unchanged on a second build | No unnecessary mutation of original files; output metadata remains stable. |

### 7.2 Package artifacts and project references

| Scenario | Expected outcome |
| --- | --- |
| One standard plugin package | Exactly one correct `.nupkg` staged and referenced. |
| Two or more plugin packages | Correct distinct packages, unique names, and independent producer metadata. |
| `.cdsproj` includes PCF reference and an ordinary `.csproj` | Microsoft's existing handling is unaffected; no false plugin-package classification. |
| `PackageId` set in `Directory.Build.props`/computed | Discovery works without raw project XML inspection. |
| Plugin package version from its own NBGV | Package is located without changing its own version. |
| Explicit package path override | Exact file selected, validated; no directory scans. |
| Producer exposes custom return target | Returned artifact selected and validated; no dependence on NuGet private target. |
| Custom `PackageOutputPath` and `OutputFileNamesWithoutVersion` | Exact artifact found/validated when toolchain supports it; otherwise actionable override path required. |
| Custom `.nuspec` with differing ID/version; old NuGet | Mismatch detected, no silent wrong artifact; explicit-path/producer fallback documented. |
| Symbols `.snupkg` and `*.symbols.nupkg` present | Only primary plugin package included. |
| Multi-targeted plugin project and `GeneratePackageOnBuild` | One correct primary output; no duplicate or stale artifact. |
| Stale package from earlier version in output folder | Not chosen due to timestamp/latest-folder logic; discovery must be deterministic. |
| Duplicate unique names, nonexistent reference, Pack unsupported | Fail with specific error, not a partly correct solution ZIP. |
| Managed identity supplied/previously present | Preserved according to documented precedence; structure exactly as expected. |

### 7.3 Build environments and compatibility

Run representative fixtures on:

- Visual Studio-supported Windows MSBuild versions, including Clean, Restore, Build, and repeated incremental Build.
- `dotnet restore` / `dotnet build` against supported SDKs (Windows first; Linux/macOS only if the Microsoft `.cdsproj` build pipeline actually supports them).
- At least two Microsoft.PowerApps.MSBuild.Solution package versions: a stable baseline and latest declared supported version.
- At least two NuGet tooling generations, including one predating and one including the July/August 2026 `_GetOutputItemsFromPack` fixes if practical; version differences must be documented.
- GitHub Actions and Azure DevOps: clean checkout, shallow checkout vs NBGV git-history requirements, central package management, custom `NuGet.Config`/restore paths, parallel builds, SDK pinning/global.json.
- Paths with spaces, clean output folders, Windows-style and cross-platform path separators where supported.

Use binlogs and final ZIP inspection to diagnose failing cases. A build pass without examining the ZIP is **not** enough.

### 7.4 Final solution ZIP assertions

For each ZIP, assert:

1. It is a valid ZIP generated through Microsoft's solution packaging step.
2. Root `solution.xml` in the final ZIP has the resolved solution version. `Other/Solution.xml` is the source/staged path, not the final ZIP entry.
3. Every included `pluginpackage.xml` version **exactly equals** that solution version.
4. Each XML package reference resolves to exactly one expected embedded `.nupkg`.
5. Embedded `.nupkg` has the intended producer package identity and version (which may differ from the solution version).
6. Publisher-prefixed name, managed identity, existing metadata, other solution components and PCF references are retained.
7. Original source-controlled `Solution.xml`/`pluginpackage.xml` remain unchanged by default.
8. Repeated builds do not choose stale artifacts or cause unpredictable output changes.

### 7.5 Deployment smoke tests (separate gated credentials)

- Disposable Dataverse environment: first import with one package; subsequent solution upgrade with changed metadata/payload; verify plugin package row/assembly and representative registered steps remain usable.
- Repeat with multiple packages and managed identity if available.
- Test managed and unmanaged solutions where the intended user workflow requires them.
- Document server-side name/version immutability behavior and any incompatibility; do **not** automate imports from default unit test jobs or require credentials for local builds.

**Release criterion:** Pass unit + build + ZIP assertions for a declared supported matrix, and publish the deployment results/limitations separately. No unsupported claim that every future NuGet/MSBuild/Microsoft SDK version will behave identically.

## 8. Delivery and remaining gates

- [x] NuGet build assets and compiled helpers extend the Microsoft pipeline without a wrapper SDK.
- [x] Explicit solution override, optional NBGV and manifest fallback implemented under the current opt-in contract.
- [x] Producer versions remain independent; exact package artifacts are validated.
- [x] Explicitly marked producers coexist with ordinary references in tested fixtures.
- [x] Final ZIP plugin metadata versions match the solution; embedded package bytes are checked.
- [x] Source metadata is unchanged; identities, names and valid metadata are preserved in tested cases.
- [x] Diagnostics, execution documentation, runnable packaging examples and package-content checks added.
- [x] Phase 6 Windows/macOS .NET CLI regression matrix passed.
- [ ] Producer-contract prototype and architecture/adoption decision (§0).
- [ ] Package-reference-only consumer workflow and ordinary project references proved.
- [ ] Conventional NBGV integration, project participation/opt-outs and scoped overrides proved under the revised contract.
- [ ] Custom-hook compatibility and same-process failure recovery established.
- [ ] Desktop Visual Studio/MSBuild and declared broader host/tooling matrix established.
- [ ] Disposable Dataverse initial import and upgrade tested and documented.
- [ ] Xrm Tools adoption and migration guidance updated after core contract approval.
- [ ] Publication/release explicitly authorized after required gates pass.

## 9. Primary references (upstream code and documentation)

- **[R1] Microsoft `.cdsproj` example:** [`AzureMapsSln.cdsproj`](https://github.com/microsoft/powerapps-tools/blob/master/Components/PCF/AzureMaps/AzureMapsSln/AzureMapsSln.cdsproj) — `RestoreProjectStyle=PackageReference`, Microsoft solution package and build imports.
- **[R2] Microsoft NuGet documentation:** [MSBuild `.props` and `.targets` in a package](https://learn.microsoft.com/en-us/nuget/concepts/msbuild-props-and-targets) — generated imports, `build`/`buildTransitive` and authoring restrictions.
- **[R3] Microsoft NuGet documentation:** [PackageReference in project files](https://learn.microsoft.com/en-us/nuget/consume-packages/package-references-in-project-files) — supported asset types and `PrivateAssets`.
- **[R4] Microsoft MSBuild documentation:** [How MSBuild builds projects](https://learn.microsoft.com/en-us/visualstudio/msbuild/build-process-overview), [Target element](https://learn.microsoft.com/en-us/visualstudio/msbuild/target-element-msbuild), [MSBuild task](https://learn.microsoft.com/en-us/visualstudio/msbuild/msbuild-task).
- **[R5] Existing NuGet extension precedent:** [TALXIS DevKit raw tasks](https://github.com/TALXIS/tools-devkit-build/blob/master/docs/Tasks-Package.md), and [Dataverse solution build README](https://github.com/TALXIS/tools-devkit-build/blob/master/src/Dataverse/Solution/README.md) — note some TALXIS targets override Microsoft's behavior; this is *not* a recommendation to copy those overrides.
- **[R6] Microsoft MSBuild documentation:** [Common MSBuild Project Items](https://learn.microsoft.com/en-us/visualstudio/msbuild/common-msbuild-project-items), including `ProjectReference` behavior.
- **[R7] Microsoft MSBuild documentation:** [MSBuild task](https://learn.microsoft.com/en-us/visualstudio/msbuild/msbuild-task) — `TargetOutputs` from child projects.
- **[R8] AlbanianXrm implementation:** [`Sdk.targets`](https://github.com/albanian-xrm/CDSPROJ-SDK/blob/main/AlbanianXrm.CDSProj.Sdk/Sdk/Sdk.targets) — package reference handling, `Pack`, `_GetOutputItemsFromPack`, plugin XML versioning, managed identity; and [`Sdk.props`](https://github.com/albanian-xrm/CDSPROJ-SDK/blob/main/AlbanianXrm.CDSProj.Sdk/Sdk/Sdk.props).
- **[R9] NBGV documentation:** [MSBuild integration and GetBuildVersion properties](https://github.com/dotnet/Nerdbank.GitVersioning/blob/main/docfx/docs/build-systems/msbuild.md) — `BuildVersion` vs `NuGetPackageVersion` / `PackageVersion`.
- **[R10] NuGet source:** [`NuGet.Build.Tasks.Pack.targets`](https://github.com/NuGet/NuGet.Client/blob/dev/src/NuGet.Core/NuGet.Build.Tasks/NuGet.Build.Tasks.Pack.targets) — `_GetOutputItemsFromPack` returns `_OutputPackItems`.
- **[R11] NuGet source:** [`GetPackOutputItemsTask.cs`](https://github.com/NuGet/NuGet.Client/blob/dev/src/NuGet.Core/NuGet.Build.Tasks.Pack/GetPackOutputItemsTask.cs) — resolved output filename inputs.
- **[R12] NuGet bug:** [NuGet/Home issue #14711](https://github.com/NuGet/Home/issues/14711) — incorrect computed `.nupkg` path with `.nuspec` overrides.
- **[R13] NuGet fix:** [NuGet.Client PR #7531](https://github.com/NuGet/NuGet.Client/pull/7531), merged 13 July 2026 — output filename mismatch.
- **[R14] NuGet fix:** [NuGet.Client PR #7612](https://github.com/NuGet/NuGet.Client/pull/7612), merged 4 August 2026 — `.nuspec` property substitution.
- **[R15] Microsoft Dataverse:** [Build and package plug-in code](https://learn.microsoft.com/en-us/power-apps/developer/data-platform/build-and-package) — plugin package storage and server-side update limitations.
- **[R16] Microsoft Power Platform:** [Create and register a plug-in package using PAC CLI](https://learn.microsoft.com/en-us/power-platform/developer/howto/cli-create-package) — plugin package name/version restrictions.
- **[R17] Microsoft Power Apps:** [Package a code component in a solution](https://learn.microsoft.com/en-us/power-apps/developer/component-framework/import-custom-controls) — Microsoft `.cdsproj` build and packaging CLI paths.

## 10. Next work session

Do not treat the prototype result as adoption of the SDK or a new producer
contract. First run the manual VS procedure in
[`docs/consumer-contract-prototype.md`](../docs/consumer-contract-prototype.md)
on a supported Windows desktop with the intended VS/MSBuild and Xrm Tools
extension. Capture the PackageReference created by NuGet UI, restore/build logs,
the final ZIP and embedded package bytes, PCF source-change scheduling, hook
ordering/invocation counts, and same-process failure/recovery.

After those results, either revise the producer contract with a concrete,
non-mutating Microsoft reference-output integration supported by real MSBuild
evidence, or explicitly retain the scoped filter and its documented trade-offs.
Do not remove the isolated package adapter until a producer-owned target proves
current package content for source, package inputs, identity/version and
configuration changes without relying on timestamps or private NuGet targets.
Keep NBGV configuration/override semantics independent from the solution SDK
decision. Proceed to broader Phase 7 certification only after those gates have a
reviewed disposition. Do not merge, publish, deploy, or claim unverified host
support.
