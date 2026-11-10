using System;
using System.Collections.Generic;
using System.IO;
using Microsoft.Build.Evaluation;
using Microsoft.Build.Exceptions;
using Microsoft.Build.Framework;
using Microsoft.Build.Utilities;

namespace XrmTools.Build.Tasks
{
    public sealed class PreparePackAdapter : Task
    {
        [Required] public ITaskItem Producer { get; set; } = null!;
        [Required] public string AdapterPath { get; set; } = "";
        public string RemoveProperties { get; set; } = "";
        [Output] public ITaskItem[] Prepared { get; set; } = Array.Empty<ITaskItem>();

        public override bool Execute()
        {
            try
            {
                var properties = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
                foreach (var pair in ((IBuildEngine6)BuildEngine).GetGlobalProperties())
                    properties[pair.Key] = pair.Value;
                foreach (var name in (RemoveProperties + ";" + Producer.GetMetadata("UndefineProperties")).Split(';'))
                    properties.Remove(name.Trim());
                // Match MSBuild task property precedence: task properties, per-project Properties, then AdditionalProperties.
                AddProperties(properties, Producer.GetMetadata("SetConfiguration"));
                AddProperties(properties, Producer.GetMetadata("SetPlatform"));
                properties["NoBuild"] = "true";
                AddProperties(properties, Producer.GetMetadata("Properties"));
                AddProperties(properties, Producer.GetMetadata("AdditionalProperties"));
                var prepared = new TaskItem(Producer);
                using (var collection = new ProjectCollection(properties))
                {
                    var project = collection.LoadProject(Producer.GetMetadata("FullPath"));
                    if (project.Targets.ContainsKey("_CalculateInputsOutputsForPack") &&
                        project.Targets.ContainsKey("GenerateNuspec"))
                    {
                        var normal = project.GetPropertyValue("CustomAfterMicrosoftCommonTargets");
                        var cross = project.GetPropertyValue("CustomAfterMicrosoftCommonCrossTargetingTargets");
                        var extra =
                            ";XrmToolsOriginalAfterCommon=" + Escape(AbsoluteImport(normal, project.DirectoryPath)) +
                            ";XrmToolsOriginalAfterCrossTargeting=" + Escape(AbsoluteImport(cross, project.DirectoryPath)) +
                            ";CustomAfterMicrosoftCommonTargets=" + Escape(AdapterPath) +
                            ";CustomAfterMicrosoftCommonCrossTargetingTargets=" + Escape(AdapterPath);
                        prepared.SetMetadata("AdditionalProperties", Producer.GetMetadata("AdditionalProperties") + extra);
                    }
                    collection.UnloadAllProjects();
                }
                Prepared = new ITaskItem[] { prepared };
                return true;
            }
            catch (Exception exception) when (exception is InvalidProjectFileException ||
                exception is IOException || exception is ArgumentException || exception is UnauthorizedAccessException)
            {
                Log.LogError(null, "XTB3008", null, Producer.ItemSpec, 0, 0, 0, 0,
                    $"XrmTools.Build: cannot prepare the isolated NuGet adapter for '{Producer.GetMetadata("FullPath")}' " +
                    $"(SetConfiguration='{Producer.GetMetadata("SetConfiguration")}', SetPlatform='{Producer.GetMetadata("SetPlatform")}'): {exception.Message} " +
                    "Correct the producer's imports/property assignments and restore its dependencies for these build dimensions.");
                return false;
            }
        }

        private static void AddProperties(IDictionary<string, string> properties, string assignments)
        {
            foreach (var assignment in assignments.Split(';'))
            {
                if (string.IsNullOrWhiteSpace(assignment)) continue;
                var separator = assignment.IndexOf('=');
                if (separator <= 0) throw new ArgumentException("Invalid producer property assignment: " + assignment);
                properties[assignment.Substring(0, separator).Trim()] =
                    ProjectCollection.Unescape(assignment.Substring(separator + 1));
            }
        }

        private static string Escape(string value) => ProjectCollection.Escape(value);
        private static string AbsoluteImport(string value, string directory) =>
            value.Length == 0 ? "" : Path.GetFullPath(Path.IsPathRooted(value) ? value : Path.Combine(directory, value));
    }
}
