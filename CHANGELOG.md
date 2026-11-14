# Changelog

Format: [Keep a Changelog](https://keepachangelog.com), versions: [Semantic Versioning](https://semver.org).

## [Unreleased]

### First release

- Publishes a folder of Markdown pages to the repository wiki: clone, replace, commit as `github-actions[bot]`, push
- Edit guard: fails when the wiki was edited online since the last publish; `force` overrides (needed once for the first publish)
- Badges from a `badges.json` folder
  - type tokens `[str]`, `[str{}]`, `[str/num]`, `[(str/tab){}]`, page badges for links to existing pages
  - types with their own settings, icons from SVG files, strict or lenient name matching
- Inputs `path`, `token`, `check-edits`, `force`, `badges`, `commit-message`, `wiki-repository`
- Outputs `published`, `result` (`published` / `unchanged` / `conflict` / `error`)
- Template files under `copy/`: `badges.json`, `module-icon.svg`, `wiki_badges.yml`
- `README.md` in the pages folder is published as `Home.md`, the wiki's start page
  - unless a `Home.md` exists as well; links to it are rewritten
- The example workflow uses `actions/checkout@v5` (Node 24)
