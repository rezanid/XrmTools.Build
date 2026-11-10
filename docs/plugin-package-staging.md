# Plugin package staging (Phase 5)

## Contract and ordering

`XrmToolsStagePluginPackages` runs before Microsoft's `PowerAppsPackage`,
depending on the **existing** `XrmToolsResolveSolutionVersion` and
`XrmToolsDiscoverPluginPackages` targets. It consumes only validated
`XrmToolsPluginPackageArtifact` items: no producer directory scan, filename
prediction, timestamps, second discovery mechanism, or producer rebuild is added.
There are no new internal Microsoft/NuGet target dependencies or ProjectReference
mutations. Microsoft's target definitions and packager remain unchanged.

The authoritative stage is `SolutionPackagerMetadataWorkingDirectory`. Each
package has:

```text
pluginpackages/<unique-name>/pluginpackage.xml
pluginpackages/<unique-name>/package/<XML package filename>.nupkg
```

New metadata uses `<unique-name>.nupkg`; existing valid filenames are retained.
The actual restored 2.13.1/2.14.1 packagers copy these entries into the final ZIP
with the same layout. `solution.xml` is a root entry in the ZIP, not
`Other/Solution.xml`. The nested managed identity schema is
`pluginpackage/managedidentityid/managedidentityid`. An independent Microsoft-only
probe established that no extra RootComponent is necessary for **ZIP inclusion**.
That is not proof of Dataverse import/registration behavior.

## Metadata precedence and validation

The reference's `XrmToolsPluginPackageUniqueName`, when set, is authoritative and
must already be publisher-prefixed. Otherwise the solution's
`SolutionManifest/Publisher/CustomizationPrefix` is prepended to the validated
NuGet PackageId, unless already present. Explicit/existing prefixes are not
rewritten to the current publisher prefix. Supported safe names match
`[A-Za-z][A-Za-z0-9]*_[A-Za-z0-9_.-]+`, without a trailing dot. No lossy name
normalization is performed. A nonconforming ID needs an explicit valid name.
Names and ZIP entries are unique case-insensitively; directory/XML identity
spelling must match exactly.

Existing metadata is loaded preserving whitespace, comments, namespaces, the XML
declaration's encoding, attributes, IDs, display name, customization flags and
unknown elements. Only the version and an explicitly supplied managed identity
GUID are changed. An omitted reference identity never removes an existing one.
Identity is one nested nonempty GUID; explicit GUIDs override only that inner
value, retaining outer attributes/unknown siblings. New XML defaults are
exportkeyversion=1, iscustomizable=1, statecode=0, statuscode=1,
name=unique-name, package mimetype=application/octet-stream. Exact lexical bytes
can change on a necessary XML edit (for example quote style/BOM); the declared
encoding and XML metadata are preserved. Unchanged XML is not saved.

Every included source-only package is stamped too, even with zero producers.
Its source archive is authoritative; it is checked as a primary NuGet ZIP/nuspec
but is not repacked or compared to a nonexistent producer. Source-only packages
therefore require their existing valid metadata and exact referenced package;
the extension never discovers artifacts on their behalf. Producer packages are
rechecked against Phase 4's validated identity before copying.

Each package requires one name, version and filename-only primary package entry,
matching its directory and exactly one `.nupkg`. Duplicate/missing XML fields,
DTDs, invalid GUIDs, extra/nested/loose package files, and malformed archives fail
explicitly. XML parsing prohibits external resolution and bounds documents at
4 MiB. This is a build metadata contract, not the complete Dataverse schema.

## Intermediate isolation and failed builds

Before Microsoft's source copy, `_XrmToolsPreparePluginPackageStage` verifies that
the stage is **strictly below** `IntermediateOutputPath`, disjoint from the source
tree (neither is an ancestor), and that neither tree traverses symlinks/reparse
points. Custom intermediate roots work; metadata stages outside them are rejected.
Source files and NuGet output directories must never be used as the metadata
stage. The stage is exclusively Microsoft's intermediate content.

Microsoft's copy is an overlay, not a mirror; on failure its normal after-pack
cleanup does not run. Without a reset, a deleted producer/source-only component
can survive a failed build and silently reappear on the next build. The narrow
pre-copy reset deletes **only intermediate `pluginpackages`**, then Microsoft's
copy restores current source packages. It does not delete user output directories
or unrelated stage components, add build state to references, or alter Microsoft's
cleanup target. The failure-recovery regression proves the necessity of this
filesystem side effect. Other extensions generating pluginpackages before this
reset must move their staging after Microsoft's copy/before our staging target.

An unsuccessful build may leave an older output ZIP in place, just as Microsoft's
pipeline does. The build returns failure, the final-validation success message
does not run, and callers must not treat a file's existence as success. The
extension neither deletes that user output nor silently accepts it. Calling
`XrmToolsValidatePackage` alone in a fresh invocation fails: validation requires
captured staging evidence from the **same invocation**.

## Final ZIP validation and output paths

Before Microsoft cleanup, staging captures the complete solution manifest,
per-package XML hashes, package hashes, and validated identity/version. The
after-`PowerAppsPackage` validator does not read the cleaned stage. It checks the
actual ZIP for the resolved solution/plugin versions, all preserved manifest
metadata, exact XML/package bytes, expected membership, and duplicate entries.
Hash equality to the identity-validated archive establishes the embedded nuspec
and payload identity, not merely the filename. Tests independently open nested
archives as well. Altered/missing/extra package bytes, XML/version/publisher
changes, and duplicate entries are rejected.

Single Unmanaged/Managed output uses Microsoft's `SolutionPackageZipFilePath`
exactly, including custom directories/names. The restored task invocation exposes
no output items. For Both, Microsoft's documented and experimentally verified
contract adds `<basename>_managed<extension>` beside the configured ZIP. Only that
second path is derived, not producer artifacts. Combined sources have Managed=2;
the final manifests legitimately become 0 and 1, the sole permitted manifest
transformation. Both files are validated. Package mappings/extensions that move
or alter plugin entries outside this layout fail explicitly rather than bypassing
validation.

## Diagnostics, overhead and limitations

| Code | Meaning |
| --- | --- |
| XTB4000 | Unsafe/non-intermediate/overlapping or linked staging/source directory |
| XTB4001 | Invalid plugin metadata, duplicate/colliding name, package shape/identity, missing or extra artifact |
| XTB4002 | Final ZIP missing, malformed, tampered, wrong metadata/membership, or no current staging evidence |

Compiled netstandard2.0 tasks reuse the already packaged task assembly and
NuGet.Versioning; no new dependencies or host Microsoft.Build runtime DLLs are
shipped. Built-in XmlPoke/Copy alone cannot robustly enforce arbitrary namespaces,
GUID structure, byte-preserving no-op metadata edits, ZIP contents and ancestry/
reparse safety across runtimes. This is the reason for the small task addition.

New work is linear in source/stage file inventory and package bytes: path-link
checks, an intermediate copy, nuspec reads, and SHA-256 of staged and compressed
ZIP package entries (twice for Both). It intentionally does not make solution
packaging incremental. Normal producer compilation remains incremental; Phase 4
retains its deliberate package regeneration overhead. Normal-verbosity messages
report stage preparation (full source/stage link inventory and reset), staging,
and final-validation elapsed milliseconds separately from Pack. Link inventory
is observable O(file-count) overhead, even with zero producers; linked/reparse
paths intentionally fail for zero-producer builds too.
No concurrent writers to a producer output or the same solution stage are
supported; use isolated intermediate/output paths for parallel configurations.
Custom build code is trusted, not sandboxed.

On the local macOS arm64/.NET 10.0.403 13-method staging run, normal-verbosity
task measurements were preparation **1–7 ms** (49 samples, median 3),
staging **3–10 ms** (26 samples, median 3.5), and final validation **0–12 ms**
(18 samples, median 1). These tiny fixture measurements exclude producer Pack
and Microsoft's packager and are not estimates for large production packages.
The complete package-first run passed 15 target, 20 artifact and 13 staging
methods (48 total). Hosted Windows/macOS results are linked from the pull request.

The tests cover both declared Microsoft solution versions, source-only and
0/1/multiple mixed PCF producers, independent package versions, metadata/encoding,
repeated and changed builds, configuration transitions, malformed metadata,
collisions, missing artifacts, compiler/pack/staging failures, failure recovery,
path ancestry/symlinks (when runner privileges permit), final-ZIP tampering and
Unmanaged/Managed/Both custom paths. Dataverse imports/upgrades, Visual Studio
MSBuild, static graph/design-time builds and other SDK releases remain separate
validation gates, not inferred from passing ZIP packaging.
