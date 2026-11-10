using System;
using System.Linq;
using Microsoft.Build.Framework;
using Microsoft.Build.Utilities;

namespace XrmTools.Build.Tasks
{
    public sealed class RecognizeProducers : Task
    {
        [Required] public ITaskItem[] References { get; set; } = Array.Empty<ITaskItem>();
        [Required] public ITaskItem[] Capabilities { get; set; } = Array.Empty<ITaskItem>();
        [Output] public ITaskItem[] Recognized { get; set; } = Array.Empty<ITaskItem>();

        public override bool Execute()
        {
            Recognized = References.Where(reference => Capabilities.Any(capability =>
                capability.GetMetadata("Capability") == "MicrosoftPluginPackage"
                && string.Equals(capability.GetMetadata("FullPath"), reference.GetMetadata("FullPath"),
                    StringComparison.OrdinalIgnoreCase)))
                .Select(reference => (ITaskItem)new TaskItem(reference)).ToArray();
            return true;
        }
    }
}
