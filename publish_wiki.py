#!/usr/bin/env python3
"""Publish a folder of Markdown pages to the repository's GitHub wiki.

Steps: clone the wiki repository, refuse if it was edited online since the last publish (unless forced),
replace its content with the pages of the source folder, optionally expand the badge shorthands (badges.py),
commit and push. Driven by environment variables (set by action.yml):
  INPUT_PATH            folder with the pages (default "wiki")
  INPUT_TOKEN           token that may push to the wiki repository
  INPUT_CHECK_EDITS     "true": fail if the wiki's last commit was not made by this action
  INPUT_FORCE           "true": publish even then (the online edits are overwritten)
  INPUT_BADGES          folder holding badges.json and the icon files; empty = no badge conversion
  INPUT_COMMIT_MESSAGE  commit message in the wiki repository
  INPUT_WIKI_REPOSITORY "owner/repo" whose wiki receives the pages (default: GITHUB_REPOSITORY)
  GITHUB_REPOSITORY, GITHUB_SHA, GITHUB_OUTPUT  provided by GitHub Actions
Outputs: published=true|false (successful runs); result=published|unchanged|conflict|error (conflict and error with a failed step).
"""
import os, re, sys, shutil, subprocess, tempfile, pathlib

MARKER = "Published-by: publish-wiki-badges-action"
BOT_NAME = "github-actions[bot]"
BOT_MAIL = "41898282+github-actions[bot]@users.noreply.github.com"
HERE = pathlib.Path(__file__).resolve().parent


def env(name, default=""):
    return os.environ.get(name, default).strip()


def flag(name):
    return env(name).lower() in ("1", "true", "yes", "on")


def output(name, value):
    path = env("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write("%s=%s\n" % (name, value))


def fail(text, result="error"):
    output("result", result)
    print("::error::" + text.replace("\n", "%0A"))
    sys.exit(1)


def git(args, cwd, check=True, capture=False):
    r = subprocess.run(["git"] + args, cwd=cwd, text=True,
                       stdout=subprocess.PIPE if capture else None, stderr=subprocess.STDOUT if capture else None)
    if check and r.returncode != 0:
        fail("Git %s failed%s" % (" ".join(args), (":\n" + r.stdout) if capture and r.stdout else ""))
    return (r.stdout or "").strip() if capture else r.returncode


def main():
    src = pathlib.Path(env("INPUT_PATH", "wiki"))
    if not src.is_dir():
        fail("The pages folder \"%s\" does not exist" % src)
    if not any(src.glob("*.md")):
        fail("The pages folder \"%s\" holds no .md file" % src)
    token = env("INPUT_TOKEN")
    if not token:
        fail("No token: pass \"token: ${{ github.token }}\" (and give the job \"permissions: contents: write\")")
    repo = env("INPUT_WIKI_REPOSITORY") or env("GITHUB_REPOSITORY")
    badges = env("INPUT_BADGES")
    message = env("INPUT_COMMIT_MESSAGE") or ("Publish wiki from " + env("GITHUB_SHA")[:7])
    check = flag("INPUT_CHECK_EDITS")
    force = flag("INPUT_FORCE")

    work = pathlib.Path(tempfile.mkdtemp(prefix="wiki-"))
    clone = work / "wiki"
    url = env("WIKI_CLONE_URL") or "https://x-access-token:%s@github.com/%s.wiki.git" % (token, repo)   # WIKI_CLONE_URL: for local tests
    r = subprocess.run(["git", "clone", "--quiet", url, str(clone)], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if r.returncode != 0:
        out = r.stdout.replace(token, "***")
        fail("Could not clone the wiki of %s.\nThe wiki must exist: enable it under Settings > Features and create any first page on GitHub once.\n%s" % (repo, out))

    # the edit guard: the last wiki commit must be one of ours
    last = git(["log", "-1", "--format=%an <%ae>%n%ad%n%B"], clone, capture=True)
    author, date = last.split("\n")[0], last.split("\n")[1]
    ours = MARKER in last
    if not ours:
        if check and not force:
            fail("The wiki was changed online since the last publish (last commit by %s on %s), or it is the first time published.\n"
                 "Either copy the online changes into your markdown files in \"%s\" and push again, or run the workflow manually from here and tick 'Overwrite the wiki even...' checkbox." % (author, date, src), "conflict")
        print("Note: the last wiki commit by %s on %s is not from this action - overwriting (%s)" % (author, date, "force" if force else "check-edits off"))

    # replace the content
    for item in clone.iterdir():
        if item.name == ".git":
            continue
        shutil.rmtree(item) if item.is_dir() else item.unlink()
    shutil.copytree(src, clone, dirs_exist_ok=True, ignore=shutil.ignore_patterns(".git"))

    # README.md is the wiki's Home page (GitHub shows Home.md as the start page)
    readme, home = clone / "README.md", clone / "Home.md"
    if readme.is_file() and not home.is_file():
        readme.rename(home)
        for page in clone.rglob("*.md"):
            text = page.read_text(encoding="utf-8")
            new = re.sub(r"(\]\()(?:\./)?README(?:\.md)?(?=[)#])", r"\1Home", text)
            if new != text:
                page.write_text(new, encoding="utf-8")
        print("README.md published as Home.md")
    elif readme.is_file():
        print("Note: both README.md and Home.md exist - README.md stays a page of its own")

    # badges
    if badges:
        folder = pathlib.Path(badges)
        cfg = folder / "badges.json"
        if not cfg.is_file():
            fail("No badges.json in the badges folder \"%s\"" % folder)
        r = subprocess.run([sys.executable, "-I", str(HERE / "badges.py"), str(clone), str(cfg.resolve())], text=True)
        if r.returncode != 0:
            fail("Badge conversion failed")

    git(["config", "user.name", BOT_NAME], clone)
    git(["config", "user.email", BOT_MAIL], clone)
    git(["add", "-A"], clone)
    if git(["diff", "--cached", "--quiet"], clone, check=False) == 0:
        print("Wiki is up to date - nothing to publish")
        output("published", "false")
        output("result", "unchanged")
        return
    git(["commit", "--quiet", "-m", message, "-m", MARKER], clone)
    git(["push", "--quiet"], clone)
    changed = git(["show", "--stat", "--format=", "HEAD"], clone, capture=True)
    print("Published to https://github.com/%s/wiki\n%s" % (repo, changed))
    output("published", "true")
    output("result", "published")


if __name__ == "__main__":
    main()
