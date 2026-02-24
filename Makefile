.PHONY: help # print this help list
help:
	grep PHONY Makefile | sed 's/.PHONY: /make /' | grep -v grep

.PHONY: major minor patch # update version, CHANGELOG.md and push with also tags

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

.PHONY: changelog # update CHANGELOG.md and amend it on the commit
changelog:
	git-cliff --config pyproject.toml --output CHANGELOG.md
	sed -i 's/<!-- [0-9]* -->//g' CHANGELOG.md
	git add CHANGELOG.md
	git commit --amend --no-edit
