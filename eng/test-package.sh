#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
package_dir="$repo_root/artifacts/local-feed"
fixture="$repo_root/tests/Fixtures/MinimalSolution/MinimalSolution.cdsproj"
plugin_fixture="$repo_root/tests/Fixtures/PluginProject/PluginProject.csproj"
manifest="$repo_root/tests/Fixtures/MinimalSolution/src/Other/Solution.xml"
nuget_cache="$repo_root/artifacts/nuget-cache"

mkdir -p "$package_dir"
NUGET_PACKAGES="$nuget_cache" dotnet pack "$repo_root/XrmTools.Build.csproj" --output "$package_dir" --verbosity quiet
# Refresh only this locally authored package in the repository-local cache after repacking.
python3 - "$repo_root" <<'PY'
from pathlib import Path
import shutil
import sys
import subprocess
import posixpath
import re
import os
import zipfile
import xml.etree.ElementTree as ET

root = Path(sys.argv[1])
version = ET.parse(root / "XrmTools.Build.csproj").findtext("./PropertyGroup/Version")
helpers = list((root / "src").glob("*/bin/Release/*/*.dll"))
assert helpers, "Pack did not build task helpers"
before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in helpers}
subprocess.run(["dotnet", "pack", str(root / "XrmTools.Build.csproj"), "--no-build",
                "--output", str(root / "artifacts/local-feed"), "--verbosity", "quiet"],
               env={**os.environ, "NUGET_PACKAGES": str(root / "artifacts/nuget-cache")},
               check=True)
assert before == {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in helpers}, "NoBuild compiled helpers"
cache = root / "artifacts/nuget-cache/xrmtools.build" / version
if cache.exists():
    shutil.rmtree(cache)
with zipfile.ZipFile(root / f"artifacts/local-feed/XrmTools.Build.{version}.nupkg") as package:
    required = {"build/XrmTools.Build.props", "build/XrmTools.Build.targets",
                "build/targets/PluginPackageReferences.targets", "build/targets/PluginPackageArtifacts.targets",
                "build/targets/ProducerPackAdapter.targets",
                "build/targets/PluginPackageMetadata.targets", "docs/plugin-package-staging.md",
                "tools/netstandard2.0/XrmTools.Build.Tasks.dll", "tools/netstandard2.0/NuGet.Versioning.dll",
                "tools/net8.0/XrmTools.Build.AdapterTasks.dll", "tools/net472/XrmTools.Build.AdapterTasks.dll",
                "docs/architecture.md", "docs/artifact-discovery.md", "licenses/NuGet.Versioning.txt",
                "README.md", "licenses/LICENSE", "docs/execution.md", "docs/troubleshooting.md",
                "docs/release-notes.md", "docs/adr/0001-additive-nuget-build-extension.md",
                "examples/README.md", "examples/Plugin/ExamplePlugin.csproj", "examples/Plugin/Example.cs",
                "examples/Solution/Example.cdsproj", "examples/Solution/src/Other/Solution.xml",
                "examples/Solution/src/Other/Customizations.xml"}
    assert required <= set(package.namelist()), required - set(package.namelist())
    assert not any(name.startswith(("lib/", "buildTransitive/")) for name in package.namelist())
    metadata = ET.fromstring(package.read("XrmTools.Build.nuspec")).find("{*}metadata")
    assert not metadata.findall(".//{*}dependency")
    assert metadata.findtext("{*}readme") == "README.md"
    assert metadata.findtext("{*}license") == "MIT"
    assert metadata.find("{*}license").attrib["type"] == "expression"
    assert "Phase 6" in metadata.findtext("{*}releaseNotes")
    assert package.read("README.md") == (root / "README.md").read_bytes()
    assert package.read("licenses/LICENSE") == (root / "LICENSE").read_bytes()
    assert package.read("licenses/NuGet.Versioning.txt") == (root / "licenses/NuGet.Versioning.txt").read_bytes()
    assert {name for name in package.namelist() if name.endswith(".dll")} == {
        "tools/netstandard2.0/XrmTools.Build.Tasks.dll", "tools/netstandard2.0/NuGet.Versioning.dll",
        "tools/net8.0/XrmTools.Build.AdapterTasks.dll", "tools/net472/XrmTools.Build.AdapterTasks.dll"}
    for name in package.namelist():
        if name.endswith((".props", ".targets")):
            ET.fromstring(package.read(name))
        if name.endswith(".md"):
            for link in re.findall(r"\[[^\]]*\]\(([^)]+)\)", package.read(name).decode()):
                path = link.split("#", 1)[0]
                if path and "://" not in path:
                    target = posixpath.normpath(posixpath.join(posixpath.dirname(name), path))
                    assert target in package.namelist(), f"Broken packaged link: {name} -> {link}"
PY

NUGET_PACKAGES="$nuget_cache" dotnet build "$plugin_fixture" --verbosity minimal \
  -p:RestoreAdditionalProjectSources="$package_dir"
NUGET_PACKAGES="$nuget_cache" dotnet msbuild "$plugin_fixture" -target:XrmToolsPrintConfiguration \
  -verbosity minimal -p:RestoreAdditionalProjectSources="$package_dir" | grep -F "XrmTools.Build imported" >/dev/null

manifest_hash() {
  python3 - "$manifest" <<'PY'
from pathlib import Path
import hashlib
import sys
print(hashlib.sha256(Path(sys.argv[1]).read_bytes()).hexdigest())
PY
}
manifest_before="$(manifest_hash)"
solution_zip="$repo_root/tests/Fixtures/MinimalSolution/bin/Debug/MinimalSolution.zip"
verify_zip_version() {
  local expected="$1"
  python3 - "$solution_zip" "$expected" <<'PY'
import sys
import zipfile
import xml.etree.ElementTree as ET

zip_path = sys.argv[1]
expected_version = sys.argv[2]
with zipfile.ZipFile(zip_path) as archive:
    solution_files = [name for name in archive.namelist() if name.lower() == "solution.xml"]
    if len(solution_files) != 1:
        raise SystemExit(f"Expected one Solution.xml in {zip_path}, found {solution_files}")
    root = ET.fromstring(archive.read(solution_files[0]))
    version = root.findtext("./SolutionManifest/Version")
    if version != expected_version:
        raise SystemExit(f"Expected staged solution version {expected_version}, got {version!r}")
print(f"Verified final Microsoft-generated ZIP contains solution version {version}.")
PY
}

build_fixture() {
  NUGET_PACKAGES="$nuget_cache" dotnet build "$fixture" --verbosity minimal \
    -p:RestoreAdditionalProjectSources="$package_dir" "$@"
}

# Explicit override wins even when NBGV is present and enabled.
build_fixture -p:XrmToolsFixtureIncludeNbgv=true -p:XrmToolsUseNbgv=true \
  -p:XrmToolsSolutionVersion=4.5.6.7 -p:XrmToolsFixtureCheckStamp=Changed -bl:"$repo_root/artifacts/phase1-2.binlog"
verify_zip_version 4.5.6.7

# NBGV is used only when the solution project explicitly opts in.
build_fixture -p:XrmToolsFixtureIncludeNbgv=true -p:XrmToolsUseNbgv=true
nbgv_version="$(NUGET_PACKAGES="$nuget_cache" dotnet msbuild "$fixture" \
  -target:PrintFixtureNbgvVersion -verbosity:minimal -p:XrmToolsFixtureIncludeNbgv=true \
  | sed -n 's/.*Fixture NBGV BuildVersion=//p' | tr -d '\r')"
verify_zip_version "$nbgv_version"

# Without opt-in, the staged manifest remains the version source.
build_fixture -p:XrmToolsFixtureIncludeNbgv=false -p:XrmToolsUseNbgv=false -p:XrmToolsFixtureCheckStamp=Unchanged
verify_zip_version 1.2.3.4

# Invalid values and an enabled-but-missing NBGV package must fail clearly.
if build_fixture -p:XrmToolsSolutionVersion=1.2.3-beta >"$repo_root/artifacts/invalid-version.log" 2>&1; then
  echo "Invalid solution version unexpectedly succeeded." >&2
  exit 1
fi
grep -Fq "must contain exactly four nonnegative numeric components" "$repo_root/artifacts/invalid-version.log"

if build_fixture -p:XrmToolsSolutionVersion=2147483648.0.0.0 >"$repo_root/artifacts/overflow-version.log" 2>&1; then
  echo "Overflowing solution version unexpectedly succeeded." >&2
  exit 1
fi
grep -Fq "XTB1003" "$repo_root/artifacts/overflow-version.log"
grep -Fq "outside the supported range 0..2147483647" "$repo_root/artifacts/overflow-version.log"

if build_fixture -p:XrmToolsFixtureIncludeNbgv=false -p:XrmToolsUseNbgv=true >"$repo_root/artifacts/missing-nbgv.log" 2>&1; then
  echo "XrmToolsUseNbgv unexpectedly succeeded without NBGV." >&2
  exit 1
fi
grep -Fq "XrmToolsUseNbgv is true, but Nerdbank.GitVersioning is not imported" "$repo_root/artifacts/missing-nbgv.log"

manifest_after="$(manifest_hash)"
if [[ "$manifest_before" != "$manifest_after" ]]; then
  echo "Source-controlled Solution.xml was modified." >&2
  exit 1
fi

NUGET_PACKAGES="$nuget_cache" dotnet msbuild "$fixture" -target:XrmToolsPrintConfiguration \
  -verbosity minimal -p:RestoreAdditionalProjectSources="$package_dir" | grep -F "XrmTools.Build imported" >/dev/null

echo "Phase 1/2 fixture passed; local package feed: $package_dir"
python3 "$repo_root/eng/test-targets.py"
python3 "$repo_root/eng/test-artifacts.py"
python3 "$repo_root/eng/test-staging.py"
python3 "$repo_root/eng/test-execution.py"
