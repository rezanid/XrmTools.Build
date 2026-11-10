using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Xml;
using System.Xml.Linq;
using Microsoft.Build.Framework;
using Microsoft.Build.Utilities;
using NuGet.Versioning;

namespace XrmTools.Build.Tasks
{
    public sealed class StagePluginPackages : Task
    {
        [Required] public string StageDirectory { get; set; } = "";
        [Required] public string SolutionVersion { get; set; } = "";
        public ITaskItem[] Artifacts { get; set; } = Array.Empty<ITaskItem>();
        [Output] public ITaskItem[] Packages { get; set; } = Array.Empty<ITaskItem>();
        [Output] public string SolutionManifest { get; set; } = "";

        public override bool Execute()
        {
            var timer = Stopwatch.StartNew();
            var inputPath = StageDirectory;
            try
            {
                PluginPackageFiles.NoTreeLinks(StageDirectory);
                inputPath = Path.Combine(StageDirectory, "Other", "Solution.xml");
                var solution = PluginPackageFiles.ReadXml(inputPath);
                var manifest = PluginPackageFiles.Manifest(solution);
                SolutionManifest = manifest.ToString(SaveOptions.DisableFormatting);
                var prefix = PluginPackageFiles.One(PluginPackageFiles.One(manifest, "Publisher"), "CustomizationPrefix").Value;
                var directory = Path.Combine(StageDirectory, "pluginpackages");
                var names = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
                foreach (var artifact in Artifacts)
                {
                    inputPath = artifact.ItemSpec;
                    var name = artifact.GetMetadata("XrmToolsPluginPackageUniqueName");
                    if (name.Length == 0)
                    {
                        if (!System.Text.RegularExpressions.Regex.IsMatch(prefix, @"\A[A-Za-z][A-Za-z0-9]*\z"))
                            throw new InvalidDataException($"Publisher/CustomizationPrefix='{prefix}' cannot derive a plugin package unique name for '{artifact.ItemSpec}'. Supply a valid publisher prefix or explicit XrmToolsPluginPackageUniqueName.");
                        var id = artifact.GetMetadata("PackageId");
                        name = id.StartsWith(prefix + "_", StringComparison.OrdinalIgnoreCase) ? id : prefix + "_" + id;
                    }
                    PluginPackageFiles.UniqueName(name);
                    if (!names.Add(name)) throw new InvalidDataException($"Duplicate plugin package unique name '{name}' from validated artifacts.");
                    var packageDirectory = Path.Combine(directory, name);
                    var xmlPath = Path.Combine(packageDirectory, "pluginpackage.xml");
                    inputPath = xmlPath;
                    var document = File.Exists(xmlPath) ? PluginPackageFiles.ReadXml(xmlPath) : Create(name);
                    var original = File.Exists(xmlPath) ? document.ToString(SaveOptions.DisableFormatting) : null;
                    var root = PluginPackageFiles.Metadata(document, name);
                    var identity = artifact.GetMetadata("ManagedIdentityId");
                    if (identity.Length > 0)
                    {
                        PluginPackageFiles.Identity(identity);
                        var outer = root.Element(root.Name.Namespace + "managedidentityid");
                        if (outer == null)
                        {
                            outer = new XElement(root.Name.Namespace + "managedidentityid",
                                new XElement(root.Name.Namespace + "managedidentityid", identity));
                            root.Add(outer);
                        }
                        else PluginPackageFiles.One(outer, "managedidentityid").Value = identity;
                    }
                    var packagePath = Path.Combine(packageDirectory, "package", PluginPackageFiles.One(root, "package").Value);
                    if (PluginPackageFiles.Within(artifact.ItemSpec, StageDirectory))
                        throw new InvalidDataException($"Producer artifact '{artifact.ItemSpec}' must be outside Microsoft's intermediate staging directory.");
                    inputPath = artifact.ItemSpec;
                    var actual = PluginPackageFiles.PackageIdentity(artifact.ItemSpec);
                    if (!string.Equals(actual.Id, artifact.GetMetadata("PackageId"), StringComparison.OrdinalIgnoreCase) ||
                        !NuGetVersion.TryParse(actual.Version, out var actualVersion) ||
                        !NuGetVersion.TryParse(artifact.GetMetadata("PackageVersion"), out var expectedVersion) ||
                        !VersionComparer.VersionRelease.Equals(actualVersion, expectedVersion))
                        throw new InvalidDataException($"Validated artifact '{artifact.ItemSpec}' changed identity before staging.");
                    Directory.CreateDirectory(Path.GetDirectoryName(packagePath)!);
                    File.Copy(artifact.ItemSpec, packagePath, true);
                    PluginPackageFiles.One(root, "version").Value = SolutionVersion;
                    inputPath = xmlPath;
                    if (original != document.ToString(SaveOptions.DisableFormatting))
                        PluginPackageFiles.Save(document, xmlPath);
                }

                var packages = new List<ITaskItem>();
                names.Clear();
                if (Directory.Exists(directory))
                {
                    foreach (var folder in Directory.EnumerateDirectories(directory).OrderBy(path => path, StringComparer.Ordinal))
                    {
                        var name = Path.GetFileName(folder);
                        PluginPackageFiles.UniqueName(name);
                        if (!names.Add(name)) throw new InvalidDataException($"Duplicate plugin package directory '{name}' (case-insensitive).");
                        var xmlPath = Path.Combine(folder, "pluginpackage.xml");
                        inputPath = xmlPath;
                        var document = PluginPackageFiles.ReadXml(xmlPath);
                        var root = PluginPackageFiles.Metadata(document, name);
                        var version = PluginPackageFiles.One(root, "version");
                        if (version.Value != SolutionVersion)
                        {
                            version.Value = SolutionVersion;
                            PluginPackageFiles.Save(document, xmlPath);
                        }
                        var packagePath = Path.Combine(folder, "package", PluginPackageFiles.One(root, "package").Value);
                        var files = PackageFiles(folder);
                        if (files.Length != 1 || !string.Equals(Path.GetFullPath(files[0]), Path.GetFullPath(packagePath), StringComparison.Ordinal))
                            throw new InvalidDataException($"Plugin package '{name}' must contain exactly its referenced package '{packagePath}'.");
                        inputPath = packagePath;
                        var identity = PluginPackageFiles.PackageIdentity(packagePath);
                        if (!NuGetVersion.TryParse(identity.Version, out _))
                            throw new InvalidDataException($"Plugin package '{name}' has invalid NuGet version '{identity.Version}'.");
                        var item = new TaskItem("pluginpackages/" + name + "/pluginpackage.xml");
                        item.SetMetadata("XmlHash", PluginPackageFiles.Hash(xmlPath));
                        item.SetMetadata("PackageEntry", "pluginpackages/" + name + "/package/" + Path.GetFileName(packagePath));
                        item.SetMetadata("PackageHash", PluginPackageFiles.Hash(packagePath));
                        item.SetMetadata("PackageId", identity.Id);
                        item.SetMetadata("PackageVersion", identity.Version);
                        packages.Add(item);
                    }
                    var xmls = Directory.GetFiles(directory, "*", SearchOption.AllDirectories)
                        .Where(path => string.Equals(Path.GetFileName(path), "pluginpackage.xml", StringComparison.OrdinalIgnoreCase)).ToArray();
                    if (xmls.Length != packages.Count || PackageFiles(directory).Length != packages.Count)
                        throw new InvalidDataException("Unexpected nested/loose plugin metadata or package files in staged pluginpackages.");
                    if (Directory.GetFiles(directory, "*", SearchOption.AllDirectories)
                        .Any(path => path.EndsWith(".snupkg", StringComparison.OrdinalIgnoreCase)))
                        throw new InvalidDataException("Symbol archives must not be included in staged pluginpackages.");
                }
                Packages = packages.ToArray();
                Log.LogMessage(MessageImportance.High, $"XrmTools.Build staged and synchronized {Packages.Length} plugin packages.");
                Log.LogMessage(MessageImportance.Normal, $"XrmTools.Build plugin staging: {timer.ElapsedMilliseconds} ms.");
                return true;
            }
            catch (Exception exception) when (exception is IOException || exception is InvalidDataException || exception is XmlException ||
                exception is ArgumentException || exception is UnauthorizedAccessException)
            {
                Log.LogError(null, "XTB4001", null, inputPath, 0, 0, 0, 0,
                    $"XrmTools.Build: cannot stage plugin packages in '{StageDirectory}' at input '{inputPath}' " +
                    $"with solution version '{SolutionVersion}': {exception.Message} " +
                    "Correct the source pluginpackage.xml/reference metadata or producer artifact; do not edit the temporary stage.");
                return false;
            }
        }

        private static string[] PackageFiles(string directory) =>
            Directory.GetFiles(directory, "*", SearchOption.AllDirectories)
                .Where(path => path.EndsWith(".nupkg", StringComparison.OrdinalIgnoreCase)).ToArray();

        private XDocument Create(string name) => new XDocument(new XDeclaration("1.0", "utf-8", null),
            new XElement("pluginpackage", new XAttribute("uniquename", name),
                new XElement("exportkeyversion", "1"), new XElement("iscustomizable", "1"),
                new XElement("name", name),
                new XElement("package", new XAttribute("mimetype", "application/octet-stream"), name + ".nupkg"),
                new XElement("statecode", "0"), new XElement("statuscode", "1"),
                new XElement("version", SolutionVersion)));
    }
}
