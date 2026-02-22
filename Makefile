.PHONY: major minor patch

VERSION = $(shell python -c "from app import __version__; print(__version__)")

major:
	$(MAKE) release PART=major

minor:
	$(MAKE) release PART=minor

patch:
	$(MAKE) release PART=patch

release:
	bump-my-version bump $(PART)
	git-cliff --config pyproject.toml --output CHANGELOG.md
	sed -i 's/<!-- [0-9]* -->//g' CHANGELOG.md
	git add CHANGELOG.md
	git commit --amend --no-edit
	git tag -f v$(VERSION)
	git push && git push --tags --force
