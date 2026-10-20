# Documentation and releases

The documentation is built with [Zensical](https://zensical.org/) from `docs/` and `zensical.toml`.
GitHub Pages hosts it at [jessielw.github.io/VideoForge](https://jessielw.github.io/VideoForge/).

## Preview

Install only the documentation group, without the app or its media dependencies:

```sh
uv sync --only-group docs --frozen
uv run --only-group docs --frozen zensical serve
```

Open `http://localhost:8000`. If you also develop the app, retain its optional dependencies:

```sh
uv sync --group docs --extra desktop --extra filters
```

With the dev and docs groups installed, `uv run --group docs poe docs` is a preview shortcut.

## Build

```sh
uv run --only-group docs --frozen zensical build --clean --strict
```

The output is `site/`, which is ignored by Git. Strict mode fails on reported warnings, including
broken documentation links. Keep all public pages in the configured navigation.

`reference/changelog.md` and `development/architecture.md` include the root `CHANGELOG.md` and
`ARCHITECTURE.md` using Markdown snippets. Edit those root documents to keep GitHub and the site
in sync. Internal `audit-*.md` notes are excluded from the published site.

## GitHub Pages

The [Docs workflow](https://github.com/jessielw/VideoForge/actions/workflows/docs.yml):

1. Builds documentation changes on pull requests.
2. Builds and deploys matching pushes to `main`.
3. Allows a manual run from the Actions page; only a run on `main` deploys.

It installs the locked docs group independently of the application. Deployment uses GitHub's
Pages artifact and OIDC flow; it does not require a personal access token in repository secrets.
The one-time repository setting is **Settings → Pages → Source → GitHub Actions**. This follows
[Zensical's publishing guide](https://zensical.org/docs/publish-your-site/).

The GitHub Pages site contains the docs build only. Publishing these docs does not change the
source repository's visibility. GitHub account plan limits still apply to Pages for private repositories.

## Application releases

Application releases use version tags without a leading `v`, such as `0.1.0` or `0.1.0-beta`.
The Release workflow builds the Windows ZIP and creates a draft release using the matching section
of `CHANGELOG.md`; publishing the draft is a separate release action.

The Docker workflow builds tagged images. A stable version tag moves `latest`; a tag with a suffix
does not. The plugins image is keyed by the `vsplugins/` content hash so unchanged toolchains can be
reused. Neither workflow is required to deploy a documentation-only update.
