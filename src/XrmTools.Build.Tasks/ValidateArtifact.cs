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
        [Output] public ITaskItem[] Artifacts { get; set; } = Array.Empty<ITaskItem>();

        public override bool Execute()
        {
            var selectedPath = Producer.GetMetadata("XrmToolsPluginPackagePath");
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

                selectedPath = path;
                if (!IsPrimary(path))
                    return Fail("XTB3002", $"'{path}' is not a primary .nupkg (symbols packages are excluded).");
                if (!File.Exists(path))
                    return Fail("XTB3003", $"Selected artifact '{path}' from {source} does not exist after Pack.");

                if (source == "NuGetAdapter")
                {
                    var evidence = AdapterOutputs.Single(item => IsPrimary(item.ItemSpec));
                    if (!string.Equals(evidence.GetMetadata("XrmToolsPackInvalidated"), "true", StringComparison.OrdinalIgnoreCase) ||
                        !string.Equals(evidence.GetMetadata("XrmToolsContinuePacking"), "true", StringComparison.OrdinalIgnoreCase) ||
                        !string.Equals(evidence.GetMetadata("XrmToolsIsPackable"), "true", StringComparison.OrdinalIgnoreCase) ||
                        evidence.GetMetadata("XrmToolsNuspecFile").Length > 0 ||
                        string.Equals(evidence.GetMetadata("XrmToolsVersionless"), "true", StringComparison.OrdinalIgnoreCase))
                        return Fail("XTB3007", "Automatic discovery cannot certify this producer's internal NuGet output " +
                            "contract (custom nuspec/versionless naming, disabled packaging, or missing invalidation evidence). " +
                            "A pre-existing predicted artifact is not accepted. Use an explicit selection contract.");
                }

                if (overridePath.Length == 0 && ContractOutputs.Length > 0)
                {
                    var primary = ContractOutputs.Where(item => IsPrimary(item.ItemSpec)).ToArray();
                    if (primary.Length != 1)
                        return Fail("XTB3001", "The producer return target must report exactly one primary package.");
                    if (expectedId.Length == 0) expectedId = primary[0].GetMetadata("PackageId");
                    if (expectedVersion.Length == 0) expectedVersion = primary[0].GetMetadata("PackageVersion");
                }
                if (expectedId.Length == 0 || expectedVersion.Length == 0)
                {
                    // Lower-priority artifact paths/counts do not constrain an explicit selection.
                    // Only their independently evaluated identity metadata can fill missing fields.
                    var evidence = AdapterOutputs.Select(item => new
                    {
                        Id = item.GetMetadata("XrmToolsEvaluatedPackageId"),
                        Version = item.GetMetadata("XrmToolsEvaluatedPackageVersion"),
                        Nuspec = item.GetMetadata("XrmToolsNuspecFile")
                    }).Distinct().ToArray();
                    if (evidence.Length != 1 || evidence[0].Nuspec.Length > 0)
                        return Fail("XTB3004", "Expected identity/version is unavailable or uses custom nuspec naming. " +
                            "Supply PackageId/PackageVersion on the selected producer return item or " +
                            "XrmToolsPluginPackageId/XrmToolsPluginPackageVersion on the explicit reference. " +
                            "An unrelated lower-priority return item cannot establish identity for an explicit path.");
                    if (expectedId.Length == 0) expectedId = evidence[0].Id;
                    if (expectedVersion.Length == 0) expectedVersion = evidence[0].Version;
                    if (expectedId.Length == 0 || expectedVersion.Length == 0)
                        return Fail("XTB3004", "The producer adapter did not return evaluated expected identity/version.");
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
                return Fail("XTB3005", $"Cannot validate the exact plugin package '{selectedPath}': {exception.Message}");
            }
        }

        private bool Fail(string code, string message)
        {
            Log.LogError(null, code, null, Producer.ItemSpec, 0, 0, 0, 0,
                $"XrmTools.Build: producer '{Producer.GetMetadata("FullPath")}': " + message + " Use an exact XrmToolsPluginPackagePath or " +
                "XrmToolsGetPluginPackageArtifact Returns contract with expected identity/version. No directory search is performed.");
            return false;
        }

        private static bool IsPrimary(string path) =>
            path.EndsWith(".nupkg", StringComparison.OrdinalIgnoreCase) &&
            !path.EndsWith(".symbols.nupkg", StringComparison.OrdinalIgnoreCase);

        private static string Absolute(string path, string directory) =>
            Path.GetFullPath(Path.IsPathRooted(path) ? path : Path.Combine(directory, path));

        internal static (string Id, string Version) ReadIdentity(Stream stream)
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
