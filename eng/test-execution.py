#!/usr/bin/env python3
"""Execution contracts against restored build assets, not source target imports."""

from concurrent.futures import ThreadPoolExecutor
import importlib.util
import io
from pathlib import Path
import subprocess
import unittest
import xml.etree.ElementTree as ET
import zipfile

spec = importlib.util.spec_from_file_location("staging", Path(__file__).with_name("test-staging.py"))
staging = importlib.util.module_from_spec(spec)
spec.loader.exec_module(staging)
targets = staging.targets


def counts(producer):
    return {path.name: path.read_bytes() for path in (producer / "obj").glob("*count*")}


class ExecutionIntegration(unittest.TestCase):
    def test_packaged_example_is_usable_with_and_without_producer(self):
        destination = targets.RUN / "extracted package"
        with zipfile.ZipFile(targets.FEED / f"XrmTools.Build.{targets.VERSION}.nupkg") as package:
            for name in package.namelist():
                if name.startswith("examples/"):
                    package.extract(name, destination)
        project = destination / "examples/Solution/Example.cdsproj"
        source = project.parent / "src/Other/Solution.xml"
        before = source.read_bytes()
        for include in ("true", "false"):
            staging.build(project, {"IncludeExamplePlugin": include})
            with zipfile.ZipFile(staging.output_zip(project)) as package:
                self.assertEqual(ET.fromstring(package.read("solution.xml"))
                                 .findtext("./SolutionManifest/Version"), "9.8.7.6")
                entries = [n for n in package.namelist() if n.endswith(".nupkg")]
                self.assertEqual(len(entries), 1 if include == "true" else 0)
                if entries:
                    artifact = destination / "examples/Plugin/packages/Example.Plugin.2.3.4-beta.1.nupkg"
                    self.assertEqual(package.read(entries[0]), artifact.read_bytes())
        self.assertEqual(source.read_bytes(), before)

    def test_restore_and_read_only_queries_never_build_or_pack(self):
        for microsoft in ("2.13.1", "2.14.1"):
            for warm in (False, True):
                with self.subTest(microsoft=microsoft, warm=warm):
                    project, _, producer = staging.fixture("queries")
                    if warm:
                        staging.build(project, {"FixtureMicrosoftVersion": microsoft})
                    before = counts(producer)
                    packages = {p: p.read_bytes() for p in producer.rglob("*.nupkg")}
                    for target in ("Restore", "GenerateRestoreGraphFile", "XrmToolsPrintConfiguration",
                                   "XrmToolsGetPluginPackageProjects"):
                        result = targets.msbuild(project, "-t:" + target,
                                                 "-p:FixtureMicrosoftVersion=" + microsoft,
                                                 f"-p:RestoreGraphOutputPath={project.parent / 'restore-graph.json'}",
                                                 label="execution-query")
                        self.assertNotIn("validated plugin artifact", result)
                        self.assertNotIn("validated final solution ZIP", result)
                        self.assertEqual(counts(producer), before)
                        self.assertEqual({p: p.read_bytes() for p in producer.rglob("*.nupkg")}, packages)
                        self.assertFalse((project.parent / "obj/Debug/Metadata").exists())

    def test_clean_rebuild_recovery_preserves_user_package_directory(self):
        for microsoft in ("2.13.1", "2.14.1"):
            for absolute in (False, True):
                with self.subTest(microsoft=microsoft, absolute=absolute):
                    project, source, producer = staging.fixture("clean")
                    output = producer / "user packages"
                    props = {"FixtureMicrosoftVersion": microsoft,
                             "FixtureOutputPath": str(output) if absolute else "user packages"}
                    staging.build(project, props)
                    unrelated = output / "Unrelated.1.0.0.nupkg"
                    unrelated.write_bytes(b"not owned by this build")
                    nested = output / "unrelated directory"
                    nested.mkdir()
                    (nested / "keep.txt").write_text("keep")
                    packages = {p: p.read_bytes() for p in output.rglob("*") if p.is_file()}
                    sources = {p: p.read_bytes() for p in source.rglob("*") if p.is_file()}
                    before = counts(producer)
                    result = staging.build(project, props, restore=False, target="Clean")
                    self.assertNotIn("validated plugin artifact", result)
                    self.assertEqual(packages, {p: p.read_bytes() for p in packages})
                    self.assertTrue(output.is_dir())
                    self.assertEqual(counts(producer), before)
                    self.assertFalse(staging.output_zip(project).exists())
                    self.assertFalse((project.parent / "obj/Debug/Metadata").exists())
                    self.assertFalse((producer / "bin/Release/net462/ArtifactProducer.dll").exists())
                    staging.build(project, props)
                    self.assertTrue(staging.output_zip(project).exists())
                    staging.build(project, props, target="Rebuild")
                    self.assertEqual(len((producer / "obj/build-count-net462.txt").read_text().splitlines()), 3)
                    self.assertEqual(len((producer / "obj/pack-count.txt").read_text().splitlines()), 3)
                    self.assertEqual(unrelated.read_bytes(), packages[unrelated])
                    self.assertEqual(sources, {p: p.read_bytes() for p in sources})

    def test_solution_pack_is_not_a_nuget_pack_alias(self):
        for microsoft in ("2.13.1", "2.14.1"):
            project, _, producer = staging.fixture("pack")
            staging.build(project, {"FixtureMicrosoftVersion": microsoft})
            before = counts(producer)
            for no_build in ("true", "false"):
                result = targets.msbuild(project, "-t:Pack", "-p:NoBuild=" + no_build,
                                         "-p:FixtureMicrosoftVersion=" + microsoft,
                                         success=False, label="solution-pack")
                self.assertIn("MSB4057", result)
                self.assertIn('"Pack"', result)
                self.assertEqual(counts(producer), before)
                command = ["dotnet", "pack", str(project), "--no-restore",
                           "-p:FixtureMicrosoftVersion=" + microsoft]
                if no_build == "true":
                    command.append("--no-build")
                packed = subprocess.run(command, cwd=project.parent, env=targets.ENV,
                                        text=True, capture_output=True)
                output = packed.stdout + packed.stderr
                (targets.RUN / f"dotnet-pack-{microsoft}-{no_build}.log").write_text(output)
                self.assertNotEqual(packed.returncode, 0)
                self.assertIn("MSB4057", output)
                self.assertEqual(counts(producer), before)

    def test_nobuild_requires_prebuilt_references_but_regenerates_package(self):
        for microsoft in ("2.13.1", "2.14.1"):
            with self.subTest(microsoft=microsoft):
                project, _, producer = staging.fixture("nobuild")
                props = {"FixtureMicrosoftVersion": microsoft}
                staging.build(project, props)
                dll = producer / "bin/Release/net462/ArtifactProducer.dll"
                compiled = (targets.digest(dll), dll.stat().st_mtime_ns)
                before = counts(producer)
                result = staging.build(project, {**props, "NoBuild": "true"}, restore=False, success=False)
                self.assertIn("NETSDK1085", result)
                self.assertEqual(counts(producer), before)
                payload = producer / "payload.txt"
                payload.write_bytes(b"updated payload with prebuilt assembly")
                result = staging.build(project, {**props, "NoBuild": "true", "BuildProjectReferences": "false"},
                                       restore=False)
                self.assertIn("validated final solution ZIP", result)
                self.assertEqual(counts(producer)["build-count-net462.txt"], before["build-count-net462.txt"])
                self.assertEqual(len((producer / "obj/pack-count.txt").read_text().splitlines()), 2)
                self.assertEqual((targets.digest(dll), dll.stat().st_mtime_ns), compiled)
                with zipfile.ZipFile(staging.output_zip(project)) as package:
                    nested = package.read("pluginpackages/xt_ArtifactProducer/package/xt_ArtifactProducer.nupkg")
                    with zipfile.ZipFile(io.BytesIO(nested)) as artifact:
                        self.assertEqual(artifact.read("content/payload.txt"), payload.read_bytes())
                        self.assertEqual(artifact.read("lib/net462/ArtifactProducer.dll"), dll.read_bytes())
                staging.build(project, props, restore=False, target="Clean")
                # Restore solution assets removed by Microsoft's Clean, without rebuilding the producer.
                targets.msbuild(project, "-t:Restore", *staging.parameters(props), label="nobuild-restore")
                result = staging.build(project, {**props, "NoBuild": "true", "BuildProjectReferences": "false"},
                                       restore=False, success=False)
                self.assertIn("XTB3000", result)
                self.assertNotIn("validated final solution ZIP", result)

    def test_parallel_runs_of_same_projects_with_isolated_paths(self):
        for microsoft in ("2.13.1", "2.14.1"):
            with self.subTest(microsoft=microsoft):
                project, source, producer = staging.fixture("parallel")
                tree = project.parent.parent
                # Set paths before Common.props/SDK defaults, independently for every project.
                (tree / "Directory.Build.props").write_text("""<Project><PropertyGroup>
<BaseIntermediateOutputPath>$(FixtureRunRoot)/$(MSBuildProjectName)/obj/</BaseIntermediateOutputPath>
<BaseOutputPath>$(FixtureRunRoot)/$(MSBuildProjectName)/bin/</BaseOutputPath>
<PackageOutputPath>$(FixtureRunRoot)/$(MSBuildProjectName)/packages/</PackageOutputPath>
</PropertyGroup></Project>""")
                props = ET.parse(producer / "Directory.Build.props")
                props.getroot().insert(0, ET.Element("Import", Project="../Directory.Build.props"))
                props.write(producer / "Directory.Build.props")
                sources = {p: p.read_bytes() for p in source.rglob("*") if p.is_file()}
                def run(index):
                    root = tree / f"isolated run {index}"
                    properties = {"FixtureRunRoot": str(root), "FixtureMicrosoftVersion": microsoft,
                                  "XrmToolsSolutionVersion": f"9.8.7.{index}"}
                    args = staging.parameters(properties)
                    targets.msbuild(project, "-t:Restore", *args, label=f"parallel-restore-{index}")
                    # Do not share test log names/binlogs between simultaneous invocations.
                    result = targets.msbuild(project, "-t:Build", "-m:2",
                                             f"-bl:{root / 'build.binlog'}", *args,
                                             label=f"parallel-build-{index}")
                    self.assertIn("validated final solution ZIP", result)
                    archive = root / "ArtifactSolution/bin/Debug/ArtifactSolution.zip"
                    artifact = root / "ArtifactProducer/packages/Computed.ArtifactProducer.6.7.8-beta.2.nupkg"
                    with zipfile.ZipFile(archive) as package:
                        self.assertEqual(ET.fromstring(package.read("solution.xml"))
                                         .findtext("./SolutionManifest/Version"), f"9.8.7.{index}")
                        self.assertEqual(package.read("pluginpackages/xt_ArtifactProducer/package/xt_ArtifactProducer.nupkg"),
                                         artifact.read_bytes())
                    self.assertEqual(len((root / "ArtifactProducer/obj/build-count-net462.txt")
                                         .read_text().splitlines()), 1)
                with ThreadPoolExecutor(max_workers=2) as executor:
                    list(executor.map(run, (1, 2)))
                self.assertEqual(sources, {p: p.read_bytes() for p in sources})
                self.assertFalse((producer / "bin").exists())


if __name__ == "__main__":
    print(f"Execution fixtures, logs and binlogs: {targets.RUN}", flush=True)
    unittest.main(verbosity=2)
