# HallwayWM contributor instructions

HallwayWM is a standalone public GNOME Shell extension. Keep its sources, build, tests and installation usable from this repository alone.

- Write maintained code, comments, documentation and commit messages in English, following the existing style.
- Keep consumer-specific settings, installation inventories, source pins and deployment paths in the consuming project. Dependencies point from consumers to HallwayWM. Public instructions and tests use this checkout and explicit fixtures.
- Resolve paths relative to the project or standard XDG locations. Read extension identity from metadata in tools and tests. Preserve the settings schema, import/export formats, authorship and licenses when changing implementation or packaging.
- Keep TypeScript as the maintained implementation. Generated output, dependencies, archives, test logs and private application rules remain outside Git.
- Preserve the distinction between persistent application rules and temporary session layouts. Keep geometry, workspace, lock and asynchronous placement changes covered by the relevant scenarios.
- Test with temporary XDG directories and isolated D-Bus/settings backends. Installation checks use a temporary destination; do not reload the active desktop or change its preferences as a side effect of validation.
- Run `npm run check`, `npm run build` and `npm run test:profiles` for code changes. Run preferences or native integration scenarios when their behavior changes, following [development and validation](docs/DEVELOPMENT.md). Report unavailable dependencies and untested physical/session behavior explicitly.
