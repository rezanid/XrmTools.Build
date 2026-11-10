# Troubleshooting

Start with the failed command's exit status and the **first** producer/Microsoft
error, not an old output ZIP. Re-run in a fresh MSBuild invocation after failure.
Use restored imports and the same configuration, platform and reference properties:

```sh
dotnet restore Solution.cdsproj
dotnet msbuild Solution.cdsproj -t:XrmToolsPrintConfiguration
dotnet msbuild Solution.cdsproj -t:XrmToolsGetPluginPackageProjects -getItem:XrmToolsPluginPackageProject
dotnet build Solution.cdsproj -v:normal -bl:solution.binlog
```

The first two XrmTools targets do not Build/Pack producers. Discovery, version
resolution and staging targets have execution/filesystem effects; see
[execution contracts](execution.md). Binlogs can contain paths, environment
variables and secrets: review/redact them before sharing.

| Symptom/code | Corrective action |
| --- | --- |
| XTB1000, missing Microsoft targets/imports | Restore `Microsoft.PowerApps.MSBuild.Solution` with build assets enabled in the `.cdsproj`. Keep Microsoft's SDK; inspect the restored targets before changing its version. The message names the required staging targets. |
| XTB1001 | Both Microsoft's `SolutionVersionStrategy` and XrmTools versioning are active. Remove the former if unintended; the diagnostic shows its value/project. |
| XTB1002 / XTB1003 | Fix the named source manifest or version input: exactly one Version and four decimal components, each 0..2147483647. Explicit override wins; otherwise enabled NBGV, then source XML. Do not repair temporary metadata. |
| Missing NBGV / empty BuildVersion | Add and restore NBGV on the owning solution, opt in explicitly, or set `XrmToolsSolutionVersion`. A producer's NBGV reference does not opt in the solution. |
| XTB2000-XTB2004 | Correct the named reference marker (`true`/`false` only), project path/type or duplicate path/unique name. Leave ordinary C#/PCF references unmarked. |
| XTB3000 / XTB3008 | Read the underlying producer error. Restore/build that producer with the reported dimensions/imports and check its Pack contract. Explicit paths do not skip Pack. |
| XTB3001-XTB3004 / XTB3007 | Return one exact primary package with expected identity/version. Custom nuspec/versionless naming needs the [explicit or producer-return contract](artifact-discovery.md). Never point at a directory or choose the newest file. |
| XTB3005 / XTB3006 | Inspect the named archive's root nuspec; fix corrupt/symbol archives or expected ID/version mismatches in the producer/reference contract. Solution version and producer NuGet version are independent. |
| XTB4000 | Use a physical stage strictly inside IntermediateOutputPath and disjoint from source; remove symlink/reparse traversal. The diagnostic includes all configured roots. Do not disable the check. |
| XTB4001 | Correct the named source plugin XML, package filename, unique name, GUID or producer artifact. The diagnostic shows the active input, stage and solution version. Preserve existing publisher prefixes/identities; do not delete metadata to make validation pass. |
| XTB4002 | Inspect the named actual ZIP and failing entry/membership/version. Rebuild with isolated paths; custom hooks/mappings must preserve validated plugin entries and manifest metadata. Both outputs are checked. Standalone validation needs same-invocation staging evidence. |
| MSB4057 on solution Pack | Use `dotnet build` for a solution ZIP. The tested Microsoft solution SDK does not define NuGet Pack. |
| NETSDK1085 with NoBuild | Do not pass NoBuild to normal reference Build. Use the documented prebuilt-reference mode only after building all required dimensions/TFMs. |
| Missing assets/output after Clean | Restore again, then Build. Keep user NuGet stores outside directories recursively owned by Microsoft/producer Clean. |

Unsupported concurrent shared-output writes can produce races or corrupted ZIPs;
isolate **every** project's paths rather than adding retries. A successful CLI
build and ZIP inspection do not establish Dataverse import/upgrade or desktop
Visual Studio compatibility.
