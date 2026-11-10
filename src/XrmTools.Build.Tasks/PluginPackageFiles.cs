using System;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using System.Xml;
using System.Xml.Linq;

namespace XrmTools.Build.Tasks
{
    internal static class PluginPackageFiles
    {
        internal static XDocument ReadXml(Stream stream)
        {
            using (var reader = XmlReader.Create(stream, new XmlReaderSettings
            {
                DtdProcessing = DtdProcessing.Prohibit,
                XmlResolver = null,
                MaxCharactersInDocument = 4 * 1024 * 1024
            }))
                return XDocument.Load(reader, LoadOptions.PreserveWhitespace);
        }

        internal static XDocument ReadXml(string path)
        {
            using (var stream = File.OpenRead(path)) return ReadXml(stream);
        }

        internal static XElement One(XElement? parent, string name)
        {
            if (parent == null) throw new InvalidDataException($"Missing XML parent for required '{name}' element.");
            var nodes = parent.Elements(parent.Name.Namespace + name).ToArray();
            if (nodes.Length != 1) throw new InvalidDataException($"Expected exactly one {parent.Name.LocalName}/{name}.");
            return nodes[0];
        }

        internal static XElement Manifest(XDocument document)
        {
            if (document.Root?.Name.LocalName != "ImportExportXml")
                throw new InvalidDataException("Solution XML must have an ImportExportXml root.");
            return One(document.Root, "SolutionManifest");
        }

        internal static void UniqueName(string name)
        {
            if (!Regex.IsMatch(name, @"\A[A-Za-z][A-Za-z0-9]*_[A-Za-z0-9_.-]+\z") ||
                name.EndsWith(".", StringComparison.Ordinal))
                throw new InvalidDataException($"Plugin package unique name '{name}' must be a safe publisher-prefixed name (for example xt_MyPlugin).");
        }

        internal static XElement Metadata(XDocument document, string name)
        {
            var root = document.Root;
            if (root == null || root.Name.LocalName != "pluginpackage" ||
                (string?)root.Attribute("uniquename") != name)
                throw new InvalidDataException($"pluginpackage.xml must have pluginpackage/@uniquename='{name}' matching its directory.");
            if (string.IsNullOrWhiteSpace(One(root, "name").Value))
                throw new InvalidDataException($"Plugin package '{name}' has an empty name.");
            One(root, "version");
            var package = One(root, "package");
            if (!Regex.IsMatch(package.Value, @"\A[A-Za-z0-9_][A-Za-z0-9_.-]*\.nupkg\z", RegexOptions.IgnoreCase) ||
                package.Value.EndsWith(".symbols.nupkg", StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException($"Plugin package '{name}' has package='{package.Value}'; it must reference one nonempty primary .nupkg filename, without directories.");
            var identities = root.Elements(root.Name.Namespace + "managedidentityid").ToArray();
            if (identities.Length > 1) throw new InvalidDataException($"Plugin package '{name}' has duplicate managedidentityid elements.");
            if (identities.Length == 1) Identity(One(identities[0], "managedidentityid").Value);
            return root;
        }

        internal static void Identity(string value)
        {
            if (!Guid.TryParse(value, out var guid) || guid == Guid.Empty)
                throw new InvalidDataException($"ManagedIdentityId '{value}' must be a nonempty GUID.");
        }

        internal static (string Id, string Version) PackageIdentity(string path)
        {
            using (var archive = ZipFile.OpenRead(path))
            {
                var manifests = archive.Entries.Where(entry => entry.FullName.IndexOfAny(new[] { '/', '\\' }) < 0 &&
                    entry.FullName.EndsWith(".nuspec", StringComparison.OrdinalIgnoreCase)).ToArray();
                if (manifests.Length != 1) throw new InvalidDataException($"'{path}' must contain exactly one root nuspec.");
                using (var stream = manifests[0].Open()) return ValidateArtifact.ReadIdentity(stream);
            }
        }

        internal static string Hash(Stream stream)
        {
            using (var hash = SHA256.Create()) return BitConverter.ToString(hash.ComputeHash(stream)).Replace("-", "");
        }

        internal static string Hash(string path)
        {
            using (var stream = File.OpenRead(path)) return Hash(stream);
        }

        internal static bool Within(string path, string directory) =>
            Path.GetFullPath(path).TrimEnd(Path.DirectorySeparatorChar).StartsWith(
                Path.GetFullPath(directory).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar,
                StringComparison.OrdinalIgnoreCase);

        internal static void NoLinks(string path)
        {
            for (var current = Path.GetFullPath(path); !string.IsNullOrEmpty(current); current = Path.GetDirectoryName(current))
            {
                FileAttributes attributes;
                try { attributes = File.GetAttributes(current); }
                catch (FileNotFoundException) { continue; }
                catch (DirectoryNotFoundException) { continue; }
                if ((attributes & FileAttributes.ReparsePoint) != 0)
                    throw new InvalidDataException($"Staging/source path '{path}' traverses symbolic link or reparse point '{current}'. Use physical, disjoint directories.");
            }
        }

        internal static void NoTreeLinks(string directory)
        {
            NoLinks(directory);
            if (!Directory.Exists(directory)) return;
            foreach (var path in Directory.EnumerateFileSystemEntries(directory))
            {
                NoLinks(path);
                if (Directory.Exists(path)) NoTreeLinks(path);
            }
        }

        internal static void Save(XDocument document, string path)
        {
            // Preserve declaration encoding, whitespace, comments, namespaces and unknown elements.
            var encoding = Encoding.GetEncoding(document.Declaration?.Encoding ?? "utf-8");
            using (var writer = XmlWriter.Create(path, new XmlWriterSettings
            {
                Encoding = encoding,
                Indent = false,
                NewLineHandling = NewLineHandling.None,
                OmitXmlDeclaration = document.Declaration == null
            }))
                document.Save(writer);
        }
    }
}
