# Minimal Dataverse solution fixture

This legacy-style `.cdsproj` deliberately references both the pinned Microsoft
solution package and a locally packed `XrmTools.Build` package. It contains only a
minimal `Other/Solution.xml`; the fixture is for validating package imports,
Microsoft target ordering, and staged solution-version behavior. It is not a
Dataverse deployment fixture.
