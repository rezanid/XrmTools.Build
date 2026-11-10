#!/usr/bin/env python3
"""Phase 5 tests against the packed extension and Microsoft's real ZIP packager."""

import importlib.util
import io
import os
from pathlib import Path
import shutil
import sys
import unittest
import xml.etree.ElementTree as ET
import zipfile

spec = importlib.util.spec_from_file_location("targets", Path(__file__).with_name("test-targets.py"))
targets = importlib.util.module_from_spec(spec)
spec.loader.exec_module(targets)
RUN = targets.RUN
NS = "{http://schemas.microsoft.com/developer/msbuild/2003}"
IDENTITY = "1a71c21a-cd2e-40f0-8a91-a31608d19900"


def parameters(properties):
    return [f"-p:{key}={str(value).replace(';', '%3B')}" for key, value in properties.items()]


def fixture(label, producers=True):
    tree = targets.fixture(f"staging-{label}-{len(list(RUN.iterdir()))}")
    project = tree / ("ArtifactSolution/ArtifactSolution.cdsproj" if producers else
                      "MinimalSolution/MinimalSolution.cdsproj")
    return project, tree / "MinimalSolution/src", tree / "ArtifactProducer"


def build(project, properties=None, success=True, restore=True, target="Build"):
    args = parameters({"XrmToolsSolutionVersion": "9.8.7.6", **(properties or {})})
    if restore:
        targets.msbuild(project, "-t:Restore", *args, label="staging-restore")
    return targets.msbuild(project, f"-t:{target}", "-v:normal",
                           f"-bl:{project.parent / 'staging.binlog'}", *args,
                           success=success, label="staging-build")


def edit_project(project, edit):
    document = ET.parse(project)
    edit(document.getroot())
    document.write(project, encoding="utf-8", xml_declaration=True)


def source_package(source, name="old_SourceOnly", version="2.3.4", namespace="", encoding="utf-8"):
    directory = source / "pluginpackages" / name
    (directory / "package").mkdir(parents=True, exist_ok=True)
    ns = f' xmlns="{namespace}"' if namespace else ""
    xml = f'''<?xml version="1.0" encoding="{encoding}"?>
<pluginpackage uniquename="{name}"{ns}>
  <!-- retain this comment -->
  <exportkeyversion>3</exportkeyversion><iscustomizable>0</iscustomizable>
  <managedidentityid extra="retain"><managedidentityid>{IDENTITY}</managedidentityid><future>retain</future></managedidentityid>
  <name>Existing display name</name>
  <package mimetype="application/octet-stream">existing.nupkg</package>
  <statecode>1</statecode><statuscode>2</statuscode><version>1.0.0.0</version>
  <future flag="retain"><nested>opaque metadata</nested></future>
</pluginpackage>'''
    (directory / "pluginpackage.xml").write_bytes(xml.encode(encoding))
    with zipfile.ZipFile(directory / "package/existing.nupkg", "w") as package:
        package.writestr("SourceOnly.nuspec", f"<package><metadata><id>SourceOnly</id><version>{version}</version></metadata></package>")
        package.writestr("content/payload.txt", b"source-only package bytes")
    return directory


def output_zip(project, configuration="Debug"):
    return project.parent / f"bin/{configuration}/{project.stem}.zip"


def xml(package, name):
    return ET.fromstring(package.read(name))


class StagingIntegration(unittest.TestCase):
    def test_direct_tasks_reject_malformed_solution_shapes_with_diagnostics(self):
        directory = RUN / "direct tasks"
        (directory / "Other").mkdir(parents=True)
        assembly = targets.CACHE / "xrmtools.build" / targets.VERSION / "tools/netstandard2.0/XrmTools.Build.Tasks.dll"
        project = directory / "Check.proj"
        root = ET.Element("Project")
        for task in ("StagePluginPackages", "ValidateSolutionPackage"):
            ET.SubElement(root, "UsingTask", TaskName=f"XrmTools.Build.Tasks.{task}", AssemblyFile=str(assembly))
        target = ET.SubElement(root, "Target", Name="Stage")
        ET.SubElement(target, "XrmTools.Build.Tasks.StagePluginPackages", StageDirectory=str(directory),
                      SolutionVersion="9.8.7.6")
        target = ET.SubElement(root, "Target", Name="Validate")
        ET.SubElement(target, "XrmTools.Build.Tasks.ValidateSolutionPackage", ZipPath=str(directory / "solution.zip"),
                      SolutionVersion="9.8.7.6", SolutionManifest="<SolutionManifest/>")
        ET.ElementTree(root).write(project)
        for content in ("", "<wrong/>", "<ImportExportXml/>",
                        "<ImportExportXml><SolutionManifest/><SolutionManifest/></ImportExportXml>"):
            with self.subTest(content=content):
                (directory / "Other/Solution.xml").write_text(content)
                with zipfile.ZipFile(directory / "solution.zip", "w") as archive:
                    archive.writestr("solution.xml", content)
                for target, code in (("Stage", "XTB4001"), ("Validate", "XTB4002")):
                    result = targets.msbuild(project, f"-t:{target}", success=False, label="invalid-solution-shape")
                    self.assertIn(code, result)
                    self.assertNotIn("MSB4018", result)

    def test_source_only_packages_zero_producers_and_encoding_metadata_preservation(self):
        for microsoft, namespace, encoding in (("2.13.1", "", "utf-8"), ("2.14.1", "urn:fixture", "utf-16")):
            with self.subTest(microsoft=microsoft):
                project, source, _ = fixture("source-only", False)
                directory = source_package(source, namespace=namespace, encoding=encoding)
                before = {path: path.read_bytes() for path in source.rglob("*") if path.is_file()}
                build(project, {"FixtureMicrosoftVersion": microsoft})
                base = "pluginpackages/old_SourceOnly/"
                with zipfile.ZipFile(output_zip(project)) as package:
                    data = package.read(base + "pluginpackage.xml")
                    document = ET.fromstring(data)
                    self.assertEqual(document.findtext("{*}version"), "9.8.7.6")
                    self.assertEqual(document.attrib["uniquename"], "old_SourceOnly")
                    self.assertEqual(document.findtext("{*}name"), "Existing display name")
                    self.assertEqual(document.findtext("{*}managedidentityid/{*}managedidentityid"), IDENTITY)
                    self.assertEqual(document.find("{*}managedidentityid").attrib["extra"], "retain")
                    self.assertEqual(document.findtext("{*}future/{*}nested"), "opaque metadata")
                    self.assertEqual(document.findtext("{*}iscustomizable"), "0")
                    self.assertEqual(document.findtext("{*}exportkeyversion"), "3")
                    self.assertEqual(document.findtext("{*}statecode"), "1")
                    self.assertEqual(document.findtext("{*}statuscode"), "2")
                    self.assertEqual(document.find("{*}package").attrib["mimetype"], "application/octet-stream")
                    self.assertIn("retain this comment", data.decode(encoding))
                    self.assertIn(f'encoding="{encoding}"', data.decode(encoding))
                    if namespace:
                        self.assertEqual(document.tag, f"{{{namespace}}}pluginpackage")
                    self.assertEqual(package.read(base + "package/existing.nupkg"),
                                     (directory / "package/existing.nupkg").read_bytes())
                self.assertEqual(before, {path: path.read_bytes() for path in before})

    def test_existing_producer_metadata_preserved_and_explicit_identity_precedence(self):
        for explicit in (False, True):
            project, source, _ = fixture("existing")
            directory = source_package(source, name="xt_ArtifactProducer")
            old_identity = "98cbd2b1-7380-4077-a246-3950fb1a5d08"
            path = directory / "pluginpackage.xml"
            path.write_text(path.read_text().replace(IDENTITY, old_identity))
            if not explicit:
                edit_project(project, lambda root: root.find(f".//{NS}ProjectReference").remove(
                    root.find(f".//{NS}ManagedIdentityId")))
            before = path.read_bytes()
            build(project)
            with zipfile.ZipFile(output_zip(project)) as package:
                document = xml(package, "pluginpackages/xt_ArtifactProducer/pluginpackage.xml")
                self.assertEqual(document.findtext("managedidentityid/managedidentityid"),
                                 IDENTITY if explicit else old_identity)
                self.assertEqual(document.findtext("package"), "existing.nupkg")
                self.assertEqual(document.findtext("name"), "Existing display name")
                self.assertEqual(document.findtext("future/nested"), "opaque metadata")
            self.assertEqual(path.read_bytes(), before)

    def test_multiple_independent_producer_versions_alongside_pcf(self):
        tree = targets.fixture("staging-independent-mixed")
        project = tree / "MixedReferences/MixedReferences.cdsproj"
        producer = tree / "MixedReferences/ProducerB/ProducerB.csproj"
        def set_version(root):
            ET.SubElement(ET.SubElement(root, "PropertyGroup"), "PackageVersion").text = "8.9.10-rc.2"
        edit_project(producer, set_version)
        build(project)
        with zipfile.ZipFile(output_zip(project)) as package:
            for name, version in (("ProducerA", "5.6.7-beta"), ("ProducerB", "8.9.10-rc.2")):
                base = f"pluginpackages/xt_{name}/"
                self.assertEqual(xml(package, base + "pluginpackage.xml").findtext("version"), "9.8.7.6")
                with zipfile.ZipFile(io.BytesIO(package.read(base + f"package/xt_{name}.nupkg"))) as nested:
                    self.assertEqual(xml(nested, f"Computed.{name}.nuspec").findtext("{*}metadata/{*}version"), version)
            self.assertIn("Controls/xt_XrmToolsFixture.Control/bundle.js", package.namelist())

    def test_matching_source_only_metadata_is_not_rewritten(self):
        project, source, _ = fixture("no-op", False)
        directory = source_package(source)
        self.replace(directory, "1.0.0.0", "9.8.7.6")
        original = (directory / "pluginpackage.xml").read_bytes()
        build(project, target="XrmToolsStagePluginPackages")
        staged = project.parent / "obj/Debug/Metadata/pluginpackages/old_SourceOnly/pluginpackage.xml"
        self.assertEqual(staged.read_bytes(), original)
        self.assertEqual(staged.stat().st_mtime_ns, (directory / "pluginpackage.xml").stat().st_mtime_ns)

    def test_derived_name_prefix_independent_versions_and_configuration_transitions(self):
        project, source, producer = fixture("transitions")
        edit_project(project, lambda root: root.find(f".//{NS}ProjectReference").remove(
            root.find(f".//{NS}XrmToolsPluginPackageUniqueName")))
        manifest = source / "Other/Solution.xml"
        manifest.write_text(manifest.read_text().replace("<Managed>0</Managed>", "<Managed>2</Managed>"))
        before = {p: p.read_bytes() for p in source.rglob("*.xml")}
        output = producer / "user packages"
        for configuration, version, solution_version in (
                ("Debug", "2.3.4-beta", "4.5.6.7"), ("Release", "7.8.9", "8.9.10.11"),
                ("Debug", "2.3.5", "4.5.6.8"), ("Debug", "2.3.5", "4.5.6.8")):
            result = build(project, {"Configuration": configuration, "FixturePackageVersion": version,
                                     "FixtureOutputPath": str(output), "XrmToolsSolutionVersion": solution_version})
            self.assertIn("validated final solution ZIP", result)
            self.assertIn("plugin staging:", result)
            self.assertIn("final ZIP validation:", result)
            base = "pluginpackages/xt_Computed.ArtifactProducer/"
            artifact = output / f"Computed.ArtifactProducer.{version}.nupkg"
            with zipfile.ZipFile(output_zip(project, configuration)) as package:
                self.assertEqual(package.read(base + "package/xt_Computed.ArtifactProducer.nupkg"),
                                 artifact.read_bytes())
                self.assertEqual(xml(package, base + "pluginpackage.xml").findtext("version"), solution_version)
                self.assertEqual(xml(package, "solution.xml").findtext("./SolutionManifest/Version"), solution_version)
                with zipfile.ZipFile(io.BytesIO(package.read(base + "package/xt_Computed.ArtifactProducer.nupkg"))) as nested:
                    self.assertEqual(xml(nested, "Computed.ArtifactProducer.nuspec").findtext("{*}metadata/{*}version"), version)
        self.assertEqual(before, {p: p.read_bytes() for p in before})
        self.assertEqual(len(list(output.glob("*.nupkg"))), 3, "User package directory was changed/cleaned")
        # A package ID already prefixed with the publisher must not acquire a second prefix.
        props = producer / "Directory.Build.props"
        props.write_text(props.read_text().replace("Computed.", "xt_"))
        build(project)
        with zipfile.ZipFile(output_zip(project)) as package:
            self.assertIn("pluginpackages/xt_ArtifactProducer/pluginpackage.xml", package.namelist())

    def test_malformed_xml_missing_files_duplicates_and_invalid_metadata_fail(self):
        mutations = [
            ("malformed", lambda d: (d / "pluginpackage.xml").write_text("<pluginpackage>")),
            ("missing-xml", lambda d: (d / "pluginpackage.xml").unlink()),
            ("missing-package", lambda d: (d / "package/existing.nupkg").unlink()),
            ("extra-package", lambda d: shutil.copyfile(d / "package/existing.nupkg", d / "package/extra.nupkg")),
            ("symbols", lambda d: shutil.copyfile(d / "package/existing.nupkg", d / "package/extra.snupkg")),
            ("wrong-name", lambda d: self.replace(d, 'uniquename="old_SourceOnly"', 'uniquename="old_Wrong"')),
            ("empty-package", lambda d: self.replace(d, "existing.nupkg", "")),
            ("unsafe-path", lambda d: self.replace(d, "existing.nupkg", "../outside.nupkg")),
            ("duplicate-version", lambda d: self.replace(d, "<version>", "<version>0.0.0.0</version><version>")),
            ("missing-version", lambda d: self.replace(d, "<version>1.0.0.0</version>", "")),
            ("duplicate-package", lambda d: self.replace(d, "<statecode>", "<package>second.nupkg</package><statecode>")),
            ("bad-identity", lambda d: self.replace(d, IDENTITY, "not-a-guid")),
            ("duplicate-identity", lambda d: self.replace(d, "<name>", f"<managedidentityid><managedidentityid>{IDENTITY}</managedidentityid></managedidentityid><name>")),
            ("invalid-nupkg", lambda d: (d / "package/existing.nupkg").write_bytes(b"not a zip")),
            ("dtd", lambda d: self.replace(d, "<pluginpackage ", '<!DOCTYPE pluginpackage [<!ENTITY x "x">]><pluginpackage ')),
        ]
        for label, mutate in mutations:
            with self.subTest(label=label):
                project, source, _ = fixture(label, False)
                mutate(source_package(source))
                result = build(project, success=False)
                self.assertIn("XTB4001", result)
                self.assertNotIn("validated final solution ZIP", result)
                self.assertFalse(output_zip(project).exists())

    @staticmethod
    def replace(directory, old, new):
        path = directory / "pluginpackage.xml"
        path.write_text(path.read_text().replace(old, new))

    def test_duplicate_derived_and_source_case_collisions_fail(self):
        project, source, producer = fixture("duplicate-derived")
        second = producer.parent / "Second"
        shutil.copytree(producer, second)
        (second / "ArtifactProducer.csproj").rename(second / "Second.csproj")
        # Give two separately classified producers the same evaluated package ID.
        for directory in (producer, second):
            props = directory / "Directory.Build.props"
            props.write_text(props.read_text().replace("Computed.$(MSBuildProjectName)", "Same.Package"))
        def duplicate(root):
            group = root.find(f"{NS}ItemGroup")
            first = root.find(f".//{NS}ProjectReference")
            first.remove(first.find(f"{NS}XrmToolsPluginPackageUniqueName"))
            second_ref = ET.fromstring(ET.tostring(first))
            second_ref.set("Include", "../Second/Second.csproj")
            group.append(second_ref)
        edit_project(project, duplicate)
        self.assertIn("Duplicate plugin package unique name", build(project, success=False))
        project, source, _ = fixture("case", False)
        source_package(source, "old_One")
        # Case-only file names cannot be represented on default macOS/Windows filesystems.
        directory = source / "pluginpackages/old_One"
        self.replace(directory, 'uniquename="old_One"', 'uniquename="old_one"')
        self.assertIn("XTB4001", build(project, success=False))

    def test_invalid_reference_names_prefixes_and_managed_id_fail(self):
        for metadata, value in (("XrmToolsPluginPackageUniqueName", "../escape"),
                                ("XrmToolsPluginPackageUniqueName", "unprefixed"),
                                ("ManagedIdentityId", "bad-guid"),
                                ("ManagedIdentityId", "00000000-0000-0000-0000-000000000000")):
            with self.subTest(metadata=metadata, value=value):
                project, _, _ = fixture("invalid-reference")
                edit_project(project, lambda root: setattr(root.find(f".//{NS}{metadata}"), "text", value))
                self.assertIn("XTB4001", build(project, success=False))
        project, source, _ = fixture("missing-prefix")
        edit_project(project, lambda root: root.find(f".//{NS}ProjectReference").remove(
            root.find(f".//{NS}XrmToolsPluginPackageUniqueName")))
        manifest = source / "Other/Solution.xml"
        manifest.write_text(manifest.read_text().replace("<CustomizationPrefix>xt</CustomizationPrefix>", "<CustomizationPrefix />"))
        self.assertIn("CustomizationPrefix", build(project, success=False))

    def test_failed_build_preserves_old_zip_but_never_reports_validation_and_recovers(self):
        project, source, producer = fixture("failure")
        build(project)
        archive = output_zip(project)
        old = archive.read_bytes()
        (producer / "Bad.cs").write_text("deliberate compiler error")
        result = build(project, success=False)
        self.assertNotIn("validated final solution ZIP", result)
        self.assertEqual(archive.read_bytes(), old)
        (producer / "Bad.cs").unlink()
        artifact = producer / "bin/Release/Computed.ArtifactProducer.6.7.8-beta.2.nupkg"
        result = build(project, {"FixtureDeleteArtifact": str(artifact)}, success=False)
        self.assertIn("XTB3003", result)
        self.assertNotIn("validated final solution ZIP", result)
        self.assertEqual(archive.read_bytes(), old)
        directory = source_package(source)
        self.replace(directory, "<version>", "<version>bad</version><version>")
        result = build(project, success=False)
        self.assertIn("XTB4001", result)
        self.assertEqual(archive.read_bytes(), old)
        # Microsoft's overlay copy does not remove failed staging leftovers. Our narrow
        # pre-copy reset must remove the source-only package deleted between invocations.
        shutil.rmtree(directory)
        result = build(project)
        self.assertIn("validated final solution ZIP", result)
        with zipfile.ZipFile(archive) as package:
            self.assertFalse(any("old_SourceOnly" in name for name in package.namelist()))

    def test_staging_ancestry_and_symlink_collisions_fail_before_source_writes(self):
        project, source, _ = fixture("ancestry", False)
        before = {p: p.read_bytes() for p in source.rglob("*") if p.is_file()}
        for stage in (source, source.parent, source / "nested", project.parent / "not-intermediate"):
            result = build(project, {"SolutionPackagerMetadataWorkingDirectory": str(stage)}, success=False)
            self.assertTrue("XTB4000" in result or "XTB1000" in result)
        self.assertEqual(before, {p: p.read_bytes() for p in before})
        link = project.parent / "obj/linked-source"
        link.parent.mkdir(parents=True, exist_ok=True)
        try:
            link.symlink_to(source, target_is_directory=True)
        except OSError as error:
            # Windows runners without symlink privileges still exercise directory ancestry.
            if os.name != "nt":
                raise
            print(f"Symlink creation unavailable: {error}")
            return
        result = build(project, {"SolutionPackagerMetadataWorkingDirectory": str(link)}, success=False)
        self.assertIn("XTB4000", result)
        self.assertEqual(before, {p: p.read_bytes() for p in before})
        link.unlink()
        source_link = source / "linked"
        source_link.symlink_to(project.parent, target_is_directory=True)
        self.assertIn("XTB4000", build(project, success=False))
        source_link.unlink()

    def test_final_zip_validator_rejects_tampered_missing_extra_and_duplicate_entries(self):
        for mode in ("package", "xml", "missing", "extra", "duplicate", "solution", "publisher"):
            with self.subTest(mode=mode):
                project, _, _ = fixture(f"tamper-{mode}")
                script = project.parent / "tamper.py"
                script.write_text('''import sys, zipfile
path, mode = sys.argv[1:]
with zipfile.ZipFile(path) as z:
    contents = {i.filename: z.read(i) for i in z.infolist()}
package = next(n for n in contents if n.endswith(".nupkg"))
xml = next(n for n in contents if n.endswith("pluginpackage.xml"))
if mode == "package": contents[package] = b"wrong bytes"
if mode == "xml": contents[xml] = contents[xml].replace(b"9.8.7.6", b"9.8.7.5")
if mode == "missing": del contents[package]
if mode == "extra": contents["pluginpackages/extra/package/extra.nupkg"] = b"extra"
if mode == "solution": contents["solution.xml"] = contents["solution.xml"].replace(b"9.8.7.6", b"9.8.7.5")
if mode == "publisher": contents["solution.xml"] = contents["solution.xml"].replace(b">xt<", b">bad<")
with zipfile.ZipFile(path, "w") as z:
    for name, data in contents.items(): z.writestr(name, data)
    if mode == "duplicate": z.writestr(package, contents[package])
''')
                def inject(root):
                    target = ET.SubElement(root, NS + "Target", Name="TamperFinalZip",
                                           BeforeTargets="XrmToolsValidatePackage")
                    ET.SubElement(target, NS + "Exec", Command=f'"{sys.executable}" "{script}" "$(SolutionPackageZipFilePath)" "{mode}"')
                edit_project(project, inject)
                result = build(project, success=False)
                self.assertIn("XTB4002", result)
                self.assertNotIn("validated final solution ZIP", result)

    def test_managed_both_and_custom_zip_output_paths(self):
        for microsoft in ("2.13.1", "2.14.1"):
            for package_type in ("Unmanaged", "Managed", "Both"):
                with self.subTest(microsoft=microsoft, package_type=package_type):
                    project, source, _ = fixture("package-types", False)
                    source_package(source)
                    manifest = source / "Other/Solution.xml"
                    # Managed=2 is Microsoft's combined-source marker, established by
                    # extracting a genuine unmanaged+managed pair with SolutionPackagerTask.
                    managed = {"Unmanaged": "0", "Managed": "1", "Both": "2"}[package_type]
                    manifest.write_text(manifest.read_text().replace("<Managed>0</Managed>", f"<Managed>{managed}</Managed>"))
                    path = project.parent / "custom output/custom solution.zip"
                    build(project, {"FixtureMicrosoftVersion": microsoft, "SolutionPackageType": package_type,
                                    "SolutionPackageZipFilePath": str(path)})
                    paths = [path, path.with_stem(path.stem + "_managed")] if package_type == "Both" else [path]
                    for archive in paths:
                        with zipfile.ZipFile(archive) as package:
                            self.assertEqual(xml(package, "pluginpackages/old_SourceOnly/pluginpackage.xml").findtext("version"), "9.8.7.6")
                            self.assertEqual(xml(package, "solution.xml").findtext("./SolutionManifest/Version"), "9.8.7.6")


if __name__ == "__main__":
    print(f"Staging fixtures, logs and binlogs: {RUN}", flush=True)
    unittest.main(verbosity=2)
