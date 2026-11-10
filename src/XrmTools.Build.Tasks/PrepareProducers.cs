using System;
using System.Linq;
using Microsoft.Build.Framework;
using Microsoft.Build.Utilities;

namespace XrmTools.Build.Tasks
{
    public sealed class PrepareProducers : Task
    {
        [Required] public ITaskItem[] Producers { get; set; } = Array.Empty<ITaskItem>();
        public ITaskItem[] ResolvedReferences { get; set; } = Array.Empty<ITaskItem>();
        [Output] public ITaskItem[] Prepared { get; set; } = Array.Empty<ITaskItem>();

        public override bool Execute()
        {
            Prepared = Producers.Select(producer =>
            {
                var copy = new TaskItem(producer);
                var resolved = ResolvedReferences.FirstOrDefault(reference =>
                    string.Equals(reference.GetMetadata("FullPath"), producer.GetMetadata("FullPath"),
                        StringComparison.OrdinalIgnoreCase));
                if (resolved != null)
                {
                    foreach (var name in new[] { "SetConfiguration", "SetPlatform", "GlobalPropertiesToRemove" })
                        copy.SetMetadata(name, resolved.GetMetadata(name));
                }
                return (ITaskItem)copy;
            }).ToArray();
            return true;
        }
    }
}
