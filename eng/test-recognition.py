#!/usr/bin/env python3
"""Opt-in package artifact experiment; consumers use ordinary references."""

import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import uuid
import xml.etree.ElementTree as ET
import zipfile


ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"
RUN = Path(tempfile.mkdtemp(prefix="recognition ", dir=ARTIFACTS))
CACHE = Path(os.environ.get("NUGET_PACKAGES", ARTIFACTS / "nuget-cache"))
ENV = {**os.environ, "NUGET_PACKAGES": str(CACHE)}
NS = "http://schemas.microsoft.com/developer/msbuild/2003"
ET.register_namespace("", NS)


def command(project, *args, success=True, label="probe"):
    result = subprocess.run(["dotnet", "msbuild", str(project), "-nologo", *args],
                            cwd=project.parent, env=ENV, capture_output=True, text=True)
    output = result.stdout + result.stderr
    log = RUN / f"{label}-{len(list(RUN.glob('*.log'))):03d}.log"
    log.write_text(output)
    if (result.returncode == 0) != success:
        raise AssertionError(f"Unexpected result; see {log}\n{output[-8000:]}")
    return output


def query(project):
    output = command(project, "-t:XrmToolsGetPluginPackageProjects",
                     "-getItem:XrmToolsPluginPackageProject,ProjectReference",
                     label="read-only-recognition")
    return json.loads(output)["Items"]


def fixture(name, version, compatible=True, ordinary=False, microsoft_only=False):
    destination = RUN / name / "examples"
    shutil.copytree(ROOT / "examples", destination,
                    ignore=shutil.ignore_patterns("bin", "obj", "packages", ".vscode"))
    config = destination / "NuGet.Config"
    document = ET.parse(config)
    document.find("./packageSources/add[@key='xrmtools-local']").set(
        "value", str(ARTIFACTS / "local-feed"))
    document.write(config, encoding="utf-8")
    project = destination / "automatic/Solution.cdsproj"
    document = ET.parse(project)
    root = document.getroot()
    if compatible:
        root.find(f"{{{NS}}}PropertyGroup/{{{NS}}}TargetFramework").text = "net48"
        root.find(f"{{{NS}}}PropertyGroup/{{{NS}}}TargetFrameworkVersion").text = "v4.8"
    root.find(f"{{{NS}}}PropertyGroup/{{{NS}}}MicrosoftSolutionBuildVersion").text = version
    items = root.find(f"{{{NS}}}ItemGroup")
    if ordinary:
        ET.SubElement(items, f"{{{NS}}}ProjectReference", {"Include": "Ordinary/Ordinary.csproj"})
    if microsoft_only:
        for item in list(items):
            if item.get("Include") == "XrmTools.Build":
                items.remove(item)
    document.write(project, encoding="utf-8", xml_declaration=True)
    return project


def observe(project):
    # Instrument the consumer and real producer through ordinary custom imports,
    # without changing either Microsoft targets or reference metadata.
    (project.parent / "Directory.Build.targets").write_text("""<Project>
  <Target Name="ProbeLateReferenceMetadata" BeforeTargets="_XrmToolsSelectCurrentRecognizedReferences"
          Condition="'$(MSBuildProjectExtension)' == '.cdsproj'">
    <ItemGroup>
      <ProjectReference Update="Plugin/Plugin.csproj" ProbeLateMetadata="preserved" />
    </ItemGroup>
  </Target>
  <Target Name="ProbeBeforeOutputs" BeforeTargets="ProcessCdsProjectReferencesOutputs"
          DependsOnTargets="_XrmToolsFilterMicrosoftProjectOutputs"
          Condition="'$(MSBuildProjectExtension)' == '.cdsproj'">
    <WriteLinesToFile File="hooks.log" Lines="before" />
    <WriteLinesToFile File="hooks.log" Lines="@(ProjectReference)" />
  </Target>
  <Target Name="ProbeAfterOutputs" AfterTargets="ProcessCdsProjectReferencesOutputs"
          DependsOnTargets="_XrmToolsRestoreMicrosoftProjectReferences"
          Condition="'$(MSBuildProjectExtension)' == '.cdsproj'">
    <Error Condition="'%(ProjectReference.Filename)' == 'Plugin' and '%(ProjectReference.ProbeLateMetadata)' != 'preserved'"
           Text="Reference metadata added after recognition was lost." />
    <WriteLinesToFile File="hooks.log" Lines="after" />
    <WriteLinesToFile File="hooks.log" Lines="@(ProjectReference)" />
  </Target>
  <Target Name="ProbeBeforePack" BeforeTargets="Pack" Condition="'$(MSBuildProjectName)' == 'Plugin'">
    <WriteLinesToFile File="$(MSBuildProjectDirectory)/pack.log" Lines="before|$(NoBuild)" />
  </Target>
  <Target Name="ProbeAfterPack" AfterTargets="Pack" Condition="'$(MSBuildProjectName)' == 'Plugin'">
    <WriteLinesToFile File="$(MSBuildProjectDirectory)/pack.log" Lines="after|$(NoBuild)|$(_XrmToolsPackInvalidated)" />
  </Target>
</Project>""")


def verify(project):
    package = project.parent / "Plugin/bin/Debug/Plugin.1.0.0.nupkg"
    with zipfile.ZipFile(project.parent / "bin/Debug/Solution.zip") as archive:
        names = archive.namelist()
        nested = [name for name in names if name.endswith(".nupkg")]
        assert nested == ["pluginpackages/xt_Plugin/package/xt_Plugin.nupkg"], nested
        assert archive.read(nested[0]) == package.read_bytes()
        with zipfile.ZipFile(io.BytesIO(archive.read(nested[0]))) as plugin_archive:
            assert plugin_archive.read("lib/net48/Plugin.dll") == (
                project.parent / "Plugin/bin/Debug/net48/Plugin.dll").read_bytes()
            nuspec = ET.fromstring(plugin_archive.read("Plugin.nuspec"))
            assert nuspec.findtext("{*}metadata/{*}id") == "Plugin"
            assert nuspec.findtext("{*}metadata/{*}version") == "1.0.0"
        control = next(name for name in names if name.endswith("/bundle.js"))
        assert archive.read(control) == (project.parent.parent / "Control/src/index.js").read_bytes()
        metadata = ET.fromstring(archive.read("pluginpackages/xt_Plugin/pluginpackage.xml"))
        assert metadata.findtext("version") == "4.5.6.7"
    return hashlib.sha256(package.read_bytes()).hexdigest()


class AutomaticRecognition(unittest.TestCase):
    def test_pac_defaults_fail_restore_before_recognition_for_both_microsoft_versions(self):
        for version in ("2.13.1", "2.14.1"):
            with self.subTest(version=version):
                project = fixture(f"pac-default-{version}", version, compatible=False, ordinary=True)
                output = command(project, "-t:Restore", success=False, label="pac-default-restore")
                self.assertIn("NU1201", output)
                self.assertIn("net462", output)
                self.assertIn("net48", output)
                self.assertFalse((project.parent / "Plugin/bin").exists())
                self.assertFalse((project.parent / "bin/Debug/Solution.zip").exists())

    def test_discovery_is_read_only_and_preserves_ordinary_microsoft_failure(self):
        for version in ("2.13.1", "2.14.1"):
            with self.subTest(version=version):
                project = fixture(f"mixed-{version}", version, ordinary=True)
                command(project, "-t:Restore", label="mixed-restore")
                graph = project.parent / "graph.json"
                command(project, "-t:GenerateRestoreGraphFile", f"-p:RestoreGraphOutputPath={graph}")
                names = {Path(path).name for path in json.loads(graph.read_text())["projects"]}
                self.assertTrue({"Plugin.csproj", "Ordinary.csproj", "ExampleControl.pcfproj"} <= names)
                state = query(project)
                self.assertEqual([Path(item["Identity"]).name for item in
                                  state["XrmToolsPluginPackageProject"]], ["Plugin.csproj"])
                self.assertEqual(len(state["ProjectReference"]), 3)
                for item in state["ProjectReference"]:
                    self.assertNotIn("XrmToolsPluginPackage", item)
                    self.assertNotIn("ReferenceOutputAssembly", item)
                self.assertFalse(list(project.parent.rglob("*.nupkg")))
                self.assertFalse(list(project.parent.rglob("bin")))
                output = command(project, "-t:Build", "-v:diagnostic", success=False,
                                 label="ordinary-reference-failure")
                self.assertIn("MSB4057", output)
                self.assertIn("GetProjectOutputPath", output)
                self.assertIn("Ordinary.csproj", output)
                self.assertFalse(list((project.parent / "Ordinary").rglob("*.nupkg")))
                self.assertFalse((project.parent / "bin/Debug/Solution.zip").exists())
                baseline = fixture(f"microsoft-only-mixed-{version}", version,
                                   ordinary=True, microsoft_only=True)
                command(baseline, "-t:Restore")
                output = command(baseline, "-t:Build", success=False, label="microsoft-only-mixed")
                self.assertIn("MSB4057", output)
                self.assertIn("GetProjectOutputPath", output)

    def test_plain_reference_builds_exact_current_package_and_keeps_compile_incremental(self):
        for version in ("2.13.1", "2.14.1"):
            with self.subTest(version=version):
                project = fixture(f"plain-compatible-{version}", version)
                observe(project)
                manifest = project.parent.parent / "Solution/src/Other/Solution.xml"
                source_bytes = manifest.read_bytes()
                command(project, "-t:Restore")
                self.assertEqual(len(query(project)["XrmToolsPluginPackageProject"]), 1)
                self.assertFalse((project.parent / "Plugin/pack.log").exists())
                producer = project.parent / "Plugin"
                dll = producer / "bin/Debug/net48/Plugin.dll"
                hashes = []
                for index in range(3):
                    if index == 2:
                        source = producer / "Plugin1.cs"
                        source.write_text(source.read_text() + """
namespace Plugin { public static class Revision { public const string Value = "changed"; } }
""")
                        pcf = project.parent.parent / "Control/src/index.js"
                        pcf.write_text(pcf.read_text() + "\nexport const revision = 'changed';\n")
                    output = command(project, "-t:Build", "-v:diagnostic",
                                     "-p:XrmToolsSolutionVersion=4.5.6.7", label="plain-compatible-build")
                    self.assertEqual(manifest.read_bytes(), source_bytes)
                    hashes.append(verify(project))
                    current = (dll.read_bytes(), dll.stat().st_mtime_ns)
                    if index == 1:
                        self.assertEqual(compiled, current, "unchanged Build recompiled the producer")
                    if index == 2:
                        self.assertNotEqual(compiled[0], current[0])
                        self.assertNotEqual(hashes[1], hashes[2])
                    compiled = current
                    hooks = (project.parent / "hooks.log").read_text().splitlines()
                    self.assertEqual(hooks, [
                        "before", "../Control/ExampleControl.pcfproj", "after",
                        "../Control/ExampleControl.pcfproj", "Plugin/Plugin.csproj",
                    ] * (index + 1))
                    packs = (producer / "pack.log").read_text().splitlines()
                    self.assertEqual(packs, [
                        "before|", "after||", "before|true", "after|true|true",
                    ] * (index + 1))
                    self.assertIn("_XrmToolsInvalidateIncrementalPack", output)

    def test_explicit_false_and_marked_overrides_are_preserved(self):
        project = fixture("overrides", "2.14.1")
        command(project, "-t:Restore")
        document = ET.parse(project)
        reference = document.find(f".//{{{NS}}}ProjectReference")
        reference.set("XrmToolsPluginPackage", "false")
        document.write(project)
        self.assertEqual(query(project)["XrmToolsPluginPackageProject"], [])
        reference.set("XrmToolsPluginPackage", "true")
        reference.set("XrmToolsPluginPackageUniqueName", "custom_Override")
        document.write(project)
        state = query(project)["XrmToolsPluginPackageProject"]
        self.assertEqual(len(state), 1)
        self.assertEqual(state[0]["XrmToolsPluginPackageUniqueName"], "custom_Override")
        command(project, "-t:Build", "-p:XrmToolsSolutionVersion=4.5.6.7")
        with zipfile.ZipFile(project.parent / "bin/Debug/Solution.zip") as archive:
            self.assertIn("pluginpackages/custom_Override/package/custom_Override.nupkg",
                          archive.namelist())

    def test_real_microsoft_plugin_output_requires_assembly_registration_without_filter(self):
        project = fixture("microsoft-only-plugin", "2.14.1", microsoft_only=True)
        command(project, "-t:Restore")
        output = command(project, "-t:Build", success=False, label="microsoft-plugin-output")
        self.assertIn("Unable to find assembly registration configuration", output)
        self.assertIn("PluginAssemblies", output)
        self.assertFalse((project.parent / "bin/Debug/Solution.zip").exists())


class DevelopmentDependency(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        suffix = uuid.uuid4().hex
        cls.versions = {False: f"0.5.0-nodev-{suffix}", True: f"0.5.0-dev-{suffix}"}
        for development, version in cls.versions.items():
            result = subprocess.run(
                ["dotnet", "pack", str(ROOT / "XrmTools.Build.csproj"), "--no-build",
                 "--output", str(ARTIFACTS / "local-feed"), "--verbosity", "quiet",
                 "-p:XrmToolsPrototypeRecognition=true", f"-p:PackageVersion={version}",
                 f"-p:DevelopmentDependency={str(development).lower()}"],
                cwd=ROOT, env=ENV, capture_output=True, text=True)
            if result.returncode:
                raise AssertionError(result.stdout + result.stderr)
            with zipfile.ZipFile(ARTIFACTS / f"local-feed/XrmTools.Build.{version}.nupkg") as package:
                metadata = ET.fromstring(package.read("XrmTools.Build.nuspec")).find("{*}metadata")
                assert (metadata.findtext("{*}developmentDependency") == "true") == development
                assert not metadata.findall(".//{*}dependency")

    def exercise(self, name, development, private=None, install=False, include=None):
        version = self.versions[development]
        project = fixture(f"development-dependency-{name}", "2.14.1")
        producer = project.parent / "Plugin/Plugin.csproj"
        for path in (project, producer):
            document = ET.parse(path)
            for group in document.getroot():
                for reference in list(group):
                    if reference.get("Include") == "XrmTools.Build":
                        reference.set("Version", version)
                        reference.attrib.pop("PrivateAssets", None)
                        if path == producer:
                            if private is not None:
                                reference.set("PrivateAssets", private)
                            if include is not None:
                                reference.set("IncludeAssets", include)
                            if install and private is None:
                                group.remove(reference)
            if path == producer:
                group = ET.SubElement(document.getroot(), "ItemGroup")
                ET.SubElement(group, "PackageReference", Include="Newtonsoft.Json", Version="13.0.3")
            document.write(path, encoding="utf-8", xml_declaration=True)
        if install:
            result = subprocess.run(
                ["dotnet", "add", str(producer), "package", "XrmTools.Build", "--version", version],
                cwd=producer.parent, env=ENV, capture_output=True, text=True)
            output = result.stdout + result.stderr
            (project.parent / "install.log").write_text(output)
            self.assertEqual(result.returncode, 0, output)
            reference = ET.parse(producer).find(".//PackageReference[@Include='XrmTools.Build']")
            self.assertEqual(reference.get("PrivateAssets") or reference.findtext("PrivateAssets"),
                             private or "all")
            included = reference.get("IncludeAssets") or reference.findtext("IncludeAssets")
            assets = set(included.lower().replace(" ", "").split(";"))
            if include is None:
                self.assertNotIn("compile", assets)
                self.assertIn("build", assets)
                self.assertIn("runtime", assets)
            else:
                self.assertEqual(assets, set(include.split(";")))
        before = {path: path.read_bytes() for path in (project, producer)}
        manifest = project.parent.parent / "Solution/src/Other/Solution.xml"
        before[manifest] = manifest.read_bytes()
        command(project, "-t:Restore", label=f"{name}-restore")
        recognized = query(project)["XrmToolsPluginPackageProject"]
        self.assertEqual([Path(item["Identity"]).name for item in recognized], ["Plugin.csproj"])
        self.assertFalse((producer.parent / "bin").exists(), "Restore/query built the producer")
        for path in (project, producer):
            self.assertIn("XrmTools.Build imported", command(path, "-t:XrmToolsPrintConfiguration"))
        for label in ("cold", "repeated", "producer-rebuild"):
            if label == "producer-rebuild":
                command(producer, "-t:Rebuild", label=f"{name}-producer-rebuild")
                command(producer, "-t:Pack", "-p:NoBuild=true", label=f"{name}-producer-pack-nobuild")
            output = command(project, "-t:Build", "-p:XrmToolsSolutionVersion=4.5.6.7",
                             label=f"{name}-{label}")
            verify(project)
            package = producer.parent / "bin/Debug/Plugin.1.0.0.nupkg"
            with zipfile.ZipFile(package) as archive:
                metadata = ET.fromstring(archive.read("Plugin.nuspec")).find("{*}metadata")
                dependencies = {item.get("id"): item.attrib for item in
                                metadata.findall(".//{*}dependency")}
                self.assertEqual(metadata.findtext("{*}version"), "1.0.0")
                self.assertEqual(dependencies["Newtonsoft.Json"], {
                    "id": "Newtonsoft.Json", "version": "13.0.3", "exclude": "Build,Analyzers"})
                excluded = private == "all" or install
                self.assertEqual("XrmTools.Build" not in dependencies, excluded)
                if not excluded:
                    self.assertEqual(dependencies["XrmTools.Build"], {
                        "id": "XrmTools.Build", "version": version, "exclude": "Build,Analyzers"})
                    self.assertIn("NU5104", output)
                else:
                    self.assertNotIn("NU5104", output)
                (project.parent / f"{label}-Plugin.nuspec").write_bytes(archive.read("Plugin.nuspec"))
            self.assertEqual(before, {path: path.read_bytes() for path in before},
                             "Restore/build modified consumer project or source metadata")

    def test_before_plain_reference_leaks_dependency(self):
        self.exercise("before-plain", False)

    def test_before_private_assets_control(self):
        self.exercise("before-private", False, private="all")

    def test_development_dependency_does_not_rewrite_manual_reference(self):
        self.exercise("after-manual", True)

    def test_install_writes_private_metadata_and_preserves_build_integration(self):
        self.exercise("after-install", True, install=True)

    def test_install_preserves_explicit_consumer_metadata(self):
        self.exercise("after-explicit", True, private="all", include="build;analyzers", install=True)


if __name__ == "__main__":
    print(f"Recognition fixtures and logs: {RUN}", flush=True)
    unittest.main(verbosity=2)
