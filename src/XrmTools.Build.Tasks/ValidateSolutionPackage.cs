using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Xml;
using System.Xml.Linq;
using Microsoft.Build.Framework;
using Microsoft.Build.Utilities;

namespace XrmTools.Build.Tasks
{
    public sealed class ValidateSolutionPackage : Task
    {
        [Required] public string ZipPath { get; set; } = "";
        [Required] public string SolutionVersion { get; set; } = "";
        [Required] public string SolutionManifest { get; set; } = "";
        public string PackageType { get; set; } = "Unmanaged";
        public ITaskItem[] Packages { get; set; } = Array.Empty<ITaskItem>();

        public override bool Execute()
        {
            var timer = Stopwatch.StartNew();
            var path = ZipPath;
            try
            {
                Validate(ZipPath, string.Equals(PackageType, "Managed", StringComparison.OrdinalIgnoreCase) ? "1" : "0");
                if (string.Equals(PackageType, "Both", StringComparison.OrdinalIgnoreCase))
                {
                    // Microsoft's task exposes no output items. This is its documented Both naming contract.
                    path = Path.Combine(Path.GetDirectoryName(ZipPath) ?? "",
                        Path.GetFileNameWithoutExtension(ZipPath) + "_managed" + Path.GetExtension(ZipPath));
                    Validate(path, "1");
                }
                Log.LogMessage(MessageImportance.High, $"XrmTools.Build validated final solution ZIP '{ZipPath}' ({Packages.Length} plugin packages, {PackageType}).");
                Log.LogMessage(MessageImportance.Normal, $"XrmTools.Build final ZIP validation: {timer.ElapsedMilliseconds} ms.");
                return true;
            }
            catch (Exception exception) when (exception is IOException || exception is InvalidDataException || exception is XmlException ||
                exception is ArgumentException || exception is UnauthorizedAccessException)
            {
                Log.LogError(null, "XTB4002", null, path, 0, 0, 0, 0,
                    $"XrmTools.Build: final solution ZIP validation failed for '{path}' " +
                    $"(SolutionPackageType='{PackageType}', expected version='{SolutionVersion}'): {exception.Message} " +
                    "Rebuild successfully with isolated output paths; check custom packaging hooks/mappings for changed or omitted entries. An existing ZIP is not proof of success.");
                return false;
            }
        }

        private void Validate(string path, string managed)
        {
            using (var archive = ZipFile.OpenRead(path))
            {
                var entries = new Dictionary<string, ZipArchiveEntry>(StringComparer.OrdinalIgnoreCase);
                foreach (var entry in archive.Entries)
                {
                    if (entries.ContainsKey(entry.FullName))
                        throw new InvalidDataException($"Duplicate ZIP entry '{entry.FullName}'.");
                    entries.Add(entry.FullName, entry);
                }
                var solution = Read(entries, "solution.xml");
                var manifest = PluginPackageFiles.Manifest(solution);
                if (PluginPackageFiles.One(manifest, "Version").Value != SolutionVersion)
                    throw new InvalidDataException($"Final solution.xml version '{PluginPackageFiles.One(manifest, "Version").Value}' differs from XrmToolsResolvedSolutionVersion='{SolutionVersion}'.");
                var expectedManifest = XElement.Parse(SolutionManifest);
                var managedNode = PluginPackageFiles.One(expectedManifest, "Managed");
                if (managedNode.Value == "2") managedNode.Value = managed;
                var actualManifest = XElement.Parse(manifest.ToString());
                if (PluginPackageFiles.One(actualManifest, "Managed").Value != managed)
                    throw new InvalidDataException($"Final ZIP '{path}' has the wrong managed/unmanaged type.");
                if (!XNode.DeepEquals(expectedManifest, actualManifest))
                    throw new InvalidDataException("Final solution manifest metadata differs from the staged manifest.");
                var expected = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
                foreach (var package in Packages)
                {
                    CheckHash(entries, package.ItemSpec, package.GetMetadata("XmlHash"));
                    CheckHash(entries, package.GetMetadata("PackageEntry"), package.GetMetadata("PackageHash"));
                    var xml = Read(entries, package.ItemSpec);
                    var name = package.ItemSpec.Split('/')[1];
                    var root = PluginPackageFiles.Metadata(xml, name);
                    if (PluginPackageFiles.One(root, "version").Value != SolutionVersion)
                        throw new InvalidDataException($"Final plugin package '{name}' version differs from the solution.");
                    expected.Add(package.ItemSpec);
                    expected.Add(package.GetMetadata("PackageEntry"));
                }
                var actual = entries.Keys.Where(name =>
                    string.Equals(Path.GetFileName(name.Replace('\\', '/')), "pluginpackage.xml", StringComparison.OrdinalIgnoreCase) ||
                    (name.Replace('\\', '/').StartsWith("pluginpackages/", StringComparison.OrdinalIgnoreCase) &&
                     (name.EndsWith(".nupkg", StringComparison.OrdinalIgnoreCase) ||
                      name.EndsWith(".snupkg", StringComparison.OrdinalIgnoreCase))));
                if (!expected.SetEquals(actual))
                    throw new InvalidDataException("Final ZIP contains missing or unexpected plugin metadata/packages. " +
                        $"Missing: [{string.Join(", ", expected.Except(actual, StringComparer.OrdinalIgnoreCase))}]; " +
                        $"unexpected: [{string.Join(", ", actual.Except(expected, StringComparer.OrdinalIgnoreCase))}].");
            }
        }

        private static XDocument Read(Dictionary<string, ZipArchiveEntry> entries, string path)
        {
            if (!entries.TryGetValue(path, out var entry)) throw new InvalidDataException($"Missing ZIP entry '{path}'.");
            using (var stream = entry.Open()) return PluginPackageFiles.ReadXml(stream);
        }

        private static void CheckHash(Dictionary<string, ZipArchiveEntry> entries, string path, string expected)
        {
            if (!entries.TryGetValue(path, out var entry)) throw new InvalidDataException($"Missing ZIP entry '{path}'.");
            using (var stream = entry.Open())
                if (PluginPackageFiles.Hash(stream) != expected)
                    throw new InvalidDataException($"Final ZIP entry '{path}' differs from validated staged bytes.");
        }
    }
}
