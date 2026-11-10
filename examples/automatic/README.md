# Evaluated producer recognition experiment

The default XrmTools.Build package is unchanged: it still requires explicit
markers. This experiment is a **separate local package artifact**:

```sh
dotnet pack XrmTools.Build.csproj -o artifacts/local-feed \
  -p:XrmToolsPrototypeRecognition=true -p:PackageVersion=0.5.0-recognition
dotnet build examples/automatic/Solution.cdsproj
```

The last command intentionally reproduces `NU1201`: the solution has the PAC
net462 defaults while PAC 2.14.1 generates net48 plugin projects. Recognition
does not repair restore/framework compatibility.

To isolate the later stages, in a disposable copy set **only the solution's**
`TargetFramework=net48` and `TargetFrameworkVersion=v4.8`, then build again.
Do not pass these as command-line global properties to all projects. This
compatible diagnostic builds the plugin + source-driven JavaScript PCF ZIP with
plain project references, no marker, explicit unique name, ReferenceOutputAssembly
metadata or replacement consumer opt-in property. The experiment retains the
scoped filter and isolated Pack freshness adapter.

`Plugin/` was generated with PAC **2.14.1+g6f517e5**:

```sh
pac plugin init --outputDirectory examples/automatic/Plugin --author XrmTools --skip-signing
```

Its generated imports and source remain. Floating package versions were pinned
to Microsoft.PowerApps.MSBuild.Plugin **1.52.1**,
Microsoft.CrmSdk.CoreAssemblies **9.0.2.60**, and reference assemblies **1.0.3**;
XrmTools.Build **0.5.0-recognition** was added. It is intentionally unsigned and
has not been registered/deployed to Dataverse.

`Ordinary/` references XrmTools.Build and has a PackageId but no plugin capability.
Add `<ProjectReference Include="Ordinary/Ordinary.csproj" />` in the disposable
compatible solution to test the mixed case: only Plugin is classified, and
Microsoft reference processing still fails `MSB4057` because the ordinary
library lacks `GetProjectOutputPath`. We do not filter that reference or add a
dummy output to hide the failure.

`python3 eng/test-recognition.py` runs both Microsoft solution versions
2.13.1/2.14.1 after `./eng/test-package.sh` has created the experimental artifact.
It verifies restore graphs, read-only classification, explicit true/false/name
overrides, exact ZIP package bytes, source edits, incremental compilation and
before/after hooks. See the [full evidence and VS procedure](../../docs/consumer-contract-prototype.md).
