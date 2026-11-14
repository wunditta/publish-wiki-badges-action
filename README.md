# Publish Wiki with Badges

A GitHub Action that publishes a folder of Markdown files from your repository to the repository's wiki. It keeps the pages under version control next to your code, refuses to overwrite a page somebody edited online, and can turn short documentation tokens like `[str]` or `[**core**](core.md)` into small inline badges.

No dependencies: it runs Python 3 and git, both present on every GitHub runner.

## What it does

1. Clones the wiki repository (`<owner>/<repo>.wiki.git`).
2. Checks that the wiki's last commit was made by this action. If someone edited a page online since the last publish, the run fails and tells you who and when, so the edit can be copied into your pages first (`check-edits`, `force`).
3. Replaces the wiki content with the files of your pages folder (`path`), subfolders included.
4. Optionally converts the badge tokens of the pages (`badges`: the folder with `badges.json` and the icons), writing the badge images as SVG files into a folder of the wiki.
5. Commits and pushes. Nothing is pushed when the wiki is already up to date.

## Setting up a workflow, step by step

1. **Enable the wiki** of your repository: Settings › General › Features › Wikis. Create any first page on GitHub (the wiki repository does not exist until a page was created once).
2. **Decide who may edit online.** Under the same setting, "Restrict editing to collaborators only" keeps strangers out; the action's edit guard still protects your own quick online fixes from being overwritten.
3. **Create the pages folder** in your repository, by default `wiki/`. The page names are the file names (`Home.md` is the start page, `Getting-Started.md` becomes "Getting Started"). Any subfolder is published too, for images for example.
4. **Add the workflow** file `.github/workflows/wiki_badges.yml` (a copy is in this repository under `copy/workflows/`):

   ```yaml
   name: Publish wiki

   on:
     push:
       branches: [main]
       paths:                        # run only when something relevant changed
         - "wiki/**"
         - ".github/wiki_badges/**"             # badges.json and the icon files
         - ".github/workflows/wiki_badges.yml"
     workflow_dispatch:              # manual start from the Actions tab ("Run workflow")
       inputs:
         force:
           description: "Overwrite the wiki even if it was edited online (needed for the very first publish)"
           type: boolean
           default: false

   permissions:
     contents: write                 # the default token may push to the wiki with this

   concurrency:                      # never two publishes at the same time
     group: wiki
     cancel-in-progress: false

   jobs:
     publish:
       runs-on: ubuntu-latest
       steps:
         - uses: actions/checkout@v5

         - uses: wunditta/publish-wiki-badges-action@v1
           with:
             path: wiki                               # folder with the pages (default)
             badges: .github/wiki_badges              # folder with all files for this function, remove this line to disable badges
             force: ${{ inputs.force || false }}      # from the manual trigger; false on a push
   ```

5. **Badges (optional):** See below. Leave the `badges` line out of the workflow if you do not want them.
6. **First publish:** the wiki still holds the page you created on GitHub, which the edit guard treats as an online edit. Open the Actions tab, choose "Publish wiki", click "Run workflow" and tick *force*. From then on every push that touches the pages folder publishes on its own.
7. **When a run fails with "the wiki was changed online"**: look at the wiki's history, copy the change into your pages folder, commit and push. Only if the online change should really be dropped, run the workflow manually with *force*.

## Inputs

| Input | Default | Description |
|---|---|---|
| `path` | `wiki` | Folder in the repository that holds the pages. |
| `token` | `${{ github.token }}` | Token that may push to the wiki. The default works when the job has `permissions: contents: write`. A personal access token is needed only to publish into another repository's wiki (`wiki-repository`). |
| `check-edits` | `true` | Fail when the wiki's last commit was not made by this action. |
| `force` | `false` | Publish anyway; online edits are overwritten. |
| `badges` | *(empty)* | Folder holding `badges.json` and the icon files, e.g. `.github/wiki_badges`. Empty: no conversion, the pages are published as they are. |
| `commit-message` | `Publish wiki from <sha>` | Commit message in the wiki repository. |
| `wiki-repository` | the current repository | `owner/repo` whose wiki receives the pages. |

## Outputs and failures

| Output | Values |
|---|---|
| `published` | `true` when a commit was pushed, `false` when the wiki was already up to date. Set on successful runs only. |
| `result` | `published`, `unchanged`, or — when the step failed — `conflict` (the wiki was edited online, see step 7) or `error` (anything else, the log says what). |

A failed step fails the job, and GitHub mails the person who triggered the run (profile Settings › Notifications › Actions). To react in the workflow itself, give the step an `id` and test the result in a later step:

```yaml
      - id: wiki
        uses: wunditta/publish-wiki-badges-action@v1
        with:
          badges: .github/wiki_badges

      - if: failure() && steps.wiki.outputs.result == 'conflict'
        run: echo "::warning::The wiki was edited online - copy the change into wiki/ and push again."
```

## Badges

Basically text within squared brackets is treated as page (including links). Although the function is generic, it allows some variations as it was written for variable types in mind. Examples:

| You write | You get |
|---|---|
| `[str]`, `[num]`, `[bool]`, … | A badge per name; the name must be listed in `colors_per_badge` (unless `only_named_badges` is false), anything else is left as text |
| `[str{}]`, `[str++]`, `[*num?]` | Decoration: characters that cannot be part of a name (anything but letters, digits, `_` `.` `-`) before or after it are kept in the badge text and ignored for the color — `str{}` for "table of strings", `str++` for whatever this is |
| `[str/num]` | Alternatives: one badge each, `altGap` between them |
| `[(str/tab){}]` | A group: treated as one badge `str/tab{}` colored like its last item (reading "a table whose items are strings or tables") |
| `` `f(x [num])` `` | Tokens inside code spans become badges too (if `badgesInCodeSpans`) |
| `[core](core.md)`, `[**core**](core.md)`, `` [`core`](core.md) `` | Everything linking to another wiki page (i.e. another markdown file converted to a wiki page) and the displayed text is equal to the file name is treated as type `file`. (So, [go to the page core](core.md) would not generate a badge). |

With `strict_name_check: true` the whole content between the brackets is the name as written: `[str{}]` is a badge only if `str{}` itself is listed. The special meaning of `/` and `( )` are then off.

A table column whose cells hold nothing but badges gets its header widened invisibly, so the column cannot squeeze the badges (`tableMinWidth`). The badge images are written to `<wiki>/badges/` (`dir`) and referenced relatively, so they work on the wiki without any external service. Badge text is measured with Verdana's metrics; the font list in `font` should therefore start with Verdana.

### Installation

1. Create a folder, recommended is `.github/wiki_badges/`
2. Copy the template below into it as `badges.json`. See below for how to configure.
3. If you want to use icons copy them as SVG files into the same folder (an example `module-icon.svg` shaped as a puzzle tileis provided).

### Badges.json

#### How badges.json is organised

* **`global`** — what acts on the page or between badges: the SVG folder, alignment, the two heights in pixels (an `<img>` in the wiki can only be sized in pixels; GitHub's body text is 16 px and code 85 % of it, hence `codeHeight`), font, corner radius, padding, the gap between alternatives (`altGap`; inside code spans a gap that is only white space is dropped, because monospace would show it as a full space — `&vert;` or `/` are visible alternatives), the table guard, `only_named_badges` and `strict_name_check`.
* **`defaults`** — what every badge inherits: text color, fallback background color, `scale`, the vertical fine positioning `shift`/`codeShift`, whether tokens in code spans are converted, and the icon.
* **`type_specs`** — badge *types*. `default` (the `[name]` tokens) and `file` (the page links) always exist; any other key is a type of your own. A type may override any key of `defaults`; `""` inherits. A name belongs to the first type that lists it in `colors_per_badge`, so a type is simply a group of names with shared settings — there is no marker in the token.
* **`colors_per_badge`** — the background color per name, grouped by type; under `file` the names are page names. A name with `""` or without an entry gets the type's `color`.

Keys starting with `//` are comments; trailing commas are tolerated.

#### Custom Icons

* An icon is an SVG file next to `badges.json`, refrenced there as `icon.name` within `defaults` or for a specific type.
* Shapes with `fill="currentColor"` (or `stroke="currentColor"`) take whatever is defined `icon.color`, falling back to the badge's `textColor`. Shapes with any other colors keep them. The simplest way to make an icon: draw it in any vector editor, export as SVG, open the file in a text editor, replace the `fill="#…"` of the shapes by `fill="currentColor"`. `module-icon.svg` in this repository is such a file.
* The space left of the icon is `icon.padding`, between icon and text `icon.gap`, both as multiples of the badge height.
* Width and height attributes are ignored, the icon is scaled to `icon.height` × badge height. It keeps its aspect ratio and is rotated by `icon.rotate` degrees around its centre.

#### Template

Copy this to `.github/wiki_badges/badges.json` and adjust names and colors (the folder holds everything the badges need: the json and the icon files). The folder `copy/wiki_badges/` in this repository holds this file and the icon it names (`module-icon.svg`) ready to be copied into your `.github/`.

```json
{
    "//": "Keys starting with // are comments and are ignored. An empty string \"\" means: inherit. Trailing commas are tolerated.",

    "//global": "Settings for the page and between badges (cannot be set per type).",
    "global": {
        "//dir": "Folder inside the wiki that receives the generated SVG files.",
        "dir": "badges",
        "//align": "Vertical alignment of a badge in the text line (<img align>): baseline, middle, absmiddle, absbottom, texttop, top, bottom.",
        "align": "absmiddle",
        "//height": "Height of a badge in px (GitHub's body text is 16 px); everything else scales with it.",
        "height": 16,
        "//codeHeight": "Height inside a code span (GitHub renders code at 85 %); set equal to height for one size everywhere.",
        "codeHeight": 16,
        "font": "Verdana, DejaVu Sans, sans-serif",
        "//fontSize": "Text size as a multiple of the badge height.",
        "fontSize": 0.8,
        "//baseline": "Baseline below the badge centre as a multiple of the text size (centres the x-height).",
        "baseline": 0.37,
        "//radius": "Corner radius as a multiple of the height (0 = square corners).",
        "radius": 0.25,
        "//padding": "Space between the badge edge and the text, as a multiple of the height.",
        "padding": 0.16,
        "//altGap": "Between the badges of alternatives ([str/num]); a gap that is only white space is dropped inside code spans (monospace would show it as a full space). &vert; or / are visible alternatives.",
        "altGap": "&thinsp;",
        "//tableMinWidth": "A table column of badge-only cells gets its header widened so the column cannot shrink the images.",
        "tableMinWidth": true,
        "//only_named_badges": "true: a [name] becomes a badge only if the name is listed in colors_per_badge. false: every [name] becomes a badge (of type default or other if named there).",
        "only_named_badges": true,
        "//strict_name_check": "false: a name is letters, digits, _ . -; other characters before/after it are decoration kept in the badge text ([str++] is a str badge reading str++), / separates alternatives, (...) groups them. true: everything between [ ] is the name as written, / and () have no meaning, so str{} must be listed itself.",
        "strict_name_check": false
    },

    "//defaults": "Settings every badge inherits; a type (type_specs) may override any of them.",
    "defaults": {
        "textColor": "#000000",
        "//color": "Background colour of a badge whose name has no entry in colors_per_badge.",
        "color": "#888888",
        "//scale": "Size factor: the badge is height * scale (codeHeight * scale in code spans) high.",
        "scale": 1,
        "//shift": "Fine positioning as a multiple of the height: positive moves the badge up, negative down.",
        "shift": -0.05,
        "//codeShift": "The same inside code spans (default: shift).",
        "codeShift": -0.05,
        "//badgesInCodeSpans": "Tokens inside `code spans` become badges too (fenced code blocks never).",
        "badgesInCodeSpans": true,
        "//icon": "SVG file next to this json (empty double quotes = no icon), see README. rotate in degrees; height, padding (left of the icon) and gap (between icon and text) as multiples of the badge height; color applies only if the SVG uses currentColor.",
        "icon": {
            "name": "",
            "rotate": 0,
            "height": 0.84,
            "padding": 0.2,
            "gap": 0.12,
            "color": ""
        }
    },

    "//type_specs": "Badge types. 'default' ([name] tokens) and 'file' (page links [**name**](name.md)) always exist; add any other type as a group of names with their own settings. A name belongs to the first type that lists it in colors_per_badge.",
    "type_specs": {
        "default": {
        },
        "file": {
            "scale": 1.2,
            "shift": 0.05,
            "color": "#ececec",
            "icon": {
                "name": "module-icon.svg",
                "color": "#e5cc4c"
            }
        }
    },

    "//colors_per_badge": "Background colour per badge name, grouped by type. Names under 'file' are page names.",
    "colors_per_badge": {
        "default": {
            "name":  "#ececec",
        },
        "file": {
            "name": "#666666"
        }
    }
}
```

To try the conversion locally: `python3 badges.py <folder> badges.json` converts the pages of `<folder>` in place (work on a copy).

## Good to know

* The wiki's sidebar and footer are ordinary pages: `_Sidebar.md` and `_Footer.md` in the pages folder.
* GitHub's wiki table of contents lists every heading of a page; keep the heading count in mind when writing.
* The edit guard recognises its own commits by a trailer in the commit message, so it also works after the repository was renamed or the workflow moved.
* Publishing into the wiki of *another* repository needs a token with write access there (`token` and `wiki-repository`).

## License

GPL-3.0-or-later. Copyright wunditta.
