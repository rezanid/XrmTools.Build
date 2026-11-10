#!/usr/bin/env python3
"""Package-only and SDK entry-point regressions using real Microsoft build targets."""

import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile


ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"
FEED = ARTIFACTS / "local-feed"
CACHE = Path(os.environ.get("NUGET_PACKAGES", ARTIFACTS / "nuget-cache"))
VERSION = ET.parse(ROOT / "XrmTools.Build.csproj").findtext("./PropertyGroup/Version")
SDK_VERSION = "0.5.0-sdk-prototype"
RECOGNITION_VERSION = "0.5.0-recognition"
RUN = Path(tempfile.mkdtemp(prefix="consumer-contract ", dir=ARTIFACTS))
ENV = {**os.environ, "NUGET_PACKAGES": str(CACHE)}
ET.register_namespace("", "http://schemas.microsoft.com/developer/msbuild/2003")


def pack_experiments():
    for version, option in ((SDK_VERSION, "XrmToolsPrototypeSdk"),
                            (RECOGNITION_VERSION, "XrmToolsPrototypeRecognition")):
        rejected_output = RUN / f"rejected-{option}"
        rejected = subprocess.run(
            ["dotnet", "pack", str(ROOT / "XrmTools.Build.csproj"), "--no-build",
             "--output", str(rejected_output), "--verbosity", "quiet", f"-p:{option}=true"],
            cwd=ROOT, env=ENV, capture_output=True, text=True)
        assert rejected.returncode != 0, "Prototype pack accepted the default version"
        assert "Prototype assets require a distinct PackageVersion" in rejected.stdout + rejected.stderr
        assert not list(rejected_output.glob("*.nupkg"))
        subprocess.run(["dotnet", "pack", str(ROOT / "XrmTools.Build.csproj"), "--no-build",
                        "--output", str(FEED), "--verbosity", "quiet",
                        f"-p:{option}=true", f"-p:PackageVersion={version}"],
                       cwd=ROOT, env=ENV, check=True)
        cached = CACHE / "xrmtools.build" / version
        if cached.exists():
            shutil.rmtree(cached)
    with zipfile.ZipFile(FEED / f"XrmTools.Build.{VERSION}.nupkg") as baseline, \
            zipfile.ZipFile(FEED / f"XrmTools.Build.{SDK_VERSION}.nupkg") as sdk, \
            zipfile.ZipFile(FEED / f"XrmTools.Build.{RECOGNITION_VERSION}.nupkg") as recognition:
        for package in (baseline, recognition):
            assert not any(name.startswith("Sdk/") for name in package.namelist())
        assert {"Sdk/Sdk.props", "Sdk/Sdk.targets"} <= set(sdk.namelist())
        capability = "build/experiments/ProducerRecognition.targets"
        assert capability not in baseline.namelist()
        assert capability not in sdk.namelist()
        assert capability in recognition.namelist()
        for name in ("build/XrmTools.Build.props", "build/XrmTools.Build.targets"):
            assert baseline.read(name) == sdk.read(name) == recognition.read(name)
        shared_targets = [name for name in baseline.namelist()
                          if name.startswith("build/targets/") and name.endswith(".targets")]
        for name in shared_targets:
            assert baseline.read(name) == sdk.read(name) == recognition.read(name)


def digest(value):
    return hashlib.sha256(value).hexdigest()


def run(project, *arguments, success=True, label="build"):
    result = subprocess.run(
        ["dotnet", "build", str(project), "--verbosity", "minimal",
         "-p:XrmToolsSolutionVersion=4.5.6.7", *arguments],
        cwd=project.parent, env=ENV, text=True, capture_output=True,
    )
    output = result.stdout + result.stderr
    log = RUN / f"{label}-{len(list(RUN.glob('*.log'))):03d}.log"
    log.write_text(output)
    if success and result.returncode:
        raise AssertionError(f"Build failed; see {log}\n" + "\n".join(output.splitlines()[-30:]))
    if not success and result.returncode == 0:
        raise AssertionError(f"Build unexpectedly passed; see {log}")
    return output


def solution_zip(project):
    return project.parent / "bin/Debug/Solution.zip"


def verify_zip(project, source):
    with zipfile.ZipFile(solution_zip(project)) as archive:
        entries = archive.namelist()
        package_name = next(name for name in entries if name.endswith(".nupkg"))
        pcf_name = next(name for name in entries if name.endswith("/bundle.js"))
        package_bytes = archive.read(package_name)
        pcf_bytes = archive.read(pcf_name)
        source_bytes = source.read_bytes()
        producer_package = project.parent.parent.parent / "Plugin/packages/Example.Plugin.2.3.4-beta.1.nupkg"
        assert package_bytes == producer_package.read_bytes(), "final ZIP package bytes differ from producer output"
        with zipfile.ZipFile(io.BytesIO(package_bytes)) as nested:
            nuspec = ET.fromstring(nested.read(next(name for name in nested.namelist()
                                                    if name.endswith(".nuspec"))))
        metadata = nuspec.find("{*}metadata")
        assert metadata.findtext("{*}id") == "Example.Plugin"
        assert metadata.findtext("{*}version") == "2.3.4-beta.1"
        assert pcf_bytes == source_bytes, f"PCF output {pcf_name} did not reflect source"
        manifest_name = next(name for name in entries if name.endswith("/pluginpackage.xml"))
        plugin_metadata = ET.fromstring(archive.read(manifest_name))
        assert plugin_metadata.findtext("{*}version") == "4.5.6.7"
        return digest(package_bytes), digest(pcf_bytes), package_name, pcf_name


def prepare_examples(name):
    destination = RUN / name / "examples"
    shutil.copytree(ROOT / "examples", destination,
                    ignore=shutil.ignore_patterns("bin", "obj", "packages", "project.assets.json"))
    config = destination / "NuGet.Config"
    document = ET.parse(config)
    source = document.find("./packageSources/add[@key='xrmtools-local']")
    source.attrib["value"] = str(FEED)
    document.write(config, encoding="utf-8", xml_declaration=True)
    return destination


class ConsumerEntrypoints(unittest.TestCase):
    def test_both_entrypoints_share_core_and_build_source_driven_pcf(self):
        examples = prepare_examples("entry-points")
        solution_source = examples / "Solution/src/Other/Solution.xml"
        pcf_source = examples / "Control/src/index.js"
        package_project = examples / "entry-points/PackageReference/Solution.cdsproj"
        sdk_project = examples / "entry-points/Sdk/Solution.cdsproj"

        before = solution_source.read_bytes()
        run(package_project, label="package-reference")
        self.assertEqual(before, solution_source.read_bytes())
        package_result = verify_zip(package_project, pcf_source)
        package_assets = json.loads((package_project.parent / "obj/project.assets.json").read_text())
        package_libraries = {name.lower() for name in package_assets["libraries"]}
        self.assertIn(f"xrmtools.build/{VERSION}".lower(), package_libraries)

        before = solution_source.read_bytes()
        run(sdk_project, label="sdk-entrypoint")
        self.assertEqual(before, solution_source.read_bytes())
        sdk_result = verify_zip(sdk_project, pcf_source)
        sdk_assets = json.loads((sdk_project.parent / "obj/project.assets.json").read_text())
        sdk_libraries = {name.lower() for name in sdk_assets["libraries"]}
        self.assertFalse(any(name.startswith("xrmtools.build/") for name in sdk_libraries))

        preprocessed = RUN / "sdk-preprocessed.xml"
        subprocess.run(["dotnet", "msbuild", str(sdk_project), "-nologo",
                        f"-preprocess:{preprocessed}"], cwd=sdk_project.parent,
                       env=ENV, check=True, capture_output=True, text=True)
        evaluated = ET.parse(preprocessed).getroot()
        self.assertIn(f"xrmtools.build/{SDK_VERSION}/Sdk/Sdk.props".lower(),
                      preprocessed.read_text().replace("\\", "/").lower())
        for target in ("ProcessCdsProjectReferencesOutputs",
                       "XrmToolsGetPluginPackageProjects",
                       "XrmToolsDiscoverPluginPackages"):
            matches = [node for node in evaluated.iter()
                       if node.tag.endswith("Target") and node.attrib.get("Name") == target]
            self.assertEqual(len(matches), 1, f"duplicate or missing target {target}")
        self.assertEqual(package_result[2:], sdk_result[2:])

        changed = pcf_source.read_text() + "\nexport const sourceRevision = 'changed';\n"
        pcf_source.write_text(changed)
        before = solution_source.read_bytes()
        run(sdk_project, label="sdk-pcf-source-change")
        self.assertEqual(before, solution_source.read_bytes())
        changed_result = verify_zip(sdk_project, pcf_source)
        self.assertNotEqual(sdk_result[1], changed_result[1])

    def test_marker_free_project_reference_fails_microsoft_output_processing(self):
        examples = prepare_examples("marker-free")
        project = examples / "entry-points/PackageReference/Solution.cdsproj"
        document = ET.parse(project)
        for reference in document.iter():
            if (reference.tag.endswith("ProjectReference")
                    and "Plugin/ExamplePlugin.csproj" in reference.attrib.get("Include", "")):
                reference.attrib.pop("XrmToolsPluginPackage", None)
                reference.attrib.pop("XrmToolsPluginPackageUniqueName", None)
        document.write(project, encoding="utf-8", xml_declaration=True)

        output = run(project, success=False, label="marker-free-reference")
        self.assertIn("MSB4057", output)
        self.assertIn('target "GetProjectOutputPath" does not exist', output)
        self.assertFalse(solution_zip(project).exists())

    def test_sdk_wrapper_keeps_microsoft_package_version_consumer_owned(self):
        project = ET.parse(ROOT / "examples/entry-points/Sdk/Solution.cdsproj").getroot()
        package_versions = {
            node.attrib["Include"]: node.attrib["Version"]
            for node in project.iter()
            if node.tag.endswith("PackageReference") and "Version" in node.attrib
        }
        self.assertEqual(package_versions["Microsoft.PowerApps.MSBuild.Solution"],
                         "$(MicrosoftSolutionBuildVersion)")
        self.assertNotIn("XrmTools.Build", package_versions)

    @classmethod
    def setUpClass(cls):
        pack_experiments()


if __name__ == "__main__":
    print(f"Consumer-contract fixtures and logs: {RUN}", flush=True)
    unittest.main(verbosity=2)
