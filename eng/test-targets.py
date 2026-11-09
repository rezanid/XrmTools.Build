#!/usr/bin/env python3
"""Target and real Microsoft packaging tests; no third-party test dependencies."""

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile


ET.register_namespace("", "http://schemas.microsoft.com/developer/msbuild/2003")

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"
CACHE = ARTIFACTS / "nuget-cache"
FEED = ARTIFACTS / "local-feed"
VERSION = ET.parse(ROOT / "XrmTools.Build.csproj").findtext("./PropertyGroup/Version")
TARGETS = CACHE / "xrmtools.build" / VERSION / "build" / "XrmTools.Build.targets"
ENV = {**os.environ, "NUGET_PACKAGES": str(CACHE)}
RUN = Path(tempfile.mkdtemp(prefix="phase3 tests ", dir=ARTIFACTS))


def msbuild(project, *arguments, success=True, label="build"):
    result = subprocess.run(
        ["dotnet", "msbuild", str(project), "-nologo", "-v:minimal",
         f"-p:RestoreAdditionalProjectSources={FEED}", *arguments],
        cwd=project.parent, env=ENV, text=True, capture_output=True,
    )
    output = result.stdout + result.stderr
    log = RUN / f"{label}-{len(list(RUN.glob('*.log'))):03d}.log"
    log.write_text(output)
    if success and result.returncode:
        raise AssertionError(f"MSBuild failed; see {log}\n" + "\n".join(output.splitlines()[-25:]))
    if not success and result.returncode == 0:
        raise AssertionError(f"MSBuild unexpectedly passed; see {log}")
    return output


def query(output):
    match = re.search(r'(?m)^\{\s*\n\s*"(?:Items|Properties)"', output)
    if not match:
        raise AssertionError(f"MSBuild did not return JSON:\n{output}")
    return json.JSONDecoder().raw_decode(output[match.start():])[0]


def fixture(name):
    destination = RUN / name / "Fixtures"
    shutil.copytree(ROOT / "tests" / "Fixtures", destination,
                    ignore=shutil.ignore_patterns("bin", "obj"))
    return destination


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class VersionTargets(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = fixture("version targets")
        cls.project = cls.tree / "MinimalSolution" / "MinimalSolution.cdsproj"
        msbuild(cls.project, "-t:Restore", label="version-restore")

    def resolve(self, version=None, **options):
        arguments = ["-t:XrmToolsResolveSolutionVersion", "-v:diagnostic"]
        if version is not None:
            arguments.append(f"-p:XrmToolsSolutionVersion={version}")
        return msbuild(self.project, *arguments, **options)

    def test_matching_staged_version_is_not_written(self):
        for version in (None, "1.2.3.4"):
            with self.subTest(version=version):
                output = self.resolve(version, label="stamp-unchanged")
                self.assertTrue('Task "XmlPoke"' not in output, "XmlPoke ran for an unchanged version")

    def test_differing_version_is_written_then_idempotent(self):
        self.resolve("8.9.10.11", label="stamp-changed")
        staged = self.project.parent / "obj" / "Debug" / "Metadata" / "Other" / "Solution.xml"
        self.assertEqual(ET.parse(staged).findtext("./SolutionManifest/Version"), "8.9.10.11")
        before = (digest(staged), staged.stat().st_mtime_ns)
        # Source is recopied by Microsoft's target per invocation; match the new source version
        # in this disposable fixture to test the no-write path on the same staged bytes.
        source = self.project.parent / "src" / "Other" / "Solution.xml"
        original = source.read_bytes()
        try:
            shutil.copyfile(staged, source)
            shutil.copystat(staged, source)
            output = self.resolve("8.9.10.11", label="stamp-repeat")
            self.assertTrue('Task "XmlPoke"' not in output, "XmlPoke ran for a repeated matching version")
            self.assertEqual(before, (digest(staged), staged.stat().st_mtime_ns))
        finally:
            source.write_bytes(original)

    def test_invalid_versions_have_extension_diagnostics(self):
        for version in (
            "1.2.3", "1.2.3-beta", "-1.2.3.4", "1.2.3.4.5",
            "1.2.3.4\n", "1.2. 3.4", "1.2.3.2147483648",
            "2147483648.0.0.0", "999999999999999999999999.0.0.0",
            "1.2.3.4+metadata", "1.2'3.4", "`1.2.3.4", "1.2.3.4'",
        ):
            with self.subTest(version=version):
                output = self.resolve(version, success=False, label="invalid-version")
                self.assertIn("error XTB1003:", output)
                self.assertNotIn("MSB4184", output)
                self.assertNotIn("System.Version", output)

    def test_supported_component_boundaries(self):
        for version in ("0.0.0.0", "2147483647.2147483647.2147483647.2147483647",
                        "00000000000000000001.02.003.0004"):
            with self.subTest(version=version):
                self.resolve(version, label="version-boundary")
                staged = self.project.parent / "obj/Debug/Metadata/Other/Solution.xml"
                self.assertEqual(ET.parse(staged).findtext("./SolutionManifest/Version"), version)

    def test_missing_manifest_is_actionable(self):
        self.assertIn("error XTB1002:", msbuild(
            self.project, "-t:XrmToolsResolveSolutionVersion", "-p:SolutionRootPath=missing",
            "-p:IntermediateOutputPath=obj/missing/", success=False, label="missing-manifest"))

    def test_invalid_manifest_version_nodes_are_actionable(self):
        source = self.project.parent / "src/Other/Solution.xml"
        original = source.read_bytes()
        try:
            for versions, code in (([], "XTB1002"), (["1.2.3.4", "1.2.3.4"], "XTB1002"),
                                   ([""], "XTB1003")):
                with self.subTest(versions=versions):
                    document = ET.fromstring(original)
                    manifest = document.find("./SolutionManifest")
                    manifest.remove(manifest.find("Version"))
                    for version in versions:
                        ET.SubElement(manifest, "Version").text = version
                    source.write_bytes(ET.tostring(document))
                    output = self.resolve(success=False, label="invalid-manifest")
                    self.assertIn(f"error {code}:", output)
        finally:
            source.write_bytes(original)

    def test_microsoft_versioning_conflict_is_diagnostic_not_version_gate(self):
        output = msbuild(self.project, "-t:_XrmToolsCheckSolutionTooling",
                         "-p:SolutionVersionStrategy=Solution", label="tooling-conflict")
        self.assertIn("warning XTB1001:", output)

    def test_source_staging_collision_is_rejected(self):
        self.assertIn("points at the source Solution.xml", msbuild(
            self.project, "-t:XrmToolsResolveSolutionVersion",
            "-p:SolutionPackagerMetadataWorkingDirectory=src", success=False, label="source-collision"))

    def test_missing_microsoft_import_is_actionable(self):
        project = RUN / "MissingTooling.cdsproj"
        project.write_text(
            f'<Project><Import Project="{TARGETS}"/>'
            '<Target Name="Build" DependsOnTargets="_XrmToolsCheckSolutionTooling"/></Project>')
        output = msbuild(project, "-t:Build", success=False, label="missing-tooling")
        self.assertIn("error XTB1000:", output)
        self.assertIn("Restore a Microsoft.PowerApps.MSBuild.Solution PackageReference", output)


class ReferenceIntegration(unittest.TestCase):
    def build_mixed(self, count=2, microsoft="2.14.1", **properties):
        tree = fixture(f"mixed-{count}-{microsoft}-{len(list(RUN.iterdir()))}")
        project = tree / "MixedReferences" / "MixedReferences.cdsproj"
        source_xml = [path for path in tree.rglob("*.xml")
                      if not {"obj", "bin"}.intersection(path.relative_to(tree).parts)]
        before = {path: digest(path) for path in source_xml}
        parameters = [f"-p:FixtureProducerCount={count}", f"-p:FixtureMicrosoftVersion={microsoft}",
                      "-p:XrmToolsSolutionVersion=4.5.6.7"]
        parameters += [f"-p:{key}={value}" for key, value in properties.items()]
        msbuild(project, "-t:Restore", *parameters, label="mixed-restore")
        preprocessed = project.parent / "preprocessed.xml"
        msbuild(project, f"-preprocess:{preprocessed}", *parameters, label="mixed-imports")
        imports = ET.parse(preprocessed).getroot()
        for name in ("CopyCdsSolutionContent", "ProcessCdsProjectReferencesOutputs", "PowerAppsPackage"):
            self.assertEqual(len(imports.findall(f'./{{*}}Target[@Name="{name}"]')), 1,
                             f"Microsoft target {name} was replaced or not imported")
        graph_path = project.parent / "obj" / "complete-restore-graph.json"
        msbuild(project, "-t:GenerateRestoreGraphFile", f"-p:RestoreGraphOutputPath={graph_path}",
                *parameters, label="restore-graph")
        graph = json.loads(graph_path.read_text())
        # Per-project dgspecs omit assembly dependencies when ReferenceOutputAssembly=false.
        # NuGet's complete recursive restore graph must still include all projects.
        referenced = {Path(path).name for path in graph["projects"] if path != str(project)}
        self.assertIn("Control.pcfproj", referenced)
        self.assertIn("Ordinary.csproj", referenced)
        self.assertEqual("ProducerA.csproj" in referenced, count > 0)
        self.assertEqual("ProducerB.csproj" in referenced, count > 1)

        log = msbuild(project, "-t:Build", "-m:2", "-v:diagnostic",
                      f"-bl:{project.parent / 'build.binlog'}", *parameters, label="mixed-build")
        self.assertIn("Unmanaged Pack complete", log)
        self.assertEqual("warning XTB2005:" in log, count > 0)
        sequence = ("CopyCdsSolutionContent", "_XrmToolsFilterMicrosoftProjectOutputs",
                    "ProcessCdsProjectReferencesOutputs", "_XrmToolsRestoreMicrosoftProjectReferences",
                    "XrmToolsResolveSolutionVersion", "PowerAppsPackage")
        positions = [log.index(f'Target "{name}:') for name in sequence
                     if count or name != "_XrmToolsRestoreMicrosoftProjectReferences"]
        self.assertEqual(positions, sorted(positions))
        self.assertTrue((project.parent / "Ordinary/obj/Debug/net462/output-contract.txt").exists())
        for name in ("ProducerA", "ProducerB")[:count]:
            configuration = "Release" if name == "ProducerB" else "Debug"
            records = (project.parent / name / f"obj/{configuration}/net462/build-count.txt").read_text().splitlines()
            self.assertEqual(records, [f"Computed.{name}|5.6.7-beta|5.6.7-beta|5.6.7.0|{name[-1]}|{configuration}"])
        archive = project.parent / "bin" / "Debug" / "MixedReferences.zip"
        with zipfile.ZipFile(archive) as package:
            solution = ET.fromstring(package.read("solution.xml"))
            self.assertEqual(solution.findtext("./SolutionManifest/Version"), "4.5.6.7")
            self.assertEqual(solution.findtext("./SolutionManifest/Publisher/CustomizationPrefix"), "xt")
            self.assertIsNotNone(solution.find(
                "./SolutionManifest/RootComponents/RootComponent[@schemaName='xt_XrmToolsFixture.Control']"))
            files = package.namelist()
            for name in ("ControlManifest.xml", "bundle.js"):
                self.assertEqual(package.read(f"Controls/xt_XrmToolsFixture.Control/{name}"),
                                 (project.parent / f"Control/prebuilt/{name}").read_bytes())
            self.assertFalse(any(path.endswith(".nupkg") for path in files), files)
        self.assertEqual(before, {path: digest(path) for path in source_xml})
        # Calling the public query target returns metadata without packing or rebuilding producers.
        state = query(msbuild(project, "-t:XrmToolsGetPluginPackageProjects",
                              "-getItem:ProjectReference,XrmToolsPluginPackageProject",
                              *parameters, label="reference-query"))["Items"]
        self.assertEqual(len(state["ProjectReference"]), count + 2)
        self.assertEqual(len(state["XrmToolsPluginPackageProject"]), count)
        if count:
            producer = state["XrmToolsPluginPackageProject"][0]
            self.assertEqual(producer["ManagedIdentityId"], "1a71c21a-cd2e-40f0-8a91-a31608d19900")
            self.assertEqual(producer["FixtureUnknownMetadata"], "preserve me")
        # A direct reference-output invocation also restores ProjectReference after the boundary.
        state = query(msbuild(project, "-t:ProcessCdsProjectReferencesOutputs",
                              "-getItem:ProjectReference", *parameters, label="direct-output"))["Items"]
        self.assertEqual(len(state["ProjectReference"]), count + 2)
        for name in ("ProducerA", "ProducerB")[:count]:
            configuration = "Release" if name == "ProducerB" else "Debug"
            self.assertEqual(len((project.parent / name / f"obj/{configuration}/net462/build-count.txt")
                                 .read_text().splitlines()), 1)
        return project, parameters

    def test_zero_one_multiple_producers_with_pcf(self):
        for count in (0, 1, 2):
            with self.subTest(count=count):
                self.build_mixed(count)

    def test_previous_microsoft_solution_package(self):
        self.build_mixed(microsoft="2.13.1")

    def test_no_dependency_build_requested(self):
        project, parameters = self.build_mixed()
        msbuild(project, "-t:Build", "-p:BuildProjectReferences=false",
                *parameters, label="no-dependency-build")
        for name in ("ProducerA", "ProducerB"):
            configuration = "Release" if name == "ProducerB" else "Debug"
            self.assertEqual(len((project.parent / name / f"obj/{configuration}/net462/build-count.txt")
                                 .read_text().splitlines()), 1)

    def test_unmarked_producer_is_not_silently_filtered(self):
        tree = fixture("unmarked producer")
        project = tree / "MixedReferences/MixedReferences.cdsproj"
        document = ET.parse(project)
        ns = {"m": "http://schemas.microsoft.com/developer/msbuild/2003"}
        references = document.findall("./m:ItemGroup/m:ProjectReference", ns)
        references[0].find("m:XrmToolsPluginPackage", ns).text = "false"
        # Remove fixture-only boundary assertions because this case intentionally
        # sends a producer without GetProjectOutputPath through Microsoft's target.
        for target in document.findall("./m:Target", ns):
            document.getroot().remove(target)
        document.write(project)
        msbuild(project, "-t:Restore", label="unmarked-restore")
        output = msbuild(project, "-t:Build", success=False, label="unmarked-build")
        self.assertIn("MSB4057", output)
        self.assertIn("GetProjectOutputPath", output)
        self.assertFalse((project.parent / "bin/Debug/MixedReferences.zip").exists())

    def test_same_identity_unmarked_reference_survives_filter(self):
        tree = fixture("shared identity")
        project = tree / "MixedReferences/MixedReferences.cdsproj"
        document = ET.parse(project)
        ns = {"m": "http://schemas.microsoft.com/developer/msbuild/2003"}
        group = document.find("./m:ItemGroup", ns)
        ET.SubElement(group, f'{{{ns["m"]}}}ProjectReference', {
            "Include": "ProducerA/ProducerA.csproj", "XrmToolsPluginPackage": "false",
            "ReferenceOutputAssembly": "false",
        })
        for target in document.findall("./m:Target", ns):
            document.getroot().remove(target)
        document.write(project)
        msbuild(project, "-t:Restore", label="same-identity-restore")
        output = msbuild(project, "-t:ProcessCdsProjectReferencesOutputs",
                         success=False, label="same-identity-output")
        self.assertIn("MSB4057", output)
        self.assertIn("GetProjectOutputPath", output)

    def test_reference_validation_and_returns_contract(self):
        tree = fixture("reference validation")
        producer = tree / "MixedReferences/ProducerA/ProducerA.csproj"
        pcf = tree / "MixedReferences/Control/Control.pcfproj"
        scenarios = [
            (f'<ProjectReference Include="{producer}" XrmToolsPluginPackage="yes"/>', "XTB2000"),
            ('<ProjectReference Include="absent.csproj" XrmToolsPluginPackage="true"/>', "XTB2001"),
            (f'<ProjectReference Include="{pcf}" XrmToolsPluginPackage="true"/>', "XTB2002"),
            (f'<ProjectReference Include="{producer}" XrmToolsPluginPackage="true"/>'
             f'<ProjectReference Include="{producer.parent}/../ProducerA/ProducerA.csproj" XrmToolsPluginPackage="true"/>', "XTB2003"),
            (f'<ProjectReference Include="{producer}" XrmToolsPluginPackage="true" XrmToolsPluginPackageUniqueName="xt_duplicate"/>'
             f'<ProjectReference Include="{tree / "MixedReferences/ProducerB/ProducerB.csproj"}" XrmToolsPluginPackage="true" XrmToolsPluginPackageUniqueName="XT_DUPLICATE"/>', "XTB2004"),
        ]
        for index, (items, code) in enumerate(scenarios):
            with self.subTest(code=code):
                project = RUN / f"InvalidReference{index}.cdsproj"
                project.write_text(f'<Project><Import Project="{TARGETS}"/><ItemGroup>{items}</ItemGroup></Project>')
                self.assertIn(f"error {code}:", msbuild(
                    project, "-t:XrmToolsGetPluginPackageProjects", success=False, label="invalid-reference"))
        # Exercise Returns/TargetOutputs rather than querying raw producer project XML.
        project = RUN / "ReferenceContract.cdsproj"
        project.write_text(f'<Project><Import Project="{TARGETS}"/><ItemGroup>'
                           f'<ProjectReference Include="{producer}" XrmToolsPluginPackage="TrUe"'
                           ' XrmToolsPluginPackageUniqueName="xt_returned"/></ItemGroup></Project>')
        caller = RUN / "Caller.proj"
        caller.write_text(
            f'<Project><Target Name="Check"><MSBuild Projects="{project}" Targets="XrmToolsGetPluginPackageProjects">'
            '<Output TaskParameter="TargetOutputs" ItemName="Returned"/></MSBuild>'
            '<Error Condition="\'@(Returned->Count())\' != \'1\'" Text="Expected one returned producer."/>'
            '<Error Condition="\'%(Returned.XrmToolsPluginPackageUniqueName)\' != \'xt_returned\'" Text="Lost metadata."/></Target></Project>')
        msbuild(caller, "-t:Check", label="returns-contract")


if __name__ == "__main__":
    print(f"Test fixtures, logs and binlogs: {RUN}", flush=True)
    unittest.main(verbosity=2)
