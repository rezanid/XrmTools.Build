# Working on XrmTools.Build

## Start from repository evidence

- Use a fresh implementation session and feature branch/worktree from current remote main for each substantial change. Preserve unrelated local changes.
- Inspect current targets, tasks, tests, README, architecture documentation and ADRs before editing. Do not infer repository state from a prior conversation.
- Read `plan/XrmTools-Build-Implementation-Plan.md`; its current-decisions section takes precedence over historical phase proposals. Identify missing material explicitly. Distinguish planned consumer contracts from implemented behavior.
- Open a reviewable PR after validation. Do not merge, publish packages or deploy without explicit authorization.

## Product goals

- Extend Microsoft's solution tooling; do not require replacing it with a wrapper SDK. Retain the CLI-generated project structure and Microsoft imports.
- Ordinary Visual Studio Add Project Reference should be the consumer workflow. Do not require a special Xrm Tools action; the build package must work without the VS extension.
- Desired future contract: referencing XrmTools.Build in a solution and participating package producers enables core integration without per-reference marker XML. This is a prototype goal, not a claim about existing behavior.
- NBGV should remain independently installed/configured by consumers. Aim to consume its evaluated results without redundant normal-case opt-in, while supporting documented project opt-outs and scoped overrides. Verify this before changing the existing explicit opt-in contract.
- Keep solution metadata versions separate from each producer's NuGet/assembly versions. Define command-line global-property propagation and project opt-out semantics explicitly.
- A package reference alone must not classify arbitrary class libraries as Dataverse plugins or unexpectedly enable Pack on ordinary Build.

## Compatibility takes priority

- Small, measured performance costs are acceptable. Unexpected build execution, incorrect artifacts, source changes and fragile compatibility assumptions are not acceptable substitutes for convenient setup.
- Consumers may have custom BeforeTargets/AfterTargets hooks and property/import customizations. Preserve their execution, reference visibility/order and build dimensions. Test observable differences against a Microsoft-only baseline where applicable.
- Do not replace Microsoft targets, scan output directories for the newest artifact, or use timestamps as proof of current package content.
- Preserve ordinary C#/PCF behavior, independent producer versions, managed identities, publisher-prefixed names and unknown valid metadata.
- Edit only owned intermediate/staged metadata. Do not broaden cleanup or delete user package stores. Keep final Microsoft-generated ZIP validation.
- Do not add dependencies or another compatibility adapter without a demonstrated need and focused evidence.

## Current limitations versus prototype work

- Existing reference filtering, isolated NuGet packaging adapter and intermediate plugin reset have documented limitations. Read `docs/architecture.md`, `docs/artifact-discovery.md` and `docs/plugin-package-staging.md` when present.
- Do not weaken existing safeguards merely to make tests pass or reduce packaging time. Do not make retaining the adapters an architectural goal either.
- Evaluate producer-owned capability/output contracts as an alternative to reference mutation and private NuGet integration in a separately scoped prototype. Explicitly verify restore graphs, Microsoft reference handling, package freshness, configuration mapping and IDE scheduling.
- Documenting risky behavior does not resolve it. Failed in-memory build recovery and custom-hook compatibility require evidence; fresh CLI invocations alone do not establish them.

## Validation and reporting

- Run the package-first suite (`./eng/test-package.sh`) for affected implementation changes when available. It tests actual NuGet assets; importing source targets alone is insufficient.
- Add focused regressions for demonstrated gaps. Cover affected Restore, Clean, Build, repeated Build, Rebuild, Pack/NoBuild and isolated parallel behavior as applicable; distinguish root package commands from consumer commands.
- Verify final ZIP contents, independent package versions, unchanged source metadata, package freshness and incremental compilation where relevant.
- For execution changes, test representative custom hooks and failure/recovery in the same process, including desktop VS when available. Record unavailable checks as gaps.
- Do not infer desktop VS, static-graph/design-time, other SDK versions or Dataverse import/upgrade support from passing CLI/ZIP tests. Actual deployment checks require an explicitly authorized disposable environment.
- Report exact commit, commands/results, CI links, new side effects/restrictions, unresolved risks and the declared support matrix. Do not call an unverified environment supported.
