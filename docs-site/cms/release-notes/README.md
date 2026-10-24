# Release documentation

Before creating an `agents-vMAJOR.MINOR.PATCH` release tag, add a file named
`agents-vMAJOR.MINOR.PATCH.md` in this directory. Start it with a title and a
one-sentence summary, then explain user-visible changes, any action needed,
platform limitations, and relevant guide links. The release workflow checks
that the matching file exists. Strapi publishes these versioned notes
automatically; procedural guides remain editable in the CMS.

Do not include credentials, private keys, device local keys, or tenant data in
release notes.
