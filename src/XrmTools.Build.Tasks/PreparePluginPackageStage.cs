using System;
using System.Diagnostics;
using System.IO;
using Microsoft.Build.Framework;
using Microsoft.Build.Utilities;

namespace XrmTools.Build.Tasks
{
    public sealed class PreparePluginPackageStage : Task
    {
        [Required] public string StageDirectory { get; set; } = "";
        [Required] public string SourceDirectory { get; set; } = "";
        [Required] public string IntermediateDirectory { get; set; } = "";

        public override bool Execute()
        {
            var timer = Stopwatch.StartNew();
            try
            {
                var stage = Path.GetFullPath(StageDirectory);
                var source = Path.GetFullPath(SourceDirectory);
                if (!PluginPackageFiles.Within(stage, IntermediateDirectory) ||
                    string.Equals(stage, source, StringComparison.OrdinalIgnoreCase) ||
                    PluginPackageFiles.Within(stage, source) || PluginPackageFiles.Within(source, stage))
                    throw new InvalidDataException("Solution staging must be strictly inside IntermediateOutputPath and disjoint from SolutionRootPath (neither may contain the other).");
                PluginPackageFiles.NoTreeLinks(source);
                PluginPackageFiles.NoTreeLinks(stage);
                // Microsoft's Copy only overlays files. A failed prior build can leave removed packages behind.
                var packages = Path.Combine(stage, "pluginpackages");
                if (Directory.Exists(packages)) Directory.Delete(packages, true);
                Log.LogMessage(MessageImportance.Normal, $"XrmTools.Build plugin stage preparation: {timer.ElapsedMilliseconds} ms.");
                return true;
            }
            catch (Exception exception) when (exception is IOException || exception is InvalidDataException || exception is ArgumentException ||
                exception is UnauthorizedAccessException)
            {
                Log.LogError(null, "XTB4000", null, null, 0, 0, 0, 0, "XrmTools.Build: " + exception.Message);
                return false;
            }
        }
    }
}
