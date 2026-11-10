# Phase 3 mixed-reference fixture

The solution references two explicitly marked C# producers, an unmarked C# project
with an empty `GetProjectOutputPath` contract, and an unmarked PCF project.
Producer A does not reference XrmTools.Build; producer B does. Their package IDs
are calculated in imported props, not read from literal project XML. Neither
producer implements Microsoft's assembly-output contract. Phase 4 now packs them
and uses their explicit artifact-return contract, which supports incremental reuse.
Producer A builds in Debug, while producer B's reference requests Release through
AdditionalProperties. Both keep their own independent NuGet versions.

The PCF project imports real Microsoft.PowerApps.MSBuild.Pcf 2.14.1 targets and
runs their normal npm build/output contract. Its dependency-free npm script copies
a minimal prebuilt control payload. This tests Microsoft's reference processing
and solution packager, not TypeScript or pcf-scripts compilation.

`FixtureProducerCount=0|1|2` selects the producer count.
`FixtureMicrosoftVersion` selects the Microsoft solution package independently.
The test runner copies the entire fixture tree to an ignored path with spaces
before restoring and building, so fixture outputs and logs are isolated.

The Phase 3 ZIP intentionally contains the PCF payload but no producer package.
XTB2005 warns about this incomplete package-inclusion feature. Discovery is
verified; Phase 5 staging is not implemented.
