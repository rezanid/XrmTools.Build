#!/usr/bin/env python3
"""Phase 4 package-first integration and ZIP validation tests (standard library only)."""

import importlib.util
from pathlib import Path
import os
import subprocess
import unittest
import xml.etree.ElementTree as ET
import zipfile

spec = importlib.util.spec_from_file_location("targets", Path(__file__).with_name("test-targets.py"))
targets = importlib.util.module_from_spec(spec)
spec.loader.exec_module(targets)
msbuild, query, fixture, RUN = targets.msbuild, targets.query, targets.fixture, targets.RUN
DEFAULT_ID = "Computed.ArtifactProducer"
DEFAULT_VERSION = "6.7.8-beta.2"


def parameters(properties):
    return [f"-p:{key}={str(value).replace(';', '%3B')}" for key, value in properties.items()]


def make_fixture(label):
    tree = fixture(f"artifact-{label}-{len(list(RUN.iterdir()))}")
    return tree / "ArtifactSolution/ArtifactSolution.cdsproj", tree / "ArtifactProducer"


def discover(project, properties, success=True, restore=True):
    arguments = parameters({"XrmToolsSolutionVersion": "9.8.7.6", **properties})
    if restore:
        msbuild(project, "-t:Restore", *arguments, label="artifact-restore")
    output = msbuild(project, "-t:XrmToolsDiscoverPluginPackages",
                     "-getItem:XrmToolsPluginPackageArtifact,ProjectReference,XrmToolsPluginPackageProject",
                     f"-bl:{project.parent / 'discovery.binlog'}", *arguments,
                     success=success, label="artifact-discovery")
    return query(output)["Items"] if success else output


class ArtifactIntegration(unittest.TestCase):
    def assert_artifact(self, state, expected_path, package_id=DEFAULT_ID, version=DEFAULT_VERSION,
                        source="NuGetAdapter"):
        artifacts = state["XrmToolsPluginPackageArtifact"]
        self.assertEqual(len(artifacts), 1)
        artifact = artifacts[0]
        self.assertEqual(Path(artifact["Identity"]), expected_path.resolve())
        self.assertEqual(artifact["PackageId"], package_id)
        self.assertEqual(artifact["PackageVersion"], version)
        self.assertEqual(artifact["DiscoverySource"], source)
        self.assertEqual(artifact["XrmToolsPluginPackageUniqueName"], "xt_ArtifactProducer")
        self.assertEqual(artifact["ManagedIdentityId"], "1a71c21a-cd2e-40f0-8a91-a31608d19900")
        self.assertEqual(artifact["FixtureUnknownMetadata"], "artifact metadata survives")
        self.assertEqual(len(state["ProjectReference"]), 1)
        self.assertEqual(state["ProjectReference"][0]["AdditionalProperties"],
                         "Configuration=Release;FixtureDimension=Artifact")
        with zipfile.ZipFile(expected_path) as package:
            nuspec = next(name for name in package.namelist() if name.endswith(".nuspec"))
            metadata = ET.fromstring(package.read(nuspec)).find("{*}metadata")
            self.assertEqual(metadata.findtext("{*}id"), package_id)
            self.assertEqual(metadata.findtext("{*}version"), version)
        return artifact

    def test_custom_relative_and_absolute_output_and_independent_version(self):
        for absolute in (False, True):
            with self.subTest(absolute=absolute):
                project, producer = make_fixture("custom-output")
                output = producer / "custom packages"
                properties = {"FixtureOutputPath": str(output) if absolute else "custom packages",
                              "FixturePackageVersion": "2.3.4-preview.5"}
                state = discover(project, properties)
                self.assert_artifact(state, output / f"{DEFAULT_ID}.2.3.4-preview.5.nupkg",
                                     version="2.3.4-preview.5")
                records = (producer / "obj/build-count-net462.txt").read_text().splitlines()
                self.assertEqual(records, [f"{DEFAULT_ID}|2.3.4-preview.5|{DEFAULT_VERSION}|6.7.8.0|Release|Artifact"])
                self.assertEqual(len((producer / "obj/pack-count.txt").read_text().splitlines()), 1)
                self.assertFalse(list((producer / "bin/Release").glob("*.nupkg")))

    def test_two_unchanged_dotnet_builds_and_changed_payload(self):
        for microsoft in ("2.13.1", "2.14.1"):
            for generate_on_build in (False, True):
                with self.subTest(microsoft=microsoft, generate_on_build=generate_on_build):
                    project, producer = make_fixture("repeat-build")
                    properties = {"FixtureMicrosoftVersion": microsoft,
                                  "FixtureGenerateOnBuild": str(generate_on_build).lower(),
                                  "XrmToolsSolutionVersion": "9.8.7.6",
                                  "RestoreAdditionalProjectSources": targets.FEED}
                    path = producer / f"bin/Release/{DEFAULT_ID}.{DEFAULT_VERSION}.nupkg"
                    payload = producer / "payload.txt"
                    original = payload.read_bytes()
                    compiled = producer / "bin/Release/net462/ArtifactProducer.dll"
                    compiled_before = None
                    for iteration in range(4):
                        if iteration == 2:
                            # Same-size, preserved-time content change cannot be proved by timestamps.
                            old_time = payload.stat().st_mtime_ns
                            payload.write_bytes(original.replace(b"Custom", b"Newest"))
                            os.utime(payload, ns=(old_time, old_time))
                        if iteration == 3:
                            (producer / "ChangedInput.cs").write_text(
                                'public static class ChangedInput { public const string Value = "new source"; }')
                        result = subprocess.run(
                            ["dotnet", "build", str(project), "-v:diagnostic", *parameters(properties)],
                            env=targets.ENV, cwd=project.parent, capture_output=True, text=True)
                        output = result.stdout + result.stderr
                        log = RUN / f"repeat-{microsoft}-{generate_on_build}-{iteration}-{len(list(RUN.iterdir()))}.log"
                        log.write_text(output)
                        self.assertEqual(result.returncode, 0, f"See {log}\n{output[-3000:]}")
                        self.assertIn(f"validated plugin artifact '{path}", output)
                        self.assertIn('Target "_XrmToolsInvalidateIncrementalPack:', output)
                        self.assertIn('Task "PackTask"', output)
                        self.assertNotIn("XTB3007", output)
                        with zipfile.ZipFile(path) as package:
                            self.assertEqual(package.read("content/payload.txt"), payload.read_bytes())
                            metadata = ET.fromstring(package.read(f"{DEFAULT_ID}.nuspec")).find("{*}metadata")
                            self.assertEqual(metadata.findtext("{*}id"), DEFAULT_ID)
                            self.assertEqual(metadata.findtext("{*}version"), DEFAULT_VERSION)
                            self.assertEqual(package.read("lib/net462/ArtifactProducer.dll"), compiled.read_bytes())
                        current = (compiled.stat().st_mtime_ns, targets.digest(compiled))
                        if iteration == 3:
                            self.assertNotEqual(current[1], compiled_before[1], "Changed code was not rebuilt/packed")
                        elif compiled_before is not None:
                            self.assertEqual(current, compiled_before, "Packaging rebuilt unchanged compiled code")
                        compiled_before = current
                    # A changed imported PackageId must not return the old, still-valid package.
                    props = producer / "Directory.Build.props"
                    props.write_text(props.read_text().replace("Computed.", "Changed."))
                    changed = discover(project, {"FixtureGenerateOnBuild": str(generate_on_build).lower()})
                    self.assert_artifact(changed, producer / f"bin/Release/Changed.ArtifactProducer.{DEFAULT_VERSION}.nupkg",
                                         package_id="Changed.ArtifactProducer")
                    self.assertTrue(path.exists())

    def test_automatic_pack_replaces_stale_same_identity_payload_without_timestamp_evidence(self):
        project, producer = make_fixture("stale-payload")
        path = producer / f"bin/Release/{DEFAULT_ID}.{DEFAULT_VERSION}.nupkg"
        self.assert_artifact(discover(project, {}), path)
        with zipfile.ZipFile(path) as package:
            contents = {entry.filename: package.read(entry) for entry in package.infolist()}
        contents["content/payload.txt"] = b"stale-but-identically-versioned payload"
        with zipfile.ZipFile(path, "w") as package:
            for name, content in contents.items():
                package.writestr(name, content)
        os.utime(path, (2000000000, 2000000000))
        self.assert_artifact(discover(project, {}), path)
        with zipfile.ZipFile(path) as package:
            self.assertEqual(package.read("content/payload.txt"), (producer / "payload.txt").read_bytes())

    def test_nbgv_producer_independent_version(self):
        project, producer = make_fixture("nbgv")
        (producer / "version.json").write_text('{"version":"8.9.10","publicReleaseRefSpec":[".*"]}')
        state = discover(project, {"FixtureNbgv": "true"})
        artifact = state["XrmToolsPluginPackageArtifact"][0]
        self.assertTrue(artifact["PackageVersion"].startswith("8.9.10"))
        self.assertNotEqual(artifact["PackageVersion"], "9.8.7.6")
        self.assert_artifact(state, Path(artifact["Identity"]), version=artifact["PackageVersion"])

    def test_symbol_formats_are_excluded(self):
        for symbol_format in ("symbols.nupkg", "snupkg"):
            with self.subTest(symbol_format=symbol_format):
                project, producer = make_fixture("symbols")
                state = discover(project, {"FixtureSymbols": symbol_format})
                self.assert_artifact(state, producer / f"bin/Release/{DEFAULT_ID}.{DEFAULT_VERSION}.nupkg")
                self.assertTrue(list((producer / "bin/Release").glob(f"*.{symbol_format}")))

    def test_versionless_adapter_failure_and_both_fallbacks(self):
        project, producer = make_fixture("versionless")
        path = producer / f"bin/Release/{DEFAULT_ID}.nupkg"
        properties = {"FixtureVersionless": "true"}
        output = discover(project, properties, success=None)
        state = query(output)["Items"]
        if state["XrmToolsPluginPackageArtifact"]:
            self.assert_artifact(state, path)
        else:
            self.assertIn("XTB3003", output)
            self.assertIn(f"{DEFAULT_ID}.{DEFAULT_VERSION}.nupkg", output)
        self.assertTrue(path.exists())
        # An unrelated newer package must never be selected as a fallback.
        stale = producer / "bin/Release/newest-decoy.nupkg"
        stale.write_bytes(path.read_bytes())
        os.utime(stale, (2000000000, 2000000000))
        properties["FixtureReturnedPaths"] = str(path.relative_to(producer))
        self.assert_artifact(discover(project, properties), path, source="ProducerTarget")
        properties.update(FixtureArtifactPath=os.path.relpath(path, project.parent),
                          FixtureExpectedId=DEFAULT_ID, FixtureExpectedVersion=DEFAULT_VERSION,
                          FixtureReturnedPaths="deliberately-invalid-return.nupkg")
        self.assert_artifact(discover(project, properties), path, source="ExplicitPath")

    def test_custom_nuspec_mismatch_and_explicit_identity_fallback(self):
        project, producer = make_fixture("custom-nuspec")
        properties = {"FixtureCustomNuspec": "true"}
        output = discover(project, properties, success=None)
        packages = list((producer / "bin/Release").glob("*.nupkg"))
        self.assertEqual(len(packages), 1)
        path = packages[0]
        with zipfile.ZipFile(path) as package:
            metadata = ET.fromstring(package.read("Literal.CustomProducer.nuspec")).find("{*}metadata")
            version = metadata.findtext("{*}version")
        self.assertEqual(version, "3.4.5-rc.1")
        state = query(output)["Items"]
        if state["XrmToolsPluginPackageArtifact"]:
            self.assert_artifact(state, path, "Literal.CustomProducer", version)
        else:
            self.assertIn("XTB3003", output)
        properties.update(FixtureArtifactPath=str(path), FixtureExpectedId="Literal.CustomProducer",
                          FixtureExpectedVersion=version)
        self.assert_artifact(discover(project, properties), path, "Literal.CustomProducer", version, "ExplicitPath")
        properties.pop("FixtureArtifactPath")
        properties.update(FixtureReturnedPaths=str(path), FixtureContractId="Literal.CustomProducer",
                          FixtureContractVersion=version)
        self.assert_artifact(discover(project, properties), path, "Literal.CustomProducer", version, "ProducerTarget")

    def test_custom_nuspec_substitution_with_contract(self):
        project, producer = make_fixture("substituted-nuspec")
        path = producer / "bin/Release/Substituted.ArtifactProducer.4.5.6-preview.7.nupkg"
        properties = {"FixtureCustomNuspec": "substituted", "FixtureReturnedPaths": str(path),
                      "FixtureContractId": "Substituted.ArtifactProducer", "FixtureContractVersion": "4.5.6-preview.7"}
        self.assert_artifact(discover(project, properties), path, "Substituted.ArtifactProducer",
                             "4.5.6-preview.7", "ProducerTarget")

    def test_missing_ambiguous_mismatched_and_symbol_contracts_fail(self):
        project, producer = make_fixture("invalid-contract")
        path = producer / f"bin/Release/{DEFAULT_ID}.{DEFAULT_VERSION}.nupkg"
        properties = {"FixtureReturnedPaths": str(path)}
        self.assert_artifact(discover(project, properties), path, source="ProducerTarget")
        scenarios = [
            ({"FixtureReturnedPaths": "missing.nupkg"}, "XTB3003"),
            ({"FixtureAmbiguousReturn": "true"}, "XTB3001"),
            ({"FixtureReturnedPaths": "only.symbols.nupkg"}, "XTB3001"),
            ({"FixtureContractId": "Wrong.Package"}, "XTB3006"),
            ({"FixtureContractVersion": "0.0.1"}, "XTB3006"),
            ({"FixtureDeleteArtifact": str(path)}, "XTB3003"),
        ]
        for changes, code in scenarios:
            with self.subTest(changes=changes):
                self.assertIn(code, discover(project, {**properties, **changes}, success=False))

    def test_multitarget_and_generate_package_on_build(self):
        for properties in ({"FixtureMultiTarget": "true"}, {"FixtureGenerateOnBuild": "true"}):
            with self.subTest(properties=properties):
                project, producer = make_fixture("pack-shapes")
                self.assert_artifact(discover(project, properties),
                                     producer / f"bin/Release/{DEFAULT_ID}.{DEFAULT_VERSION}.nupkg")
                for record in producer.glob("obj/build-count-*.txt"):
                    self.assertEqual(len(record.read_text().splitlines()), 1, record)

    def test_missing_pack_and_nonpackable_fail_clearly(self):
        project, producer = make_fixture("no-pack")
        msbuild(project, "-t:Restore", label="no-pack-solution-restore")
        producer_project = producer / "ArtifactProducer.csproj"
        producer_project.write_text('<Project><Target Name="Build"/></Project>')
        output = discover(project, {}, success=False, restore=False)
        self.assertIn("XTB3000", output)
        self.assertIn("Pack", output)
        project, producer = make_fixture("not-packable")
        self.assertIn("XTB3003", discover(project, {"IsPackable": "false"}, success=False))

    def test_stale_same_identity_is_not_mistaken_for_custom_nuspec_output(self):
        project, producer = make_fixture("stale-nuspec")
        path = producer / f"bin/Release/{DEFAULT_ID}.{DEFAULT_VERSION}.nupkg"
        self.assert_artifact(discover(project, {}), path)
        # Switching to a custom nuspec can leave a perfectly valid old default package.
        # Both that package and its generated nuspec match the adapter's computed names.
        # The adapter must not silently return them.
        future = 2000000000
        os.utime(path, (future, future))
        output = discover(project, {"FixtureCustomNuspec": "true"}, success=None)
        current = producer / "bin/Release/Literal.CustomProducer.3.4.5-rc.1.nupkg"
        self.assertTrue(current.exists())
        state = query(output)["Items"]
        if state["XrmToolsPluginPackageArtifact"]:
            self.assert_artifact(state, current, "Literal.CustomProducer", "3.4.5-rc.1")
        else:
            self.assertIn("XTB3007", output)

    def test_versionless_naming_rejects_stale_computed_path(self):
        project, producer = make_fixture("stale-versionless")
        path = producer / f"bin/Release/{DEFAULT_ID}.{DEFAULT_VERSION}.nupkg"
        self.assert_artifact(discover(project, {}), path)
        os.utime(path, (2000000000, 2000000000))
        failure = discover(project, {"FixtureVersionless": "true"}, success=False)
        self.assertIn("XTB3007", failure)
        self.assertTrue((producer / f"bin/Release/{DEFAULT_ID}.nupkg").exists())

    def test_explicit_path_ignores_conflicting_ambiguous_and_failing_return_target(self):
        project, producer = make_fixture("explicit-precedence")
        path = producer / f"bin/Release/{DEFAULT_ID}.{DEFAULT_VERSION}.nupkg"
        properties = {
            "FixtureArtifactPath": str(path),
            "FixtureReturnedPaths": "conflicting.nupkg",
            "FixtureContractId": "Conflicting.Identity",
            "FixtureContractVersion": "0.0.1",
            "FixtureAmbiguousReturn": "true",
            "FixtureFailReturn": "true",
        }
        for metadata in ({}, {"FixtureExpectedId": DEFAULT_ID}, {"FixtureExpectedVersion": DEFAULT_VERSION},
                         {"FixtureExpectedId": DEFAULT_ID, "FixtureExpectedVersion": DEFAULT_VERSION}):
            with self.subTest(metadata=metadata):
                self.assert_artifact(discover(project, {**properties, **metadata}), path, source="ExplicitPath")

    def test_existing_producer_import_hooks_are_chained_for_both_build_shapes(self):
        for multi in (False, True):
            with self.subTest(multi=multi):
                project, producer = make_fixture("producer-hooks")
                props = producer / "Directory.Build.props"
                document = ET.parse(props)
                group = document.getroot().find("PropertyGroup")
                for name, file in (("CustomAfterMicrosoftCommonTargets", "after-common.targets"),
                                   ("CustomAfterMicrosoftCommonCrossTargetingTargets", "after-cross.targets")):
                    ET.SubElement(group, name).text = f"$(MSBuildProjectDirectory)/{file}"
                    (producer / file).write_text(
                        f'<Project><Target Name="FixtureHook{file.replace("-", "").replace(".", "")}" BeforeTargets="Pack">'
                        f'<WriteLinesToFile File="$(BaseIntermediateOutputPath)hook-{file}.txt" Lines="preserved" Overwrite="true"/>'
                        '</Target></Project>')
                document.write(props)
                arguments = {"FixtureMultiTarget": str(multi).lower()}
                state = discover(project, arguments)
                self.assert_artifact(state, producer / f"bin/Release/{DEFAULT_ID}.{DEFAULT_VERSION}.nupkg")
                self.assertEqual((producer / f"obj/hook-after-{'cross' if multi else 'common'}.targets.txt").read_text().strip(),
                                 "preserved")

    def test_explicit_override_validation_and_generated_identity(self):
        project, producer = make_fixture("override")
        path = producer / f"bin/Release/{DEFAULT_ID}.{DEFAULT_VERSION}.nupkg"
        properties = {"FixtureArtifactPath": os.path.relpath(path, project.parent)}
        self.assert_artifact(discover(project, properties), path, source="ExplicitPath")
        for changes, code in (
            ({"FixtureArtifactPath": str(producer / "missing.nupkg")}, "XTB3003"),
            ({"FixtureArtifactPath": str(producer / "only.symbols.nupkg")}, "XTB3002"),
            ({"FixtureExpectedId": "Wrong.Package", "FixtureExpectedVersion": DEFAULT_VERSION}, "XTB3006"),
        ):
            with self.subTest(changes=changes):
                self.assertIn(code, discover(project, {**properties, **changes}, success=False))

    def test_public_returns_contract(self):
        project, producer = make_fixture("public-returns")
        path = producer / f"bin/Release/{DEFAULT_ID}.{DEFAULT_VERSION}.nupkg"
        properties = {"FixtureReturnedPaths": str(path)}
        discover(project, properties)
        caller = project.parent / "Caller.proj"
        caller.write_text(
            '<Project><Target Name="Check">'
            f'<MSBuild Projects="{project}" Targets="XrmToolsDiscoverPluginPackages" '
            f'Properties="FixtureReturnedPaths={path}">'
            '<Output TaskParameter="TargetOutputs" ItemName="Artifacts"/></MSBuild>'
            '<Error Condition="\'@(Artifacts->Count())\' != \'1\'" Text="Expected one returned artifact"/>'
            '<Error Condition="\'%(Artifacts.PackageId)\' != \'Computed.ArtifactProducer\'" Text="Lost identity"/>'
            '<Error Condition="\'%(Artifacts.ManagedIdentityId)\' == \'\'" Text="Lost reference metadata"/>'
            '</Target></Project>')
        msbuild(caller, "-t:Check", label="public-artifact-returns")

    def test_custom_pack_without_internal_adapter_requires_explicit_identity(self):
        project, producer = make_fixture("no-internal-adapter")
        msbuild(project, "-t:Restore", label="custom-pack-restore")
        source = producer / "input.nupkg"
        with zipfile.ZipFile(source, "w") as archive:
            archive.writestr("Computed.ArtifactProducer.nuspec",
                             f"<package><metadata><id>{DEFAULT_ID}</id><version>{DEFAULT_VERSION}</version></metadata></package>")
        path = producer / "custom.nupkg"
        (producer / "ArtifactProducer.csproj").write_text(
            '<Project><Target Name="Build"/><Target Name="Pack">'
            '<Copy SourceFiles="$(MSBuildProjectDirectory)/input.nupkg" '
            'DestinationFiles="$(MSBuildProjectDirectory)/custom.nupkg"/>'
            '</Target></Project>')
        self.assertIn("XTB3001", discover(project, {}, success=False, restore=False))
        properties = {"FixtureArtifactPath": str(path)}
        self.assertIn("XTB3004", discover(project, properties, success=False, restore=False))
        properties.update(FixtureExpectedId=DEFAULT_ID, FixtureExpectedVersion=DEFAULT_VERSION)
        self.assert_artifact(discover(project, properties, restore=False), path, source="ExplicitPath")

    def test_phase3_failure_then_fresh_invocation_recovers(self):
        for microsoft in ("2.13.1", "2.14.1"):
            with self.subTest(microsoft=microsoft):
                tree = fixture(f"failure-recovery-{microsoft}")
                project = tree / "MixedReferences/MixedReferences.cdsproj"
                ordinary = tree / "MixedReferences/Ordinary/Ordinary.csproj"
                document = ET.parse(ordinary)
                target = document.find('./Target[@Name="GetProjectOutputPath"]')
                ET.SubElement(target, "Error", {
                    "Condition": "'$(FixtureFailOutput)' == 'true'",
                    "Text": "Intentional reference-output failure",
                })
                document.write(ordinary)
                properties = {"FixtureMicrosoftVersion": microsoft}
                msbuild(project, "-t:Restore", *parameters(properties), label="recovery-restore")
                failure = msbuild(project, "-t:ProcessCdsProjectReferencesOutputs",
                                  "-p:FixtureFailOutput=true", *parameters(properties),
                                  success=False, label="recovery-failure")
                self.assertIn("Intentional reference-output failure", failure)
                self.assertFalse((project.parent / "bin/Debug/MixedReferences.zip").exists())
                document = ET.parse(project)
                ns = "{http://schemas.microsoft.com/developer/msbuild/2003}"
                ET.SubElement(document.getroot(), ns + "Target", {
                    "Name": "FixtureReturnReferences", "Returns": "@(ProjectReference)",
                })
                document.write(project)
                caller = project.parent / "FailureReuse.proj"
                caller.write_text(
                    '<Project><Target Name="Check">'
                    f'<MSBuild Projects="{project}" Targets="ProcessCdsProjectReferencesOutputs" '
                    'Properties="FixtureFailOutput=true" ContinueOnError="WarnAndContinue"/>'
                    f'<MSBuild Projects="{project}" Targets="FixtureReturnReferences" '
                    'Properties="FixtureFailOutput=true">'
                    '<Output TaskParameter="TargetOutputs" ItemName="Remaining"/></MSBuild>'
                    '<Message Importance="High" Text="Fixture failed-instance remaining=@(Remaining->Count())"/>'
                    '<Error Condition="\'@(Remaining->Count())\' != \'2\'" '
                    'Text="Expected transient filtered list in the failed reused instance"/>'
                    '</Target></Project>')
                reused = msbuild(caller, "-t:Check", *parameters(properties),
                                 success=False, label="reused-failed-instance")
                self.assertIn("Fixture failed-instance remaining=2", reused)
                output = msbuild(project, "-t:Build", "-getItem:ProjectReference,XrmToolsPluginPackageArtifact",
                                 *parameters(properties), label="recovery-build")
                state = query(output)["Items"]
                self.assertEqual(len(state["ProjectReference"]), 4)
                self.assertEqual(len(state["XrmToolsPluginPackageArtifact"]), 2)


class ArtifactValidation(unittest.TestCase):
    def test_actual_zip_validation_and_version_normalization(self):
        directory = RUN / "validation"
        directory.mkdir()
        assembly = targets.CACHE / "xrmtools.build" / targets.VERSION / "tools/netstandard2.0/XrmTools.Build.Tasks.dll"
        artifact = directory / "exact.nupkg"
        project = directory / "Validate.proj"
        project.write_text(
            f'<Project><UsingTask TaskName="XrmTools.Build.Tasks.ValidateArtifact" AssemblyFile="{assembly}"/>'
            '<ItemGroup><Producer Include="producer.csproj" XrmToolsPluginPackagePath="exact.nupkg" '
            'XrmToolsPluginPackageId="Test.Package" XrmToolsPluginPackageVersion="1.2.0+build"/>'
            '<Lower Include="conflicting.nupkg;ambiguous.nupkg" PackageId="Wrong" PackageVersion="0.0.1"/></ItemGroup>'
            '<Target Name="Check"><XrmTools.Build.Tasks.ValidateArtifact Producer="@(Producer)" '
            'ContractOutputs="@(Lower)" AdapterOutputs="@(Evidence)" SolutionDirectory="$(MSBuildProjectDirectory)"/></Target></Project>')
        cases = [
            ('<package><metadata><id>test.package</id><version>1.2</version></metadata></package>', None),
            ('<package><metadata><id>Other</id><version>1.2.0</version></metadata></package>', "XTB3006"),
            ('<package><metadata><id>Test.Package</id><version>1.2.0-beta</version></metadata></package>', "XTB3006"),
            ('<package><metadata><id>Test.Package</id><version>1.2.0</version><packageTypes>'
             '<packageType name="SymbolsPackage"/></packageTypes></metadata></package>', "XTB3005"),
            ('<package><metadata/><metadata/></package>', "XTB3005"),
            ('<package><metadata><id>Test.Package</id><id>Other</id><version>1.2</version></metadata></package>', "XTB3005"),
            ('<package><metadata><id>Test.Package</id><version>not-a-version</version></metadata></package>', "XTB3006"),
            ('<!DOCTYPE package [<!ENTITY x SYSTEM "file:///missing">]><package>&x;</package>', "XTB3005"),
        ]
        for xml, code in cases:
            with self.subTest(xml=xml):
                with zipfile.ZipFile(artifact, "w") as archive:
                    archive.writestr("Test.Package.nuspec", xml)
                output = msbuild(project, "-t:Check", success=code is None, label="validate-zip")
                if code:
                    self.assertIn(code, output)
                    self.assertNotIn("MSB4018", output)
        for manifests in ([], ["one.nuspec", "two.nuspec"]):
            with self.subTest(manifests=manifests):
                with zipfile.ZipFile(artifact, "w") as archive:
                    for name in manifests:
                        archive.writestr(name, "<package/>")
                self.assertIn("XTB3005", msbuild(project, "-t:Check", success=False, label="nuspec-count"))
        artifact.write_bytes(b"not a zip")
        self.assertIn("XTB3005", msbuild(project, "-t:Check", success=False, label="corrupt-zip"))
        with zipfile.ZipFile(artifact, "w") as archive:
            archive.writestr("Test.Package.nuspec",
                             "<package><metadata><id>Test.Package</id><version>1.2.0</version></metadata></package>")
        project.write_text(project.read_text().replace('XrmToolsPluginPackageVersion="1.2.0+build"',
                                                      'XrmToolsPluginPackageVersion=""'))
        output = msbuild(project, "-t:Check", success=False, label="explicit-missing-metadata")
        self.assertIn("XTB3004", output)
        self.assertNotIn("XTB3001", output)
        document = ET.parse(project)
        group = ET.SubElement(document.getroot(), "ItemGroup")
        for path in ("unrelated-one.nupkg", "unrelated-two.nupkg"):
            ET.SubElement(group, "Evidence", {
                "Include": path, "XrmToolsEvaluatedPackageId": "Test.Package",
                "XrmToolsEvaluatedPackageVersion": "1.2.0",
            })
        document.write(project)
        msbuild(project, "-t:Check", label="explicit-ambiguous-paths-unambiguous-identity")
        group[-1].set("XrmToolsEvaluatedPackageVersion", "9.9.9")
        document.write(project)
        output = msbuild(project, "-t:Check", success=False, label="explicit-ambiguous-identity")
        self.assertIn("XTB3004", output)


if __name__ == "__main__":
    print(f"Artifact fixtures, logs and binlogs: {RUN}", flush=True)
    unittest.main(verbosity=2)
