using System;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Xml;
using System.Xml.Linq;
using Microsoft.Build.Framework;
using Microsoft.Build.Utilities;
using NuGet.Versioning;

namespace XrmTools.Build.Tasks
{
    public sealed class ValidateArtifact : Task
    {
        [Required] public ITaskItem Producer { get; set; } = null!;
        [Required] public string SolutionDirectory { get; set; } = "";
        public ITaskItem[] ContractOutputs { get; set; } = Array.Empty<ITaskItem>();
        public ITaskItem[] AdapterOutputs { get; set; } = Array.Empty<ITaskItem>();
        public long DiscoveryStartedUtcTicks { get; set; }
        [Output] public ITaskItem[] Artifacts { get; set; } = Array.Empty<ITaskItem>();

        public override bool Execute()
        {
            try
            {
                var producerPath = Producer.GetMetadata("FullPath");
                var producerDirectory = Path.GetDirectoryName(producerPath)!;
                var overridePath = Producer.GetMetadata("XrmToolsPluginPackagePath");
                var expectedId = Producer.GetMetadata("XrmToolsPluginPackageId");
                var expectedVersion = Producer.GetMetadata("XrmToolsPluginPackageVersion");
                var source = overridePath.Length > 0 ? "ExplicitPath" :
                    ContractOutputs.Length > 0 ? "ProducerTarget" : "NuGetAdapter";
                string path;
                if (overridePath.Length > 0)
                    path = Absolute(overridePath, SolutionDirectory);
                else
                {
                    var outputs = ContractOutputs.Length > 0 ? ContractOutputs : AdapterOutputs;
                    var candidates = outputs.Where(item => IsPrimary(item.ItemSpec)).ToArray();
                    if (candidates.Length != 1)
                        return Fail("XTB3001", $"Expected exactly one primary .nupkg from {source}, found {candidates.Length}. " +
                            $"Reported outputs: {string.Join(", ", outputs.Select(item => item.ItemSpec))}.");
                    path = Absolute(candidates[0].ItemSpec, producerDirectory);
                }

                if (!IsPrimary(path))
                    return Fail("XTB3002", $"'{path}' is not a primary .nupkg (symbols packages are excluded).");
                if (!File.Exists(path))
                    return Fail("XTB3003", $"Selected artifact '{path}' from {source} does not exist after Pack.");

                if (ContractOutputs.Length > 0)
                {
                    var primary = ContractOutputs.Where(item => IsPrimary(item.ItemSpec)).ToArray();
                    if (primary.Length != 1)
                        return Fail("XTB3001", "The producer return target must report exactly one primary package.");
                    if (expectedId.Length == 0) expectedId = primary[0].GetMetadata("PackageId");
                    if (expectedVersion.Length == 0) expectedVersion = primary[0].GetMetadata("PackageVersion");
                }
                if (expectedId.Length == 0 || expectedVersion.Length == 0)
                {
                    var nuspecs = AdapterOutputs.Where(item =>
                        string.Equals(Path.GetExtension(item.ItemSpec), ".nuspec", StringComparison.OrdinalIgnoreCase) &&
                        !item.ItemSpec.EndsWith(".symbols.nuspec", StringComparison.OrdinalIgnoreCase)).ToArray();
                    if (nuspecs.Length != 1 || !File.Exists(Absolute(nuspecs[0].ItemSpec, producerDirectory)))
                        return Fail("XTB3004", "Expected identity/version is unavailable. The internal NuGet adapter did not " +
                            "return one existing generated nuspec. Supply PackageId/PackageVersion on the producer return item " +
                            "or XrmToolsPluginPackageId/XrmToolsPluginPackageVersion on the reference.");
                    using (var stream = File.OpenRead(Absolute(nuspecs[0].ItemSpec, producerDirectory)))
                    {
                        var expected = ReadIdentity(stream);
                        if (expectedId.Length == 0) expectedId = expected.Id;
                        if (expectedVersion.Length == 0) expectedVersion = expected.Version;
                    }
                }

                using (var archive = ZipFile.OpenRead(path))
                {
                    var manifests = archive.Entries.Where(entry =>
                        entry.FullName.IndexOf('/') < 0 && entry.FullName.IndexOf('\\') < 0 &&
                        entry.FullName.EndsWith(".nuspec", StringComparison.OrdinalIgnoreCase)).ToArray();
                    if (manifests.Length != 1)
                        return Fail("XTB3005", $"'{path}' must contain exactly one root nuspec; found {manifests.Length}.");
                    using (var stream = manifests[0].Open())
                    {
                        var actual = ReadIdentity(stream);
                        if (!NuGetVersion.TryParse(expectedVersion, out var expected) ||
                            !NuGetVersion.TryParse(actual.Version, out var version) ||
                            !string.Equals(expectedId, actual.Id, StringComparison.OrdinalIgnoreCase) ||
                            !VersionComparer.VersionRelease.Equals(expected, version))
                            return Fail("XTB3006", $"Package identity mismatch at '{path}': expected " +
                                $"'{expectedId} {expectedVersion}', actual '{actual.Id} {actual.Version}'.");
                        if (source == "NuGetAdapter" && File.GetLastWriteTimeUtc(path).Ticks < DiscoveryStartedUtcTicks)
                            return Fail("XTB3007", $"The internal adapter selected an unchanged pre-existing artifact '{path}'. " +
                                "It cannot prove that Pack produced this path in this invocation (including custom nuspec naming " +
                                "and incremental Pack). Use an explicit path or producer contract for intentional reuse.");
                        var artifact = new TaskItem(Producer);
                        artifact.ItemSpec = path;
                        artifact.SetMetadata("ProducerProject", producerPath);
                        artifact.SetMetadata("PackageId", actual.Id);
                        artifact.SetMetadata("PackageVersion", version!.ToNormalizedString());
                        artifact.SetMetadata("DiscoverySource", source);
                        Artifacts = new ITaskItem[] { artifact };
                        Log.LogMessage(MessageImportance.High,
                            $"XrmTools.Build validated plugin artifact '{path}' ({actual.Id} {actual.Version}, {source}).");
                    }
                }
                return true;
            }
            catch (Exception exception) when (exception is IOException || exception is InvalidDataException ||
                exception is XmlException || exception is ArgumentException || exception is UnauthorizedAccessException)
            {
                return Fail("XTB3005", $"Cannot validate the exact plugin package: {exception.Message}");
            }
        }

        private bool Fail(string code, string message)
        {
            Log.LogError(null, code, null, Producer.ItemSpec, 0, 0, 0, 0,
                "XrmTools.Build: " + message + " Use an exact XrmToolsPluginPackagePath or " +
                "XrmToolsGetPluginPackageArtifact Returns contract with expected identity/version. No directory search is performed.");
            return false;
        }

        private static bool IsPrimary(string path) =>
            path.EndsWith(".nupkg", StringComparison.OrdinalIgnoreCase) &&
            !path.EndsWith(".symbols.nupkg", StringComparison.OrdinalIgnoreCase);

        private static string Absolute(string path, string directory) =>
            Path.GetFullPath(Path.IsPathRooted(path) ? path : Path.Combine(directory, path));

        private static (string Id, string Version) ReadIdentity(Stream stream)
        {
            using (var reader = XmlReader.Create(stream, new XmlReaderSettings
            {
                DtdProcessing = DtdProcessing.Prohibit,
                XmlResolver = null,
                MaxCharactersInDocument = 4 * 1024 * 1024
            }))
            {
                var document = XDocument.Load(reader);
                var sections = document.Root?.Elements().Where(element => element.Name.LocalName == "metadata").ToArray();
                if (document.Root?.Name.LocalName != "package" || sections?.Length != 1)
                    throw new InvalidDataException("A nuspec must have one package/metadata element.");
                var metadata = sections[0];
                var id = metadata?.Elements().Where(element => element.Name.LocalName == "id").ToArray();
                var version = metadata?.Elements().Where(element => element.Name.LocalName == "version").ToArray();
                if (id?.Length != 1 || version?.Length != 1 ||
                    string.IsNullOrWhiteSpace(id[0].Value) || string.IsNullOrWhiteSpace(version[0].Value))
                    throw new InvalidDataException("A nuspec must have exactly one nonempty metadata/id and metadata/version.");
                if (metadata!.Descendants().Any(element => element.Name.LocalName == "packageType" &&
                    string.Equals((string?)element.Attribute("name"), "SymbolsPackage", StringComparison.OrdinalIgnoreCase)))
                    throw new InvalidDataException("The selected nuspec identifies a symbols package.");
                return (id[0].Value, version[0].Value);
            }
        }
    }
}
