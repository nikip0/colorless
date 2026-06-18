# Releasing colorless

Published under names that differ from the bare brand (both `colorless` names were taken):

| | Package name | Users install / import |
|---|---|---|
| **PyPI** | `colorless-audit` | `pip install colorless-audit` → `import colorless` |
| **npm**  | `@nikip0/colorless` | `npm install @nikip0/colorless` |

> On this Mac there's no bare `pip` alias — use `python3 -m pip`.

## One-time setup
- **PyPI** account with 2FA + an API token (https://pypi.org/manage/account/token/).
- **npm** account with 2FA (`npm login` in the terminal).
- Tooling: `python3 -m pip install --upgrade build twine`; Node 18+ for npm.

## Per-release steps
1. **Bump the version** in both packages (keep them in lockstep):
   ```bash
   # pyproject.toml      -> version = "X.Y.Z"
   # clients/js/package.json
   cd clients/js && npm version X.Y.Z --no-git-tag-version && cd ..
   ```
2. **Update `CHANGELOG.md`** — add an `## [X.Y.Z] — DATE` section.
3. **Test, then commit:**
   ```bash
   python3 -m unittest discover -s tests -p 'test_*.py'
   (cd clients/js && node --test)
   git add -A && git commit -m "release: vX.Y.Z" && git push origin main
   ```
4. **Publish Python:**
   ```bash
   rm -rf dist && python3 -m build
   python3 -m twine upload dist/*        # username: __token__   password: your pypi-… token
   ```
5. **Publish JS:**
   ```bash
   cd clients/js && npm publish --access public && cd ..
   ```
6. **Tag + GitHub Release:**
   ```bash
   git tag vX.Y.Z && git push origin vX.Y.Z
   gh release create vX.Y.Z --title "colorless vX.Y.Z" --notes-file <(sed -n '/## \[X.Y.Z\]/,/## \[/p' CHANGELOG.md)
   ```
7. **Verify from a clean shell:**
   ```bash
   python3 -m pip install -U colorless-audit && python3 -c "import colorless; print('ok')"
   npm install @nikip0/colorless
   ```

## Notes
- The PyPI **distribution** name (`colorless-audit`) is intentionally not the import name (`colorless`); don't "fix" it.
- Core stays **zero-dependency**; OpenTelemetry is an optional extra (`colorless-audit[otel]`).
- Credentials are always run by the owner — never commit tokens.
