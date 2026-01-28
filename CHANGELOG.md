# Changelog

## 0.5.5

* Ensure that POT content is now sorted by path when merging POTs from multiple sources (i.e., templates and content).
* `xgettext` is used to merge POT files instead of `msgcat`, providing a better header and merging of same strings from different sources.
* The initially generated PO files will now have a header compatible with GNOME's Translation Editor, since they will have a non-placeholder `Project-Id-Version`. Existing users hitting this problem will need to fill in the `Project-Id-Version` header manually.
* Translations in templates now provide pgettext and ngettext methods.
* The bug with non-English content is resolved.

## 0.5.4

* POT content is now sorted by path.

## 0.5.3

* `POT-Creation-Date` in `.pot` file is only updated on initial creation.

## 0.5.2

* Ensure that PO file merging is performed by file, avoiding changes in PO file order (which cases large PO file deltas)

## 0.5.1

* Include fuzzy translations in the compiled `.mo` files

## 0.5.0

* Remove Python 2 compatibility code, and update code to use modern Python idiom.

* Add patches applied by [The Tor Project](https://gitlab.torproject.org/tpo/web/lego/-/blob/b1de03b222fad02369017afce3a12ccd5f8990f2/packages/i18n/lektor_i18n.py) in November 2024 to their own fork. These patches optimize some of the ordering of translation commands to avoid the need for multiple


## 0.4.4

Initial code import from [Numericube repisot](https://github.com/numericube/lektor-i18n-plugin).
